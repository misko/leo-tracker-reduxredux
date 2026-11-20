"""Build the original ordinary wave8 code with adjacent coarse epoch triplets."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import ROOT, local_output
from . import ordinary_front_build as stock
from .full_v5_check import _sha

HEADER = ROOT / "tools/pipeline_eval/variants/coarse_glrt_triplet.h"


def overlay(source):
    source = stock.replace(
        source,
        "static void coarse_fp32_templates",
        '#include "coarse_glrt_triplet.h"\n\nstatic void coarse_fp32_templates',
    )
    marker = "/* Evaluate a previously unsearched epoch around a sparse coarse proposal."
    prepare = """/* Fall back if any member cannot use the ordinary positive denominator. */
static int coarse_fp32_triplet(leo_presence_workspace *w, int symbol,
    ptrdiff_t position, ptrdiff_t epoch, int taps)
{
    float inverse[3];
    for (int i=0;i<3;++i) {
        double received=w->prefix[position+i+taps]-w->prefix[position+i];
        if (received<0) received=0;
        double denominator=sqrt(w->float_reference_energy[symbol]*received);
        if (!(denominator>0)) return 0;
        inverse[i]=(float)(1.0/denominator);
        if (!isfinite(inverse[i])) return 0;
    }
    leo_coarse_triplet(w->float_samples+2*position,
        w->float_reference_real+symbol*45*12, w->float_reference_imag+symbol*45*12,
        taps,inverse,w->float_accumulated+12*epoch);
    ++w->support[epoch];++w->support[epoch+1];++w->support[epoch+2];
    return 1;
}

"""
    source = stock.replace(source, marker, prepare + marker)
    line = "                if (epoch>=valid) continue;"
    replacement = """                if (epoch>=valid) continue;
                if (active+2<w->regional_count && epoch+2<valid &&
                    w->regional_epochs[active+1]==epoch+1 &&
                    w->regional_epochs[active+2]==epoch+2 &&
                    coarse_fp32_triplet(w,symbol,base+epoch,epoch,taps)) {
                    active+=2;
                    continue;
                }"""
    return stock.replace(source, line, replacement)


def build(work, target):
    host = target == "host"
    control = stock.CONTROL_BUILD if host else stock.ARM_CONTROL / "build-receipt.json"
    receipt = json.loads(control.read_bytes())
    if any(_sha(stock.SOURCE / item) != sha for item, sha in receipt["sources"].items()):
        raise ValueError("The native source differs from the measured ordinary control")
    source = work / f"{target}-source"
    shutil.copytree(stock.SOURCE, source, ignore=shutil.ignore_patterns("__pycache__"))
    coarse = source / "kernel/private/native_presence/coarse_fp32.h"
    coarse.write_text(overlay(coarse.read_text()), encoding="utf-8")
    shutil.copyfile(HEADER, coarse.with_name(HEADER.name))
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(stock.HOST_FFTW if host else stock.ARM_FFTW),
            "--target",
            receipt["target"],
            "--output-dir",
            str(work / target),
            "--work-dir",
            str(work / f"{target}-build"),
        ],
        check=True,
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("target", choices=("host", "arm"))
    cli.add_argument("--work", required=True, type=Path)
    args = cli.parse_args()
    build(local_output(args.work), args.target)
