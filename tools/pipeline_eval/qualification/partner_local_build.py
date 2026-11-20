"""Build the local partner entry against the sealed active-grid wide detector."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from ..variants import partner_local
from . import native_pruning_build as parent
from .full_v5_check import _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/antenna-confirmation/partner-local"
PARENT = Path("/var/tmp/leo-native-pruning-20261119/build")
DETECTOR = "libleo-adaptive-detector.so"


def build(work):
    seal = parent.REPORT / "result-lock.json"
    files = whole_iq.read(seal)["files"]
    bound = whole_iq.read(whole_iq.checked(PARENT / "build.json", files["build.json"]))
    receipt = whole_iq.checked(
        PARENT / "detector/build-receipt.json", bound["detector_build_sha256"]
    )
    reference = whole_iq.read(receipt)
    base = whole_iq.checked(PARENT / "detector" / DETECTOR, reference["outputs"][DETECTOR])
    for name, digest in reference["sources"].items():
        whole_iq.checked(PARENT / "source" / name, digest)
    copy = work / "source"
    shutil.copytree(PARENT / "source", copy, ignore=shutil.ignore_patterns("__pycache__"))
    kernel = copy / "native_glrt.c"
    kernel.write_text(kernel.read_text() + '\n#include "partner_local.h"\n')
    header = Path(partner_local.__file__).with_suffix(".h")
    shutil.copyfile(header, copy / header.name)
    temporary = work / "compiler_tmp"
    temporary.mkdir()
    tool = {
        k: whole_iq.checked(Path(reference[k]), reference[k + "_sha256"])
        for k in ("compiler", "archiver")
    }
    fftw = parent.combined.lane.hotpath.ordinary_front_build.HOST_FFTW
    whole_iq.checked(fftw / "lib/libfftw3f.a", reference["fftw_float_archive_sha256"])
    whole_iq.checked(fftw / "include/fftw3.h", reference["fftw_header_sha256"])
    command = [
        sys.executable,
        str(copy / "build.py"),
        "--compiler",
        str(tool["compiler"]),
        "--archiver",
        str(tool["archiver"]),
        "--fftw-prefix",
        str(fftw),
        "--target",
        "host",
        "--output-dir",
        str(work / "detector"),
        "--work-dir",
        str(work / "objects"),
    ]
    subprocess.run(command, env=os.environ | {"TMPDIR": str(temporary)}, check=True, timeout=65)
    built_path = work / "detector/build-receipt.json"
    built = whole_iq.read(built_path)
    expected = reference["sources"] | {"native_glrt.c": _sha(kernel), header.name: _sha(header)}
    if built["sources"] != expected or built["abi_version"] != reference["abi_version"]:
        raise ValueError("build changed a source outside the partner entry")
    candidate = whole_iq.checked(work / "detector" / DETECTOR, built["outputs"][DETECTOR])
    exports = parent.combined.lane.exports
    if exports(candidate) != exports(base) | {partner_local.ENTRY}:
        raise ValueError("existing native exports changed")
    save_json(
        work / "build.json",
        dict(
            parent_library={"path": str(base), "sha256": _sha(base)},
            candidate={"path": str(candidate), "sha256": _sha(candidate)},
            parent_build_sha256=_sha(receipt),
            detector_build_sha256=_sha(built_path),
            parent_result_lock_sha256=_sha(seal),
            sources={str(p.relative_to(ROOT)): _sha(p) for p in (Path(__file__), header)},
            changed={n: expected[n] for n in ("native_glrt.c", header.name)},
            new_symbol=partner_local.ENTRY,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    build(parser.parse_args().work)
