"""
Regression tests for notebooks/run_coupling.py (stdlib only; the netCDF tests run when numpy, xarray and netCDF4 import).

  python3 notebooks/tests/test_run_coupling.py -v
"""

import os
import re
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import run_coupling as rc   # noqa: E402

try:
    import numpy as np
    import xarray as xr
    xr.Dataset().to_netcdf  # noqa: B018
    HAVE_NC = True
except Exception:                      # pragma: no cover
    HAVE_NC = False


def service(name, items, out):
    body = "".join(f'    "--item=/mnt/total_out/{i}" \\\n' for i in items)
    return (f'run_service "facts-total-{name}-0.2.1" \\\n    "--pyear-start=2020" \\\n{body}'
            f'    "--output-path=/mnt/total_out/{out}" &\nPID_X=$!\n\n')


GOOD = ("pull_image \"fair-temperature-0.2.1\" \"ghcr.io/x/fair-temperature:0.2.1\"\n"
        "pull_image \"facts-total-wf1e-global-0.2.1\" \"ghcr.io/x/facts-total:0.2.1\"\n"
        "pull_image \"facts-total-wf1e-local-0.2.1\" \"ghcr.io/x/facts-total:0.2.1\"\n\n"
        + service("wf1e-global", ["emulandice-ais/output-gslr.nc", "emulandice-ais/output-gslr-eais.nc"][:1] +
                  ["tlm-sterodynamics/gslr.nc"], "facts-total/wf1e_global_total.nc")
        + service("wf4-local", ["bamber19-icesheets/AIS-lslr.nc", "bamber19-icesheets/GIS-lslr.nc"], "facts-total/wf4_local_total.nc"))


class ParseScript(unittest.TestCase):
    def test_totals_are_grouped_per_workflow_and_scale(self):
        t = rc.parse_totals(GOOD)
        self.assertEqual(sorted(t), ["wf1e-global", "wf4-local"])
        self.assertEqual(t["wf4-local"], ["bamber19-icesheets/AIS-lslr.nc", "bamber19-icesheets/GIS-lslr.nc"])

    def test_images_in_order(self):
        self.assertEqual([n for n, _ in rc.parse_images(GOOD)],
                         ["fair-temperature-0.2.1", "facts-total-wf1e-global-0.2.1", "facts-total-wf1e-local-0.2.1"])

    def test_expected_files_include_totals(self):
        text = 'x "--output-gsat-file=/mnt/out/fair-temperature/gsat.nc" \\\n' + service("wf1e-global", ["a/b.nc"], "facts-total/wf1e_global_total.nc")
        self.assertEqual(rc.expected_files(text), ["a/b.nc", "facts-total/wf1e_global_total.nc", "fair-temperature/gsat.nc"])   # items are module outputs too


class DoubleCount(unittest.TestCase):
    def test_aggregate_only_is_fine(self):
        self.assertEqual(rc.check_total_items(GOOD), [])

    def test_each_module_family_is_flagged(self):
        cases = {
            "bamber19-icesheets": ["AIS-gslr.nc", "EAIS-gslr.nc", "GIS-gslr.nc"],
            "deconto21-ais": ["ais-lslr.nc", "wais-lslr.nc"],
            "larmip-ais": ["ais_global_output.nc", "smb_global_output.nc"],
            "emulandice-ais": ["output-gslr.nc", "output-gslr-wais.nc"],
        }
        for mod, files in cases.items():
            with self.subTest(mod=mod):
                text = service("wf9-global", [f"{mod}/{f}" for f in files], "facts-total/wf9_global_total.nc")
                problems = rc.check_total_items(text)
                self.assertEqual(len(problems), 1)
                self.assertIn(mod, problems[0])

    def test_parts_without_aggregate_are_fine(self):
        text = service("wf9-global", ["larmip-ais/eais_global_output.nc", "larmip-ais/wais_global_output.nc"], "x.nc")
        self.assertEqual(rc.check_total_items(text), [])

    def test_aggregate_in_one_module_does_not_flag_another(self):
        text = service("wf9-global", ["bamber19-icesheets/AIS-gslr.nc", "deconto21-ais/eais-gslr.nc"], "x.nc")
        self.assertEqual(rc.check_total_items(text), [])


