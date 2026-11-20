"""Create an opt-in native hint ABI over the frozen four-center wide release."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import local_output, save_json
from ..variants import hinted_glrt as hint
from . import paired_epoch_build
from . import wide_regional_build as wide
from .full_v5_check import _sha


def defined_symbols(path):
    symbols = subprocess.check_output(["nm", "-D", "--defined-only", str(path)], text=True)
    return {line.split()[-1] for line in symbols.splitlines()}


def build(work):
    stock = wide.ROOT / "wide"
    staged = wide.ROOT / "wide-source"
    recipe = stock / "build-receipt.json"
    original = json.loads(recipe.read_bytes())
    library = stock / wide.LIBRARY
    if (
        _sha(library) != paired_epoch_build.BASE_SHA256
        or original["outputs"][wide.LIBRARY] != paired_epoch_build.BASE_SHA256
        or any(_sha(staged / name) != sha for name, sha in original["sources"].items())
    ):
        raise ValueError("wide ABI base or its declared source differs from the frozen release")
    work.mkdir(parents=True, exist_ok=False)
    scratch, staged_control, output = work / "compiler-tmp", work / "source", work / "hinted"
    scratch.mkdir()
    shutil.copytree(staged, staged_control, ignore=shutil.ignore_patterns("__pycache__"))
    detector = staged_control / "native_glrt.c"
    detector.write_text(hint.graft(detector.read_text()))
    shutil.copyfile(hint.HEADER, staged_control / hint.HEADER.name)
    subprocess.run(
        [
            sys.executable,
            str(staged_control / "build.py"),
            "--compiler",
            original["compiler"],
            "--archiver",
            original["archiver"],
            "--fftw-prefix",
            str(wide.stock.HOST_FFTW),
            "--target",
            original["target"],
            "--output-dir",
            str(output),
            "--work-dir",
            str(work / "build"),
        ],
        env=os.environ | {"TMPDIR": str(scratch)},
        check=True,
    )
    produced = output / wide.LIBRARY
    built = json.loads((output / "build-receipt.json").read_bytes())
    initial = defined_symbols(library)
    actual = defined_symbols(produced)
    changed = {
        name for name, sha in built["sources"].items() if original["sources"].get(name) != sha
    }
    if (
        built["abi_version"] != 1
        or _sha(produced) != built["outputs"][wide.LIBRARY]
        or actual != initial | {hint.ENTRY}
        or changed != {"native_glrt.c", hint.HEADER.name}
    ):
        raise ValueError("hint build changed more than the opt-in entry and its private helper")
    save_json(
        work / "build-lock.json",
        dict(
            paths={"stock": str(library), "hinted": str(produced)},
            library_sha256={"stock": _sha(library), "hinted": _sha(produced)},
            sources={str(p): _sha(p) for p in (Path(__file__), Path(hint.__file__), hint.HEADER)},
            stock_receipt_sha256=_sha(recipe),
            hinted_receipt_sha256=_sha(output / "build-receipt.json"),
            additional_export=hint.ENTRY,
            source_delta={name: built["sources"][name] for name in sorted(changed)},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    build(local_output(parser.parse_args().work))
