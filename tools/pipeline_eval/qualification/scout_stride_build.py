"""Compile the CFO-stride release from the pinned prepared-fractional wide source."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import local_output, save_json
from ..variants import scout_stride
from . import ordinary_front_build, scout_radius_build, wide_regional_build
from .full_v5_check import _sha

ROOT = Path("/var/tmp/leo-scout-stride-20261119")
LIBRARY = wide_regional_build.LIBRARY
PIN = scout_radius_build.PIN


def build(work):
    original = wide_regional_build.ROOT / "wide"
    source_original = original.with_name("wide-source")
    receipt = json.loads((original / "build-receipt.json").read_bytes())
    if (
        _sha(original / LIBRARY) != PIN
        or receipt["outputs"][LIBRARY] != PIN
        or any(_sha(source_original / f) != d for f, d in receipt["sources"].items())
    ):
        raise ValueError("Pinned release or source changed")
    source, control, target = (work / name for name in ("stride-source", "control", "stride"))
    shutil.copytree(original, control)
    shutil.copytree(source_original, source, ignore=shutil.ignore_patterns("__pycache__"))
    scout_stride.apply(source)
    temp = work / "compiler-temp"
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
            "host",
            "--output-dir",
            str(target),
            "--work-dir",
            str(work / "stride-build"),
        ],
        env={**os.environ, "TMPDIR": str(temp)},
        check=True,
    )
    built = json.loads((target / "build-receipt.json").read_bytes())
    trial = _sha(target / LIBRARY)
    if not (
        trial == built["outputs"][LIBRARY]
        and _sha(control / LIBRARY) == PIN
        and receipt["abi_version"] == built["abi_version"] == 1
    ):
        raise ValueError("CFO-stride or its off artifact does not verify")

    def names(path):
        s = subprocess.check_output(["nm", "-D", "--defined-only", str(path)], text=True)
        return [line.split()[-1] for line in s.splitlines()]

    if names(control / LIBRARY) != names(target / LIBRARY):
        raise ValueError("CFO-stride changed public exported names")
    save_json(
        work / "release.json",
        dict(
            abi_version=1,
            paths={"control": str(control / LIBRARY), "stride": str(target / LIBRARY)},
            library_sha256={"control": PIN, "stride": trial},
            method="even coarse CFOs and two adjacent repairs around one winner per scout basin",
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=ROOT)
    work = local_output(p.parse_args().work)
    work.mkdir(mode=0o755, exist_ok=True, parents=True)
    build(work)
