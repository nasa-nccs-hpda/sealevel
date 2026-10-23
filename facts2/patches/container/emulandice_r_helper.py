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

    # PATCH (sealevel repo): load the patched main.R (bound over the package source file in the image) into the installed package's
    # namespace before calling main(). The only change in it is a vectorised temperature lookup; see facts2/patches/README.md.
    r_cmd = (
        "library(emulandice);ns<-asNamespace('emulandice');unlockBinding('main',ns);unlockBinding('e',ns);"
        "for(x in parse('/opt/emulandice/modules/emulandice/shared/emulandice/R/main.R')) eval(x, envir=ns);"
        f"get('main',ns)('decades', dataset='{emulandice_dataset}', N_FACTS={nsamps}, outdir='{outdir}', ice_sources=c('{icesource}'))"
    )

    subprocess.run(
        ["R", "-q", "--no-save", "-e", r_cmd],
        shell=False,
        check=True,
    )
    logger.debug("R emulandice subprocess complete")
