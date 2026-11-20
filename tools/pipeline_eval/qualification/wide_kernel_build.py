"""Build one ABI-compatible adjacent-fractional template peer of the released wide detector."""

import argparse
import json
import os
import shutil
import subprocess
import sys

from ..__main__ import local_output, save_json
from ..variants import wide_kernel
from . import ordinary_front_build, wide_regional_build
from .full_v5_check import _sha
from .scout_radius_build import PIN

LIBRARY = wide_regional_build.LIBRARY
ORIGINAL = wide_regional_build.ROOT / "wide"
PATCHED = "kernel/private/native_presence/presence.c"


def exports(path):
    symbols = subprocess.check_output(["nm", "-D", "--defined-only", str(path)], text=True)
    return {line.split()[-1] for line in symbols.splitlines()}


def build(work, trace=False):
    original_source = ORIGINAL.with_name("wide-source")
    baseline = ORIGINAL / LIBRARY
    receipt = json.loads((ORIGINAL / "build-receipt.json").read_bytes())
    if (
        _sha(baseline) != PIN
        or receipt["outputs"][LIBRARY] != PIN
        or any(_sha(original_source / f) != sha for f, sha in receipt["sources"].items())
    ):
        raise ValueError("canonical wide build or its sources differ from the frozen artifact")
    source, target, temp = (work / n for n in ("source", "candidate", "compiler-temp"))
    shutil.copytree(original_source, source, ignore=shutil.ignore_patterns("__pycache__"))
    kernel = source / PATCHED
    kernel.write_text(wide_kernel.overlay(kernel.read_text(), trace=trace))
    shutil.copyfile(wide_kernel.HEADER, kernel.with_name(wide_kernel.HEADER.name))
    temp.mkdir(exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(ordinary_front_build.HOST_FFTW),
            "--target",
            receipt["target"],
            "--output-dir",
            str(target),
            "--work-dir",
            str(work / "objects"),
        ],
        env={**os.environ, "TMPDIR": str(temp)},
        check=True,
    )
    candidate = target / LIBRARY
    built = json.loads((target / "build-receipt.json").read_bytes())
    additional = {"leo_wide_kernel_fractional_counts"} if trace else set()
    changed = {f for f, sha in receipt["sources"].items() if built["sources"][f] != sha}
    if (
        _sha(candidate) != built["outputs"][LIBRARY]
        or built["abi_version"] != receipt["abi_version"]
        or exports(candidate) != exports(baseline) | additional
        or changed != {PATCHED}
    ):
        raise ValueError("candidate differed outside the authorized native interpolation leaf")
    save_json(
        work / "release.json",
        dict(
            control=dict(path=str(baseline), sha256=PIN),
            candidate=dict(path=str(candidate), sha256=_sha(candidate)),
            trace=trace,
            abi_version=built["abi_version"],
            build_receipt_sha256=_sha(target / "build-receipt.json"),
            interpolation_header_sha256=_sha(wide_kernel.HEADER),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", required=True, type=local_output)
    p.add_argument("--trace", action="store_true")
    args = p.parse_args()
    build(args.work, args.trace)
