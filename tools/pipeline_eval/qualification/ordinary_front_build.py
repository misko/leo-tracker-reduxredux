"""Build an isolated ordinary detector with ordered four-output interpolation."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import ROOT, local_output
from .full_v5_check import _sha

SOURCE = ROOT / "native/adaptive/detector"
HEADER = ROOT / "tools/pipeline_eval/variants/ordinary_front_filter.h"
HOST_FFTW = Path("/tmp/leo-pipeline-native.sfewXn/fftw")
ARM_FFTW = Path("/tmp/leo-frontend-embedded/arm-fftw")
ARM_CONTROL = Path("/tmp/leo-frontend-embedded/arm-ordinary")
CONTROL_BUILD = ROOT / ".build-short-window-native-host/build-receipt.json"


def replace(source, before, after):
    if source.count(before) != 1:
        raise ValueError("Frozen ordinary source does not contain the one expected edit point")
    return source.replace(before, after)


def overlay(source):
    marker = "static double sinc(double x) { return x == 0 ? 1 : sin(TAU*0.5*x)/(TAU*0.5*x); }"
    source = replace(source, marker, f'{marker}\n#include "ordinary_front_filter.h"')
    source = replace(
        source,
        "    double previous_fraction = NAN, weights[16], normalizer = 0;",
        "    leo_fractional_filter filter = {.fraction = NAN};",
    )
    source = replace(
        source,
        "        double complex correlations[2][64] = {{0}};",
        "        if (!integer)\n"
        "            leo_fractional_filter_apply(w->samples,first,stop,start,offset,\n"
        "                &filter,w->input);\n"
        "        double complex correlations[2][64] = {{0}};",
    )
    first = source.index("                double complex received = 0;")
    last = source.index(
        "                /* Omit only the common unit-magnitude frame phase. */", first
    )
    return (
        source[:first]
        + "                double complex received = integer\n"
        + "                    ? w->samples[start+k+integer_offset] : w->input[k];\n"
        + source[last:]
    )


def build(work, target):
    import json

    host = target == "host"
    control = CONTROL_BUILD if host else ARM_CONTROL / "build-receipt.json"
    receipt = json.loads(control.read_bytes())
    if any(_sha(SOURCE / item) != sha for item, sha in receipt["sources"].items()):
        raise ValueError("The native source differs from the measured ordinary control")
    source = work / f"{target}-source"
    shutil.copytree(SOURCE, source, ignore=shutil.ignore_patterns("__pycache__"))
    kernel = source / "kernel/private/native_presence/presence.c"
    kernel.write_text(overlay(kernel.read_text()), encoding="utf-8")
    shutil.copyfile(HEADER, kernel.with_name(HEADER.name))
    args = [
        sys.executable,
        str(source / "build.py"),
        "--compiler",
        receipt["compiler"],
        "--archiver",
        receipt["archiver"],
        "--fftw-prefix",
        str(HOST_FFTW if host else ARM_FFTW),
        "--target",
        receipt["target"],
        "--output-dir",
        str(work / target),
        "--work-dir",
        str(work / f"{target}-build"),
    ]
    subprocess.run(args, check=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("target", choices=("host", "arm"))
    cli.add_argument("--work", required=True, type=Path)
    args = cli.parse_args()
    build(local_output(args.work), args.target)
