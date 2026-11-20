"""Build the opt-in folded-phase mask over the exact hinted-wide source release."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..__main__ import local_output, save_json
from ..variants import folded_cfo as band
from . import hinted_glrt_build, oracle_start
from .full_v5_check import _sha
from .wide_regional_build import LIBRARY, stock

WORK = Path("/var/tmp/leo-folded-cfo-20261119")


def build(work):
    release = json.loads(oracle_start.ABI.read_bytes())
    base = Path(release["paths"]["hinted"])
    recipe_file = base.parent / "build-receipt.json"
    source = base.parent.parent / "source"
    recipe = json.loads(recipe_file.read_bytes())
    if (
        _sha(base) != release["library_sha256"]["hinted"]
        or _sha(recipe_file) != release["hinted_receipt_sha256"]
        or any(_sha(source / name) != digest for name, digest in recipe["sources"].items())
    ):
        raise ValueError("Pinned hinted-wide release changed")
    work.mkdir(exist_ok=False)
    staged, output, tmp = (work / name for name in ("source", "band", "compiler-tmp"))
    tmp.mkdir()
    shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__"))
    presence = "kernel/private/native_presence"
    changed = {
        "native_glrt.c": band.native,
        f"{presence}/presence.c": band.presence,
        f"{presence}/coarse_fp32.h": band.coarse,
    }
    for name, transform in changed.items():
        p = staged / name
        p.write_text(transform(p.read_text()))
    shutil.copyfile(band.HEADER, staged / presence / band.HEADER.name)
    subprocess.run(
        [
            sys.executable,
            str(staged / "build.py"),
            "--compiler",
            recipe["compiler"],
            "--archiver",
            recipe["archiver"],
            "--fftw-prefix",
            str(stock.HOST_FFTW),
            "--target",
            recipe["target"],
            "--output-dir",
            str(output),
            "--work-dir",
            str(work / "obj"),
        ],
        env=os.environ | {"TMPDIR": str(tmp)},
        check=True,
    )
    new = output / LIBRARY
    new_recipe = output / "build-receipt.json"
    after = json.loads(new_recipe.read_bytes())
    actual_changes = {
        name for name, digest in after["sources"].items() if recipe["sources"].get(name) != digest
    }
    exports = hinted_glrt_build.defined_symbols
    if (
        after["abi_version"] != 1
        or exports(new) != exports(base) | {band.ENTRY}
        or (actual_changes != set(changed) | {f"{presence}/{band.HEADER.name}"})
    ):
        raise ValueError("Mask build changed the pinned ABI or unrelated source")
    save_json(
        work / "build-lock.json",
        dict(
            base=str(base),
            library=str(new),
            source_sha256=_sha(Path(band.__file__)),
            pinned_sha256=_sha(base),
            library_sha256=_sha(new),
            recipe_sha256=_sha(new_recipe),
            source_delta={name: after["sources"][name] for name in sorted(actual_changes)},
            additional_symbol=band.ENTRY,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    build(local_output(parser.parse_args().work))