class Preflight(unittest.TestCase):
    def make(self, text, workspace=None):
        d = tempfile.mkdtemp()
        ws = workspace or d
        exp = os.path.join(d, "exp")
        os.makedirs(exp)
        with open(os.path.join(exp, "experiment-apptainer.sh"), "w") as f:
            f.write(f'WORKSPACE="{ws}"\n' + text)
        for sub in ("shared_input_data/FPRINT", "module_specific_input_data/fair-temperature"):
            os.makedirs(os.path.join(d, "data", sub))
        open(os.path.join(d, "data/shared_input_data/location.lst"), "w").close()
        return rc.Config(workspace=d, experiment="exp")

    def log(self):
        return mock.MagicMock()

    def test_double_count_blocks_the_run(self):
        cfg = self.make(service("wf9-global", ["bamber19-icesheets/AIS-gslr.nc", "bamber19-icesheets/EAIS-gslr.nc"], "x.nc"))
        with mock.patch("shutil.which", return_value="/usr/bin/apptainer"):
            self.assertFalse(rc.preflight(cfg, self.log()))
            cfg.allow_double_count = True
            self.assertTrue(rc.preflight(cfg, self.log()))

    def test_script_for_another_workspace_is_refused(self):
        cfg = self.make(GOOD, workspace="/somewhere/else")
        with mock.patch("shutil.which", return_value="/usr/bin/apptainer"):
            self.assertFalse(rc.preflight(cfg, self.log()))

    def test_missing_bind_source_is_reported(self):
        cfg = self.make('BINDS=(\n    "--bind=/nonexistent/data/module_specific_input_data/ipccar5:/mnt/module_specific_in"\n)\n' + GOOD)
        with mock.patch("shutil.which", return_value="/usr/bin/apptainer"):
            log = self.log()
            self.assertFalse(rc.preflight(cfg, log))
            self.assertIn("ipccar5", log.error.call_args[0][0])

    def test_clean_script_passes(self):
        cfg = self.make(GOOD)
        with mock.patch("shutil.which", return_value="/usr/bin/apptainer"):
            self.assertTrue(rc.preflight(cfg, self.log()))


