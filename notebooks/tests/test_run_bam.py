#!/usr/bin/env python
"""
Regression tests for the safeguards in notebooks/run_bam.py (no containers, no input data, runs in seconds).

  python3 notebooks/tests/test_run_bam.py -v

Guarded behaviour:
  - the script check: AIS listed together with EAIS/WAIS in a facts-total --item list is flagged (global and local),
    correct lists are not, and the committed experiments are classified correctly;
  - preflight refuses a script generated for another workspace (absolute WORKSPACE=...);
  - registry_has_fix, and the tracked registry patch itself;
  - main(): refuses a double-counting script in run mode (nothing executed), --allow-double-count overrides it,
    --skip-run only warns;
  - validate_outputs: accepts AIS+GIS totals, warns on the four-way sum, reports the many-site median definition,
    fails on missing files (needs xarray + netCDF4 + numpy; skipped if they are not importable).
"""

import importlib.util
import logging
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
spec = importlib.util.spec_from_file_location("run_bam", os.path.join(REPO, "notebooks", "run_bam.py"))
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)

try:
    import numpy as np
    import xarray as xr
    xr.Dataset().to_netcdf  # attribute exists even without a backend; the backend is checked in the test setup
    HAVE_XARRAY = True
except Exception:  # pragma: no cover
    HAVE_XARRAY = False


def quiet_logger():
    log = logging.getLogger("test_run_bam")
    log.handlers[:] = [logging.NullHandler()]
    log.propagate = False
    return log


def item(module, comp, kind):
    return f'    "--item=/mnt/total_out/{module}/{comp}-{kind}.nc" \\\n'


def write_script(path, items, workspace=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    head = f'WORKSPACE="{workspace}"\n' if workspace else ""
    with open(path, "w") as f:
        f.write("#!/usr/bin/env bash\n" + head + "run_service facts-total \\\n" + "".join(items))


class CheckTotalItems(unittest.TestCase):
    def check(self, items):
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "exp", "experiment-apptainer.sh")
            write_script(script, items)
            return rb.check_total_items(rb.Config(workspace=d, experiment="exp"), quiet_logger())

    def test_four_way_sum_is_flagged(self):
        problems = self.check([item("bamber19-icesheets", c, "gslr") for c in ("AIS", "EAIS", "WAIS", "GIS")])
        self.assertEqual(len(problems), 1)
        self.assertIn("AIS together with EAIS and WAIS", problems[0])
        self.assertIn("gslr", problems[0])

    def test_ais_with_only_one_part_is_flagged(self):
        self.assertEqual(len(self.check([item("bamber19-icesheets", c, "lslr") for c in ("AIS", "WAIS")])), 1)

    def test_correct_lists_pass(self):
        self.assertEqual(self.check([item("bamber19-icesheets", c, "gslr") for c in ("AIS", "GIS")]), [])
        self.assertEqual(self.check([item("bamber19-icesheets", c, "lslr") for c in ("EAIS", "WAIS", "GIS")]), [])

    def test_parts_from_a_different_module_are_not_flagged(self):
        self.assertEqual(self.check([item("bamber19-icesheets", "AIS", "gslr"), item("emulandice", "EAIS", "gslr")]), [])

    def test_only_the_bad_result_type_is_reported(self):
        items = ([item("bamber19-icesheets", c, "gslr") for c in ("AIS", "GIS")]
                 + [item("bamber19-icesheets", c, "lslr") for c in ("AIS", "EAIS", "GIS")])
        problems = self.check(items)
        self.assertEqual(len(problems), 1)
        self.assertIn("lslr", problems[0])

    def test_no_items_or_no_script_is_not_a_problem(self):
        self.assertEqual(self.check([]), [])
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rb.check_total_items(rb.Config(workspace=d, experiment="missing"), quiet_logger()), [])

    def test_committed_experiments(self):
        base = os.path.join(REPO, "facts2", "apptainer_experiments")
        cases = {"bam_ssp585": True, "bam_ssp585_fixed": False, "bam_ssp585_fixed_gauges": False}   # True = double-counts
        for name, bad in cases.items():
            if not os.path.isfile(os.path.join(base, name, "experiment-apptainer.sh")):
                self.skipTest(f"{name} not present in this checkout")
            problems = rb.check_total_items(rb.Config(workspace=os.path.join(REPO, "facts2"),
                                                      experiment=f"apptainer_experiments/{name}"), quiet_logger())
            self.assertEqual(bool(problems), bad, f"{name}: {problems}")


