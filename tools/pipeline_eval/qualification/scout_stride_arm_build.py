"""Cross-build the byte-frozen full and strided x86 release source trees."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import save_json
from . import ordinary_front_build, scout_stride_build, wide_regional_build
from .full_v5_check import _sha

WORK = Path("/var/tmp/leo-scout-stride-arm-20261119")
MODES = ("control", "stride")
ARM_PIN = "ddc058cb82a223e70591d38ce2e904c073476cd994898e7369a845bfbcd218af"
LIBRARY = scout_stride_build.LIBRARY
CLI = "leo-native-glrt-short-window"


def build(work):
    work.mkdir(exist_ok=False, parents=True)
    stock = wide_regional_build.ROOT / "arm-wide"
    arm = json.loads((stock / "build-receipt.json").read_bytes())
    if not _sha(stock / LIBRARY) == arm["outputs"][LIBRARY] == ARM_PIN:
        raise ValueError("Pinned off ARM release changed")
    temp = work / "compiler-temp"
    temp.mkdir()
    receipts, symbols = {}, {}
    for mode in MODES:
        host = scout_stride_build.ROOT / mode
        original = (
            wide_regional_build.ROOT / "wide-source"
            if mode == "control"
            else scout_stride_build.ROOT / "stride-source"
        )
        reviewed = json.loads((host / "build-receipt.json").read_bytes())
        if any(_sha(original / f) != digest for f, digest in reviewed["sources"].items()):
            raise ValueError("The frozen detector input source differs from its host receipt")
        if _sha(host / LIBRARY) != reviewed["outputs"][LIBRARY]:
            raise ValueError("The paired host library differs from its frozen source receipt")
        source, target = (work / f"arm-{mode}{suffix}" for suffix in ("-source", ""))
        shutil.copytree(original, source, ignore=shutil.ignore_patterns("__pycache__"))
        subprocess.run(
            [
                sys.executable,
                str(source / "build.py"),
                "--compiler",
                arm["compiler"],
                "--archiver",
                arm["archiver"],
                "--fftw-prefix",
                str(ordinary_front_build.ARM_FFTW),
                "--target",
                arm["target"],
                "--output-dir",
                str(target),
                "--work-dir",
                str(work / f"{mode}-build"),
            ],
            env={**os.environ, "TMPDIR": str(temp)},
            check=True,
        )
        built = json.loads((target / "build-receipt.json").read_bytes())
        if built["sources"] != reviewed["sources"] or built["abi_version"] != 1:
            raise ValueError("Cross compile changed the detector source or ABI")
        off_names = (LIBRARY, CLI)
        if mode == "control" and any(_sha(target / f) != arm["outputs"][f] for f in off_names):
            raise ValueError("Cross-built ARM control differs from the pinned binaries")
        abi = subprocess.check_output(["readelf", "-h", str(target / LIBRARY)], text=True)
        if "hard-float ABI" not in abi or "ARM" not in abi:
            raise ValueError("Cross-built library differs from Cortex-A9 hard-float ABI")
        exports = subprocess.check_output(
            ["nm", "-D", "--defined-only", str(target / LIBRARY)], text=True
        )
        symbols[mode] = [line.split()[-1] for line in exports.splitlines()]
        receipts[mode] = dict(
            abi_version=1,
            library_sha256=_sha(target / LIBRARY),
            cli_sha256=_sha(target / CLI),
            host_library_sha256=_sha(host / LIBRARY),
            source_receipt_sha256=_sha(target / "build-receipt.json"),
        )
    if symbols["control"] != symbols["stride"]:
        raise ValueError("Cross-built variants have different ABI exports")
    save_json(
        work / "release.json",
        dict(
            builds=receipts,
            sysroot=str(Path(arm["fftw_double_library"]).parents[2]),
            arm_wide_library_sha256=ARM_PIN,
            target=arm["target"],
            abi_exports=symbols["control"],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=WORK)
    build(p.parse_args().work)
