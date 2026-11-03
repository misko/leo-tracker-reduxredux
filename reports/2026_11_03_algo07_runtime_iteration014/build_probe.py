"""Build a storage-isolated native runtime with only fractional weight reuse."""

import argparse
import ast
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from stage_native_glrt_runtime import digest, verify, verify_files  # noqa: E402

MEMBER = "src/leo/analysis/starlink/fast_scan_fractional.py"
ORIGINAL = "ae177873aee33dc4efad0e7737fc0cd8f6785dfd9b2c9e698644d3d86b00e3f7"


def build(base, pin, output):
    base, output = base.resolve(strict=True), output.resolve()
    if output.exists() or not output.is_relative_to("/srv/bulk/leo/research"):
        raise ValueError("New private research output required")
    manifest = verify(base, pin)
    if manifest["files_sha256"][MEMBER] != ORIGINAL:
        raise ValueError("Untested fractional interpolation baseline")
    before, after = (ast.parse(p.read_text()).body for p in (base / MEMBER, ROOT / MEMBER))
    for old, new in zip(before, after, strict=True):
        if getattr(old, "name", None) != "fractional_take" and ast.dump(old) != ast.dump(new):
            raise ValueError("Unexpected changes outside fractional_take")
    output.mkdir(parents=True)
    for name in manifest["files_sha256"]:
        target = output / name
        target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(base / name, target)
    shutil.copyfile(ROOT / MEMBER, output / MEMBER)
    inventory = {n: digest(output / n) for n in manifest["files_sha256"]}
    changes = [n for n in inventory if inventory[n] != manifest["files_sha256"][n]]
    if changes != [MEMBER]:
        raise ValueError("Expected only one changed module")
    verify(base, pin)
    verify_files(output, inventory)
    receipt = dict(base=str(base), base_pin=pin, candidate=str(output), changes=changes,
                   files_sha256=inventory, builder_sha256=digest(Path(__file__)),
                   original_module_sha256=ORIGINAL, candidate_module_sha256=inventory[MEMBER],
                   production_modified=False, qualification="research only")
    (output / "fractional-probe.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return dict(candidate=str(output), changes=changes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.base, args.pin, args.output)))
