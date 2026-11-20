"""Build width-only prepared-fractional wave8 peers using the reviewed release recipe."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import local_output, save_json
from ..variants import fractional_runtime_overlay, ordinary_prepared, wide_regional
from . import ordinary_front_build as stock
from .full_v5_check import _sha

ROOT = Path("/srv/bulk/leo-dev/20261119-wide-regional")
FROZEN = Path("/tmp/ordinary-fractional-runtime-20261119/host-fractional_runtime")
FROZEN_SHA256 = "e545c28554c9db50fe5aece28e7c8ce6ab2b2504db13ab946fbff0f0a190fe0d"
LIBRARY = "libleo-adaptive-detector.so"


def build(work, mode, arch):
    host = arch == "host"
    receipt_path = stock.CONTROL_BUILD if host else stock.ARM_CONTROL / "build-receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    if any(_sha(stock.SOURCE / item) != sha for item, sha in receipt["sources"].items()):
        raise ValueError("The native source differs from the measured ordinary release")
    target = work / (mode if host else f"arm-{mode}")
    source = target.with_name(target.name + "-source")
    shutil.copytree(stock.SOURCE, source, ignore=shutil.ignore_patterns("__pycache__"))
    detector = source / "native_glrt.c"
    native = ordinary_prepared.retain_short_window_preparation(detector.read_text())
    kernel = source / "kernel/private/native_presence/presence.c"
    presence = fractional_runtime_overlay.overlay(kernel.read_text())
    shutil.copyfile(fractional_runtime_overlay.HEADER, kernel.with_name("fractional_runtime.h"))
    if mode == "wide":
        native = wide_regional.native_glrt(native)
        presence = wide_regional.presence(presence)
        region = kernel.with_name("coarse_fp32.h")
        region.write_text(wide_regional.coarse(region.read_text()))
        shutil.copyfile(wide_regional.HEADER, region.with_name(wide_regional.HEADER.name))
        full = source / "kernel/private/full_search.c"
        full.write_text(wide_regional.full_search(full.read_text()))
        full_h = full.with_suffix(".h")
        full_h.write_text(
            wide_regional.replace(full_h.read_text(), "coarse_cfo_hz[11]", "*coarse_cfo_hz")
        )
    detector.write_text(native)
    kernel.write_text(presence)
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
            str(target),
            "--work-dir",
            str(target.with_name(target.name + "-build")),
        ],
        check=True,
    )
    built = json.loads((target / "build-receipt.json").read_bytes())
    library = target / LIBRARY
    if _sha(library) != built["outputs"][LIBRARY] or built["abi_version"] != 1:
        raise ValueError("Unexpected native release output")
    if host and mode == "control" and _sha(FROZEN / LIBRARY) != FROZEN_SHA256:
        raise ValueError("Historical prepared-fractional control is unavailable")
    save_json(
        target / "width-receipt.json",
        dict(
            abi_version=built["abi_version"],
            path=str(library),
            sha256=_sha(library),
            base_prepared_control_sha256=FROZEN_SHA256,
            exact_historical_binary=host and _sha(library) == FROZEN_SHA256,
            ordinary_cfo_band_hz=[-400_000, 400_000],
            wide_10msps_short=mode == "wide",
            wide_cfo_band_hz=[-800_000, 800_000] if mode == "wide" else None,
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("control", "wide"))
    cli.add_argument("--arch", choices=("host", "arm"), default="host")
    cli.add_argument("--work", default=ROOT, type=Path)
    args = cli.parse_args()
    build(local_output(args.work), args.mode, args.arch)
