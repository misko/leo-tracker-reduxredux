"""Compile the 16-center release from the authenticated four-center wide build."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import local_output, save_json
from ..variants import scout_budget
from . import ordinary_front_build, wide_regional_build
from .full_v5_check import _sha

ROOT = Path("/srv/bulk/leo-dev/20261119-scout-budget")
LIBRARY = wide_regional_build.LIBRARY
PIN = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"


def build(work, arch):
    host = arch == "host"
    name = "wide" if host else "arm-wide"
    base = wide_regional_build.ROOT / name
    original = base.with_name(name + "-source")
    receipt = json.loads((base / "build-receipt.json").read_bytes())
    current = _sha(base / LIBRARY)
    if (
        current != receipt["outputs"][LIBRARY]
        or (host and current != PIN)
        or any(_sha(original / f) != d for f, d in receipt["sources"].items())
    ):
        raise ValueError("Pinned four-center release or its reviewed source changed")
    prefix = "" if host else "arm-"
    control, target = (work / f"{prefix}{name}" for name in ("control", "scout16"))
    shutil.copytree(base, control)
    source = target.with_name(target.name + "-source")
    shutil.copytree(original, source, ignore=shutil.ignore_patterns("__pycache__"))
    scout_budget.apply(source)
    temp = work / "compiler-temp"
    temp.mkdir(exist_ok=True)
    fftw = ordinary_front_build.HOST_FFTW if host else ordinary_front_build.ARM_FFTW
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(fftw),
            "--target",
            receipt["target"],
            "--output-dir",
            str(target),
            "--work-dir",
            str(target.with_name(target.name + "-build")),
        ],
        env={**os.environ, "TMPDIR": str(temp)},
        check=True,
    )
    built = json.loads((target / "build-receipt.json").read_bytes())
    trial = _sha(target / LIBRARY)
    if not (
        trial == built["outputs"][LIBRARY]
        and current == _sha(control / LIBRARY)
        and built["abi_version"] == receipt["abi_version"] == 1
    ):
        raise ValueError("The 16-center or pinned-off artifact does not verify")

    def symbols(path):
        out = subprocess.check_output(["nm", "-D", "--defined-only", str(path)], text=True)
        return [line.split()[-1] for line in out.splitlines()]

    if symbols(control / LIBRARY) != symbols(target / LIBRARY):
        raise ValueError("The 16-center release changed public exported ABI names")
    save_json(
        work / f"{arch}-release.json",
        dict(
            abi_version=1,
            paths={"control": str(control / LIBRARY), "scout16": str(target / LIBRARY)},
            library_sha256={"control": current, "scout16": trial},
            policy="16 distinct scout centers for wide 10 MS/s fractional short-window only",
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", default=ROOT, type=Path)
    parser.add_argument("--arch", choices=("host", "arm"), default="host")
    config = parser.parse_args()
    work = local_output(config.work)
    work.mkdir(exist_ok=True, parents=True)
    build(work, config.arch)
