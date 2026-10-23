"""Helpers to ease the relationship between R and Python."""

import logging
import subprocess
import shlex


logger = logging.getLogger(__name__)


def run_emulandice(
    *,
    emulandice_dataset: str,
    nsamps: int | str,
    icesource: str,
    outdir: str = "results",
) -> None:
    """
    Runs emulandice as a subprocess via R. Requires `emulandice` to be installed and available to R. R must be available in PATH.

    This only runs on POSIX systems.
    """
    # Safety to ensure nsamps can be interpreted as int.
    nsamps = str(int(nsamps))

    # Sanitize user inputs.
    emulandice_dataset = shlex.quote(emulandice_dataset)
    nsamps = shlex.quote(nsamps)
    icesource = shlex.quote(icesource)
    outdir = shlex.quote(outdir)

    r_cmd = f"library(emulandice);emulandice::main('decades', dataset='{emulandice_dataset}', N_FACTS={nsamps}, outdir='{outdir}', ice_sources=c('{icesource}'))"

    subprocess.run(
        ["R", "-q", "--no-save", "-e", r_cmd],
        shell=False,
        check=True,
    )
    logger.debug("R emulandice subprocess complete")