class PreflightWorkspaceGuard(unittest.TestCase):
    def make_workspace(self, d):
        for sub in ("module_specific_input_data/bamber19-icesheets", "module_specific_input_data/fair-temperature",
                    "shared_input_data/FPRINT"):
            os.makedirs(os.path.join(d, "data", sub), exist_ok=True)
        open(os.path.join(d, "data", "shared_input_data", "location.lst"), "w").close()

    def run_preflight(self, ws, script_workspace):
        write_script(os.path.join(ws, "exp", "experiment-apptainer.sh"), [], workspace=script_workspace)
        with mock.patch.object(rb.shutil, "which", return_value="/usr/bin/apptainer"):
            return rb.preflight(rb.Config(workspace=ws, experiment="exp"), quiet_logger())

    def test_script_for_another_workspace_is_refused(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            self.make_workspace(d)
            self.assertFalse(self.run_preflight(d, other))

    def test_script_for_this_workspace_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self.make_workspace(d)
            self.assertTrue(self.run_preflight(d, d))

    def test_same_workspace_through_a_symlink_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self.make_workspace(d)
            link = d + "_link"
            os.symlink(d, link)
            try:
                self.assertTrue(self.run_preflight(d, link))
            finally:
                os.unlink(link)

    def test_missing_input_data_is_refused(self):
        with tempfile.TemporaryDirectory() as d:        # no data dirs at all
            self.assertFalse(self.run_preflight(d, d))


class RegistryFix(unittest.TestCase):
    def registry(self, d, text):
        path = os.path.join(d, "facts-module-registry", "bamber19-icesheets")
        os.makedirs(path)
        with open(os.path.join(path, "bamber19_icesheets_module.yaml"), "w") as f:
            f.write(text)

    def test_detects_the_fix(self):
        with tempfile.TemporaryDirectory() as d:
            self.registry(d, "        output_type: global\n        pass_to_total: false\n")
            self.assertTrue(rb.registry_has_fix(rb.Config(workspace=d)))

    def test_detects_a_pristine_registry(self):
        with tempfile.TemporaryDirectory() as d:
            self.registry(d, "        output_type: global\n")
            self.assertFalse(rb.registry_has_fix(rb.Config(workspace=d)))

    def test_missing_registry_counts_as_unfixed(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(rb.registry_has_fix(rb.Config(workspace=d)))

    def test_tracked_patch_marks_exactly_the_four_eais_wais_outputs(self):
        patch = os.path.join(REPO, "facts2", "patches", "bamber19_pass_to_total.patch")
        if not os.path.isfile(patch):
            self.skipTest("patch not present in this checkout")
        with open(patch) as f:
            lines = f.read().splitlines()
        added = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
        self.assertEqual([l.strip() for l in added], ["+        pass_to_total: false"] * 4)
        removed = [l for l in lines if l.startswith("-") and not l.startswith("---")]
        self.assertEqual(removed, [])
        text = "\n".join(lines)
        for name in ("EAIS-gslr", "WAIS-gslr", "EAIS-lslr", "WAIS-lslr"):
            self.assertIn(f"{name}.nc", text)
        self.assertNotIn("AIS-gslr.nc\"\n+", text)   # AIS and GIS outputs keep the default (passed to the total)


def config_text(exp_params=None):
    p = {"pipeline-id": "bam001", "nsamps": "500", "scenario": "ssp585",
         "pyear_start": "2020", "pyear_end": "2150", "pyear_step": "10"}
    p.update(exp_params or {})
    body = "".join(f"{k}:\n        {v}\n" for k, v in p.items())
    return body + 'fair-temperature:\n  image: "ghcr.io/fact-sealevel/fair-temperature:0.2.1"\n' \
                  'bamber19-icesheets:\n  image: "ghcr.io/fact-sealevel/bamber19-icesheets:0.2.0"\n'


class MainFlow(unittest.TestCase):
    def run_main(self, items, argv_extra, ok_outputs=True):
        with tempfile.TemporaryDirectory() as d:
            exp = os.path.join(d, "apptainer_experiments", "x")
            os.makedirs(exp)
            with open(os.path.join(exp, "experiment-config.yaml"), "w") as f:
                f.write(config_text())
            write_script(os.path.join(exp, "experiment-apptainer.sh"), items, workspace=d)
            calls = {"run": 0}

            def fake_run(cfg, log):
                calls["run"] += 1
                return {"exit": 0, "wall_s": 1.0}

            argv = ["run_bam.py", "--workspace", d, "--experiment", "apptainer_experiments/x"] + argv_extra
            with mock.patch.object(sys, "argv", argv), mock.patch.object(rb, "preflight", return_value=True), \
                    mock.patch.object(rb, "run_script", side_effect=fake_run), \
                    mock.patch.object(rb, "validate_outputs", return_value={"ok": ok_outputs, "warnings": []}), \
                    mock.patch.object(rb, "setup_logging", return_value=quiet_logger()):
                rc = rb.main()
            return rc, calls["run"]

    BAD = [item("bamber19-icesheets", c, "gslr") for c in ("AIS", "EAIS", "WAIS", "GIS")]
    GOOD = [item("bamber19-icesheets", c, "gslr") for c in ("AIS", "GIS")]

    def test_double_counting_script_is_refused_and_nothing_runs(self):
        rc, runs = self.run_main(self.BAD, [])
        self.assertEqual((rc, runs), (1, 0))

    def test_allow_double_count_overrides(self):
        rc, runs = self.run_main(self.BAD, ["--allow-double-count"])
        self.assertEqual((rc, runs), (0, 1))

    def test_skip_run_only_warns(self):
        rc, runs = self.run_main(self.BAD, ["--skip-run"])
        self.assertEqual((rc, runs), (0, 0))

    def test_correct_script_runs(self):
        rc, runs = self.run_main(self.GOOD, [])
        self.assertEqual((rc, runs), (0, 1))

    def test_failed_output_validation_gives_nonzero_exit(self):
        rc, runs = self.run_main(self.GOOD, [], ok_outputs=False)
        self.assertEqual((rc, runs), (1, 1))


@unittest.skipUnless(HAVE_XARRAY, "needs xarray, netCDF4 and numpy")
class ValidateOutputs(unittest.TestCase):
    N, YEARS, SITES = 20, list(range(2020, 2151, 10)), 3

    def write_slr(self, path, a, with_sites):
        a = a[:, :, None] * (np.array([0.5, 1.0, 1.5]) if with_sites else np.array([1.0]))[None, None, :]
        n, ny, ns = a.shape
        ds = xr.Dataset({"sea_level_change": (("samples", "years", "locations"), a, {"units": "mm"}),
                         "lat": (("locations",), np.linspace(-10, 10, ns)), "lon": (("locations",), np.linspace(0, 20, ns))},
                        coords={"samples": np.arange(n), "years": np.array(self.YEARS, dtype=np.int32),
                                "locations": np.arange(ns)})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ds.to_netcdf(path)

    def build(self, d, double_count=False, drop=None):
        rng = np.random.default_rng(0)
        out = os.path.join(d, "exp", "output-apptainer")
        ais = rng.uniform(10, 500, (self.N, len(self.YEARS)))
        parts = {"AIS": ais, "EAIS": ais * 0.5, "WAIS": ais * 0.5, "GIS": rng.uniform(10, 300, (self.N, len(self.YEARS)))}
        total = parts["AIS"] + parts["GIS"] + (parts["EAIS"] + parts["WAIS"] if double_count else 0)
        for kind, sites in (("gslr", False), ("lslr", True)):
            for c, a in parts.items():
                self.write_slr(os.path.join(out, "bamber19-icesheets", f"{c}-{kind}.nc"), a, sites)
            scale = "global" if kind == "gslr" else "local"
            self.write_slr(os.path.join(out, "facts-total", f"all-modules_{scale}_total.nc"), total, sites)
        fair = os.path.join(out, "fair-temperature")
        os.makedirs(fair, exist_ok=True)
        xr.Dataset(coords={"year": [1, 2]}).to_netcdf(os.path.join(fair, "climate.nc"))
        for name, var in (("gsat", "surface_temperature"), ("oceantemp", "deep_ocean_temperature"), ("ohc", "ocean_heat_content")):
            xr.Dataset({var: (("samples", "years"), rng.normal(size=(self.N, 4)))},
                       coords={"samples": np.arange(self.N), "years": np.arange(4)}).to_netcdf(os.path.join(fair, f"{name}.nc"))
        if drop:
            os.remove(os.path.join(out, drop))
        return total

    def cfg(self, d):
        return rb.Config(workspace=d, experiment="exp", nsamps=self.N)

    def test_correct_totals_pass_without_warnings(self):
        with tempfile.TemporaryDirectory() as d:
            self.build(d)
            report = rb.validate_outputs(self.cfg(d), quiet_logger())
            self.assertTrue(report["ok"])
            self.assertEqual(report["warnings"], [])

    def test_four_way_sum_total_warns_but_outputs_are_valid(self):
        with tempfile.TemporaryDirectory() as d:
            self.build(d, double_count=True)
            report = rb.validate_outputs(self.cfg(d), quiet_logger())
            self.assertTrue(report["ok"])
            self.assertEqual(len(report["warnings"]), 2)                  # global and local
            self.assertTrue(all("double-counts Antarctica" in w for w in report["warnings"]))

    def test_many_site_median_is_a_median_across_sites(self):
        with tempfile.TemporaryDirectory() as d:
            total = self.build(d)
            report = rb.validate_outputs(self.cfg(d), quiet_logger())
            self.assertIn("median across sites", report["p50_last_definition"])
            per_site = [np.median(total[:, -1] * s) for s in (0.5, 1.0, 1.5)]
            self.assertAlmostEqual(report["total_local"]["p50_last_total"], float(np.median(per_site)), places=6)
            self.assertAlmostEqual(report["total_global"]["p50_last_total"], float(np.median(total[:, -1])), places=6)

    def test_missing_output_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self.build(d, drop="bamber19-icesheets/GIS-gslr.nc")
            self.assertFalse(rb.validate_outputs(self.cfg(d), quiet_logger())["ok"])

    def test_wrong_sample_count_fails(self):
        with tempfile.TemporaryDirectory() as d:
            self.build(d)
            self.assertFalse(rb.validate_outputs(rb.Config(workspace=d, experiment="exp", nsamps=self.N + 1),
                                                 quiet_logger())["ok"])


if __name__ == "__main__":
    unittest.main()