class ShimBehaviour(unittest.TestCase):
    """Runs the generated PATH shim in front of a fake `apptainer` that just echoes its arguments."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        fake = os.path.join(self.d, "fakebin")
        os.makedirs(fake)
        with open(os.path.join(fake, "apptainer"), "w") as f:
            f.write('#!/usr/bin/env bash\necho "REAL $*"\n')
        os.chmod(os.path.join(fake, "apptainer"), 0o755)
        self.out = os.path.join(self.d, "out")
        os.makedirs(os.path.join(self.out, "mod"))
        self.claims = os.path.join(self.d, "claims")
        os.makedirs(self.claims)
        self.path = fake + os.pathsep + os.environ["PATH"]

    def shim(self, gates=(), resume=False, claims=False):
        with mock.patch.dict(os.environ, {"PATH": self.path}):
            bindir = rc.write_shim(os.path.join(self.d, "run%d" % len(os.listdir(self.d))), gates, resume, mock.MagicMock(),
                                   self.claims if claims else None)
        return bindir

    def call(self, bindir, sif, *flags, timeout=10):
        import subprocess
        env = dict(os.environ, PATH=bindir + os.pathsep + self.path)
        try:
            p = subprocess.run(["apptainer", "run", "--pwd", "/", f"--bind={self.out}:/mnt/out", f"/x/sif/{sif}.sif", *flags],
                               env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return None
        return p.returncode, p.stdout, p.stderr

    def test_non_run_commands_pass_through(self):
        import subprocess
        env = dict(os.environ, PATH=self.shim() + os.pathsep + self.path)
        p = subprocess.run(["apptainer", "pull", "docker://x"], env=env, capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "REAL pull docker://x")

    def test_emulandice_gets_a_writable_working_directory_others_do_not(self):
        b = self.shim()
        self.assertIn("--pwd /tmp", self.call(b, "emulandice-ais-0.2.0")[1])
        self.assertIn("--pwd / ", self.call(b, "bamber19-icesheets-0.2.0")[1])

    def test_patched_file_is_bound_only_for_emulandice_glaciers_and_only_if_it_exists(self):
        ws = os.path.join(self.d, "ws")
        os.makedirs(os.path.join(ws, "patches/container"))
        with mock.patch.dict(os.environ, {"PATH": self.path}):
            absent = rc.write_shim(os.path.join(self.d, "run_a"), (), False, mock.MagicMock(), None, ws)
            open(os.path.join(ws, "patches/container/emulandice_glaciers_project.py"), "w").close()
            present = rc.write_shim(os.path.join(self.d, "run_b"), (), False, mock.MagicMock(), None, ws)
        want = f"--bind={ws}/patches/container/emulandice_glaciers_project.py:/opt/emulandice/src/emulandice/emulandice_glaciers_project.py:ro"
        self.assertNotIn("emulandice_glaciers_project", self.call(absent, "emulandice-glaciers-0.2.0")[1])
        self.assertIn(want, self.call(present, "emulandice-glaciers-0.2.0")[1])
        self.assertNotIn("emulandice_glaciers_project", self.call(present, "emulandice-ais-0.2.0")[1])
        self.assertNotIn("emulandice_glaciers_project", self.call(present, "bamber19-icesheets-0.2.0")[1])
        self.assertTrue(self.call(present, "emulandice-glaciers-0.2.0")[1].startswith("REAL run --bind="))

    def test_speedup_patches_are_bound_for_the_right_services(self):
        ws = os.path.join(self.d, "ws2")
        os.makedirs(os.path.join(ws, "patches/container"))
        for name in ("emulandice_r_helper.py", "emulandice_main.R", "fair_temperature_project.py", "emulandice_glaciers_project.py"):
            open(os.path.join(ws, "patches/container", name), "w").close()
        with mock.patch.dict(os.environ, {"PATH": self.path}):
            b = rc.write_shim(os.path.join(self.d, "run_sp"), (), False, mock.MagicMock(), None, ws)
        helper = "/opt/emulandice/src/emulandice/r_helper.py:ro"
        main_r = "/opt/emulandice/modules/emulandice/shared/emulandice/R/main.R:ro"
        fair = "/opt/fair-temperature/src/fair_temperature/fair_temperature_project.py:ro"
        glaciers = "/opt/emulandice/src/emulandice/emulandice_glaciers_project.py:ro"
        for svc in ("emulandice-ais-0.2.0", "emulandice-gris-0.2.0", "emulandice-glaciers-0.2.0"):
            out = self.call(b, svc)[1]
            self.assertIn(helper, out, svc)
            self.assertIn(main_r, out, svc)
            self.assertNotIn(fair, out, svc)
        self.assertIn(glaciers, self.call(b, "emulandice-glaciers-0.2.0")[1])
        self.assertNotIn(glaciers, self.call(b, "emulandice-gris-0.2.0")[1])
        out = self.call(b, "fair-temperature-0.2.1")[1]
        self.assertIn(fair, out)
        self.assertNotIn(helper, out)
        for svc in ("bamber19-icesheets-0.2.0", "tlm-sterodynamics-0.3.2", "facts-total-wf1e-global-0.2.1"):
            self.assertNotIn("--bind=" + ws, self.call(b, svc)[1], svc)

    def test_simultaneous_joins_get_different_log_files(self):
        import concurrent.futures
        d = os.path.join(self.d, "joinlogs")
        os.makedirs(d)
        with concurrent.futures.ThreadPoolExecutor(8) as ex:
            names = list(ex.map(lambda _: rc.reserve_join_log(d), range(24)))
        self.assertEqual(len(set(names)), 24)
        self.assertEqual(os.path.basename(names[0]).startswith("run.join"), True)

    def test_emulandice_gets_a_large_private_tmp_that_is_removed_afterwards(self):
        run_dir = os.path.join(self.d, "run_tmp")
        with mock.patch.dict(os.environ, {"PATH": self.path}):
            b = rc.write_shim(run_dir, (), False, mock.MagicMock())
        out = self.call(b, "emulandice-glaciers-0.2.0")[1]
        m = re.search(r"--bind=(%s/tmp\.\w+):/tmp" % re.escape(run_dir), out)
        self.assertIsNotNone(m, out)                                                    # a fresh directory under the run dir is bound over /tmp
        self.assertFalse(os.path.exists(m.group(1)))                                    # ... and is gone after the container exits
        self.assertNotIn(":/tmp", self.call(b, "bamber19-icesheets-0.2.0")[1].replace("--pwd /tmp", ""))

    def test_gate_holds_until_the_file_exists(self):
        gate = os.path.join(self.d, "ready")
        b = self.shim(gates=(f"tlm-sterodynamics={gate}",))
        self.assertIsNone(self.call(b, "tlm-sterodynamics-0.3.2", timeout=3))          # still waiting
        open(gate, "w").close()
        self.assertEqual(self.call(b, "tlm-sterodynamics-0.3.2")[0], 0)
        self.assertIn("REAL run", self.call(b, "tlm-sterodynamics-0.3.2")[1])

    def test_resume_skips_only_when_every_declared_path_exists(self):
        b = self.shim(resume=True)
        flags = ("--out-a=/mnt/out/mod/a.nc", "--out-b=/mnt/out/mod/b.nc")
        open(os.path.join(self.out, "mod/a.nc"), "w").write("x")
        r = self.call(b, "m-1", *flags)
        self.assertIn("REAL run", r[1])                                                # b.nc missing: runs
        open(os.path.join(self.out, "mod/b.nc"), "w").write("x")
        r = self.call(b, "m-1", *flags)
        self.assertEqual(r[1], "")
        self.assertIn("[resume] skipping m-1.sif", r[2])

    def test_resume_off_never_skips(self):
        open(os.path.join(self.out, "mod/a.nc"), "w").write("x")
        self.assertIn("REAL run", self.call(self.shim(), "m-1", "--out-a=/mnt/out/mod/a.nc")[1])

    def test_second_instance_skips_a_claimed_service(self):
        b = self.shim(claims=True)
        self.assertIn("REAL run", self.call(b, "m-1")[1])                              # first instance claims and runs
        r = self.call(b, "m-1")
        self.assertEqual(r[1], "")
        self.assertIn("[claim] m-1 is being run by another instance", r[2])
        self.assertIn("REAL run", self.call(b, "m-2")[1])                              # other services are still free

    def test_total_waits_for_its_items(self):
        b = self.shim(claims=True)
        item = os.path.join(self.out, "mod/a.nc")
        self.assertIsNone(self.call(b, "facts-total-1", "--item=/mnt/out/mod/a.nc", timeout=3))
        open(item, "w").write("x")
        self.assertIn("REAL run", self.call(b, "facts-total-2", "--item=/mnt/out/mod/a.nc")[1])


class ServiceTimes(unittest.TestCase):
    def test_skipped_and_failed_services_are_not_counted(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "run.log"), "w") as f:
            f.write("[06:00:00] Running service: a-1\n[06:14:30] Completed: a-1\n"
                    "[06:14:30] Running service: b-1\n[resume] skipping b-1.sif: its 3 declared paths already exist\n[06:14:30] Completed: b-1\n"
                    "[06:14:30] Running service: c-1\n")                       # c never completed
        with open(os.path.join(d, "run.join.log"), "w") as f:
            f.write("[06:20:00] Running service: b-1\n[06:25:00] Completed: b-1\n"
                    "[06:25:00] Running service: facts-total-wf1-global-0.2.1\n[06:40:00] Completed: facts-total-wf1-global-0.2.1\n")
        with open(os.path.join(d, "run.join.2.log"), "w") as f:                     # a longer but EARLIER run of b-1 (its output was replaced)
            f.write("[05:00:00] Running service: b-1\n[05:59:00] Completed: b-1\n")
        r = rc.collect_service_times(d)
        s = r["services"]
        self.assertEqual(s["a-1"]["seconds"], 14 * 60 + 30)
        self.assertEqual(s["b-1"]["seconds"], 300)                               # the latest completed run, not the longest
        self.assertNotIn("c-1", s)
        self.assertTrue(s["facts-total-wf1-global-0.2.1"]["includes_wait_for_inputs"])
        self.assertEqual(s["a-1"]["start"], "06:00:00")


class Regenerate(unittest.TestCase):
    def test_refuses_to_overwrite_an_existing_config(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "exp"))
        open(os.path.join(d, "exp", "experiment-config.yaml"), "w").close()
        cfg = rc.Config(workspace=d, experiment="exp")
        with mock.patch.object(rc, "feb") as feb:
            self.assertFalse(rc.regenerate(cfg, mock.MagicMock()))
            feb.assert_not_called()

    def test_catalog_command_and_workflow_answers(self):
        d = tempfile.mkdtemp()
        cfg = rc.Config(workspace=d, experiment="apptainer_experiments/e")
        calls = []

        def fake_feb(c, args, log, stdin=None):
            calls.append((args, stdin))
            if args[0] == "setup-experiment":
                os.makedirs(c.exp_dir, exist_ok=True)
                with open(c.config_yaml, "w") as f:
                    f.write('pipeline-id:\n        # Pipeline ID\nworkflows:\n  all-modules: "a, b"\n  wf1e: "x"\n'
                            'module-specific-input-data:\n        # Module-specific input data\nshared-input-data:\n'
                            '        # Shared input data\nexperiment-specific-input-data:\n        []\n'
                            'emulandice-ais:\n  inputs:\n    input-data-file:\n      "fair-temperature/climate.nc"  # x\n'
                            'emulandice-glaciers:\n  inputs:\n    input-data-file:\n      "fair-temperature/climate.nc"  # x\n'
                            'larmip-ais:\n  inputs:\n    climate-data-file:\n      "fair-temperature/climate.nc"  # x\n')
            return 0

        with mock.patch.object(rc, "feb", side_effect=fake_feb):
            self.assertTrue(rc.regenerate(cfg, mock.MagicMock()))
        setup, stdin = calls[0]
        self.assertIn("extremesealevel-pointsoverthreshold", setup)
        self.assertEqual(setup[setup.index("--nsamps") + 1], "2000")
        answers = stdin.split("\n")
        self.assertEqual(answers[0], "y")
        self.assertEqual([answers[1 + 3 * i] for i in range(6)], list(rc.WORKFLOWS))
        self.assertEqual(answers[-2], "n")
        self.assertEqual(calls[1][0][0], "generate-apptainer")
        text = open(cfg.config_yaml).read()
        self.assertNotIn("all-modules", text)                      # the catalog has no such workflow
        self.assertIn("wf1e", text)
        self.assertRegex(text, r"pipeline-id:\n        abcd\n")
        self.assertRegex(text, rf'module-specific-input-data:\n        "{re.escape(d)}/data/module_specific_input_data"')
        self.assertRegex(text, rf'shared-input-data:\n        "{re.escape(d)}/data/shared_input_data"')
        self.assertRegex(text, r'emulandice-glaciers:\n  inputs:\n    input-data-file:\n      "fair-temperature/gsat.nc"')
        self.assertRegex(text, r'emulandice-ais:\n  inputs:\n    input-data-file:\n      "fair-temperature/climate.nc"')   # untouched
        self.assertRegex(text, r'larmip-ais:\n  inputs:\n    climate-data-file:\n      "fair-temperature/climate.nc"')   # untouched

    def test_existing_data_paths_are_not_overwritten(self):
        d = tempfile.mkdtemp()
        cfg = rc.Config(workspace=d, experiment="e")

        def fake_feb(c, args, log, stdin=None):
            if args[0] == "setup-experiment":
                os.makedirs(c.exp_dir, exist_ok=True)
                with open(c.config_yaml, "w") as f:
                    f.write('pipeline-id:\n  zzz\nmodule-specific-input-data:\n        "/mine/m"\nshared-input-data:\n        "/mine/s"\n')
            return 0

        with mock.patch.object(rc, "feb", side_effect=fake_feb):
            rc.regenerate(cfg, mock.MagicMock())
        text = open(cfg.config_yaml).read()
        self.assertIn('"/mine/m"', text)
        self.assertNotIn(d + "/data", text)


@unittest.skipUnless(HAVE_NC, "numpy/xarray/netCDF4 not importable")
class ValidateOutputs(unittest.TestCase):
    NS, YEARS = 6, [2020, 2030]

    def write(self, base, rel, arr, units="mm"):
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ds = xr.Dataset({"sea_level_change": (("samples", "years", "locations"), arr, {"units": units})},
                        coords={"samples": np.arange(self.NS), "years": self.YEARS, "locations": [1]})
        ds.to_netcdf(path)

    def setup_exp(self, total_offset=0.0, with_parts=True, with_esl=True):
        d = tempfile.mkdtemp()
        exp = os.path.join(d, "exp")
        out = os.path.join(exp, "output-apptainer")
        a = np.random.default_rng(1).random((self.NS, 2, 1)) * 100
        b = np.random.default_rng(2).random((self.NS, 2, 1)) * 100
        self.write(out, "m1/a.nc", a)
        self.write(out, "m2/b.nc", b)
        self.write(out, "facts-total/wf1_global_total.nc", a + b + total_offset)
        script = (service("wf1-global", ["m1/a.nc", "m2/b.nc"], "facts-total/wf1_global_total.nc")
                  + '"--output-x=/mnt/out/m1/a.nc"\n"--output-y=/mnt/out/m2/b.nc"\n')
        os.makedirs(exp, exist_ok=True)
        with open(os.path.join(exp, "experiment-apptainer.sh"), "w") as f:
            f.write(script)
        if with_esl:
            esl_dir = os.path.join(out, "extremesealevel-pointsoverthreshold-wf1")
            os.makedirs(esl_dir)
            xr.Dataset({"allowance_quantiles": (("quantiles",), np.array([0.5, 1.0]))}).to_netcdf(
                os.path.join(esl_dir, "abcd_id12_year2100_extremesl.nc"))
        return rc.Config(workspace=d, experiment="exp", nsamps=self.NS, pyear_start=2020, pyear_end=2030, pyear_step=10)

    def test_consistent_total_passes(self):
        rep = rc.validate_outputs(self.setup_exp(), mock.MagicMock())
        self.assertTrue(rep["ok"])
        self.assertLess(rep["totals"]["wf1-global"]["max_abs_diff_vs_sum_of_items_mm"], 1e-4)

    def test_total_that_is_not_the_sum_of_its_items_fails(self):
        self.assertFalse(rc.validate_outputs(self.setup_exp(total_offset=5.0), mock.MagicMock())["ok"])

    def test_missing_output_fails(self):
        cfg = self.setup_exp()
        os.remove(os.path.join(cfg.out_dir, "m2/b.nc"))
        self.assertFalse(rc.validate_outputs(cfg, mock.MagicMock())["ok"])

    def test_base_year_column_is_accepted_and_aligned(self):
        cfg = self.setup_exp()
        out = cfg.out_dir
        a = np.random.default_rng(3).random((self.NS, 3, 1)) * 100                 # years 2005, 2020, 2030
        ds = xr.Dataset({"sea_level_change": (("samples", "years", "locations"), a, {"units": "mm"})},
                        coords={"samples": np.arange(self.NS), "years": [2005, 2020, 2030], "locations": [1]})
        ds.to_netcdf(os.path.join(out, "m1/a.nc"))
        b = xr.open_dataset(os.path.join(out, "m2/b.nc"))["sea_level_change"].values
        tot = xr.Dataset({"sea_level_change": (("samples", "years", "locations"), a[:, 1:] + b, {"units": "mm"})},
                         coords={"samples": np.arange(self.NS), "years": self.YEARS, "locations": [1]})
        tot.to_netcdf(os.path.join(out, "facts-total/wf1_global_total.nc"))
        cfg.baseyear = 2005
        rep = rc.validate_outputs(cfg, mock.MagicMock())
        self.assertTrue(rep["ok"])
        self.assertTrue(rep["files"]["m1/a.nc"]["extra_baseyear_column"])

    def test_extreme_sea_level_output_is_required_per_workflow(self):
        self.assertFalse(rc.validate_outputs(self.setup_exp(with_esl=False), mock.MagicMock())["ok"])
        self.assertTrue(rc.validate_outputs(self.setup_exp(), mock.MagicMock())["ok"])

    def test_item_ending_early_is_reported_and_total_matches_the_partial_sum(self):
        cfg = self.setup_exp()
        out = cfg.out_dir
        a = xr.open_dataset(os.path.join(out, "m1/a.nc"))["sea_level_change"].values           # years 2020, 2030
        b = xr.open_dataset(os.path.join(out, "m2/b.nc"))["sea_level_change"].values
        xr.Dataset({"sea_level_change": (("samples", "years", "locations"), b[:, :1], {"units": "mm"})},
                   coords={"samples": np.arange(self.NS), "years": [2020], "locations": [1]}).to_netcdf(os.path.join(out, "m2/b2.nc"))
        os.replace(os.path.join(out, "m2/b2.nc"), os.path.join(out, "m2/b.nc"))
        total = a.copy()
        total[:, :1] += b[:, :1]                                                              # what facts-total does: 2030 has only m1
        xr.Dataset({"sea_level_change": (("samples", "years", "locations"), total, {"units": "mm"})},
                   coords={"samples": np.arange(self.NS), "years": self.YEARS, "locations": [1]}).to_netcdf(
            os.path.join(out, "facts-total/wf1_global_total.nc"))
        rep = rc.validate_outputs(cfg, mock.MagicMock())
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["totals"]["wf1-global"]["valid_through_year"], 2020)
        self.assertTrue(any("only valid through 2020" in w and "m2" in w for w in rep["warnings"]))

    def test_wrong_sample_count_fails(self):
        cfg = self.setup_exp()
        cfg.nsamps = self.NS + 1
        self.assertFalse(rc.validate_outputs(cfg, mock.MagicMock())["ok"])


if __name__ == "__main__":
    unittest.main()
