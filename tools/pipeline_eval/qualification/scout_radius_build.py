"""Build the two-sample radius release from the verified canonical wide source."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import local_output, save_json
from ..variants import scout_radius
from . import ordinary_front_build, scout_budget_build, wide_regional_build
from .full_v5_check import _sha

ROOT = Path("/srv/bulk/leo-dev/20261119-scout-radius")
LIBRARY = wide_regional_build.LIBRARY
PIN = scout_budget_build.PIN


def build(work):
    original = wide_regional_build.ROOT / "wide"
    source_original = original.with_name("wide-source")
    receipt = json.loads((original / "build-receipt.json").read_bytes())
    if (
        receipt["outputs"][LIBRARY] != PIN
        or _sha(original / LIBRARY) != PIN
        or any(_sha(source_original / f) != d for f, d in receipt["sources"].items())
    ):
        raise ValueError("Pinned four-center wide source or release was modified")
    source, control, radius = (work / n for n in ("radius2-source", "control", "radius2"))
    shutil.copytree(original, control)
    shutil.copytree(source_original, source, ignore=shutil.ignore_patterns("__pycache__"))
    native = source / "native_glrt.c"
    native.write_text(scout_radius.overlay(native.read_text()))
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
            receipt["target"],
            "--output-dir",
            str(radius),
            "--work-dir",
            str(work / "radius2-build"),
        ],
        env={**os.environ, "TMPDIR": str(temp)},
        check=True,
    )
    built = json.loads((radius / "build-receipt.json").read_bytes())
    trial = _sha(radius / LIBRARY)
    if not (
        trial == built["outputs"][LIBRARY]
        and _sha(control / LIBRARY) == PIN
        and built["abi_version"] == receipt["abi_version"] == 1
    ):
        raise ValueError("Radius2 or its four-center canonical control does not verify")
    if {k for k in receipt["sources"] if receipt["sources"][k] != built["sources"][k]} != {
        "native_glrt.c"
    }:
        raise ValueError("Radius2 changed more than the native support loop")

    def exports(path):
        raw = subprocess.check_output(["nm", "-D", "--defined-only", str(path)], text=True)
        return [line.split()[-1] for line in raw.splitlines()]

    if exports(control / LIBRARY) != exports(radius / LIBRARY):
        raise ValueError("Radius2 changed public native export names")
    save_json(
        work / "release.json",
        dict(
            abi_version=1,
            paths={"control": str(control / LIBRARY), "radius2": str(radius / LIBRARY)},
            library_sha256={"control": PIN, "radius2": trial},
            policy="four centers, +/-2 support on 10 MS/s wide fractional dual-RX short windows",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=ROOT)
    work_dir = local_output(parser.parse_args().work)
    work_dir.mkdir(exist_ok=True, parents=True)
    build(work_dir)
