"""Build an ABI-compatible union of the calibrated two-lane epoch proposals."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import save_json
from ..variants import paired_epoch_overlay as overlay
from . import wide_regional_build as wide
from .full_v5_check import _sha

BASE_SHA256 = "db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66"
WORK = Path("/srv/bulk/leo-dev/20261119-paired-epochs")
REPORT = Path(__file__).resolve().parents[3] / (
    "reports/2026_11_19_receiver_screening/detector-origins/paired-epochs"
)


def build(work):
    original = wide.ROOT / "wide"
    staged = wide.ROOT / "wide-source"
    library = original / wide.LIBRARY
    receipt_path = original / "build-receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    if (
        _sha(library) != BASE_SHA256
        or receipt["outputs"][wide.LIBRARY] != BASE_SHA256
        or any(_sha(staged / name) != digest for name, digest in receipt["sources"].items())
    ):
        raise ValueError("staged expanded-frequency release differs from its measured provenance")
    work.mkdir(parents=True, exist_ok=False)
    scratch = work / "compiler-tmp"
    scratch.mkdir()
    source, output = work / "source", work / "out"
    shutil.copytree(staged, source, ignore=shutil.ignore_patterns("__pycache__"))
    detector = source / "native_glrt.c"
    detector.write_text(overlay.overlay(detector.read_text()))
    shutil.copyfile(overlay.HEADER, source / overlay.HEADER.name)
    subprocess.run(
        [
            sys.executable,
            str(source / "build.py"),
            "--compiler",
            receipt["compiler"],
            "--archiver",
            receipt["archiver"],
            "--fftw-prefix",
            str(wide.stock.HOST_FFTW),
            "--target",
            receipt["target"],
            "--output-dir",
            str(output),
            "--work-dir",
            str(work / "build"),
        ],
        env=os.environ | {"TMPDIR": str(scratch)},
        check=True,
    )
    produced = output / wide.LIBRARY
    after = json.loads((output / "build-receipt.json").read_bytes())
    sha = _sha(produced)
    if after["abi_version"] != 1 or after["outputs"][wide.LIBRARY] != sha:
        raise ValueError("unexpected paired-epoch release")
    changed = {name: v for name, v in after["sources"].items() if receipt["sources"].get(name) != v}
    if set(receipt["sources"]) - set(after["sources"]) or not set(changed) <= {
        "native_glrt.c",
        overlay.HEADER.name,
    }:
        raise ValueError("compile changed unrelated source")
    row = dict(
        library=str(produced),
        sha256=sha,
        wide_library=str(library),
        wide_sha256=BASE_SHA256,
        abi_version=after["abi_version"],
        original_build_receipt_sha256=_sha(receipt_path),
        paired_build_receipt_sha256=_sha(output / "build-receipt.json"),
        overlay_native_sha256=_sha(detector),
        overlay_header_sha256=_sha(overlay.HEADER),
        source_delta=changed,
        activation="10MS/s dual-RX 20 ms short-window API",
    )
    save_json(REPORT / "build.json", row)
    print(row, flush=True)
    return row


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, default=WORK)
    build(cli.parse_args().work)
