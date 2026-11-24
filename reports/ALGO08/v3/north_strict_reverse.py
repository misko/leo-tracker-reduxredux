"""Run the reverse order of the sealed North packed-reader comparison."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from reports.ALGO08.v3.north_strict_read import HERE, frozen, resident_packed, score
from aperture_trial import write
from empty_bootstrap import checked


MERGED = "06faca9f663acbf752aa41a0675378bbe48ced9c"
FIRST = Path("/dev/shm/leo-v3-north-strict-result01")
FIRST_RECEIPT = "08e0a349dcae2f9871417c2224ccdc40edbf5ab7e5c119216d7297adac22a3a2"


def sealed_conversion(sealed, original):
    content = checked(original / "conversion.json", sealed["sources"]["conversion.json"])
    conversion = json.loads(content)
    config = conversion["request"]
    if (conversion != sealed["conversion"] or not conversion["independent_check"] or
            Path(config["map"]) != original / "conversion/map.json" or Path(config["codec"]) != original / "packing.so"):
        raise ValueError("Use the complete independently verified original derivative")
    return content, conversion


def admitted_derivative(conversion):
    from ci16_packing import Packing
    from north_held_anchor_pair import tmpfs
    from packed_combined_input import member_map
    from seekable_eight_raw import PREFIX
    from seekable_member import open_member

    request = conversion["request"]
    mapping, binary = Path(request["map"]), Path(request["codec"])
    tmpfs(mapping)
    tmpfs(binary)
    codec_pin, entries = member_map(checked(mapping, request["map_sha256"].removeprefix("sha256:")), strict_eight=True)
    checked(binary, codec_pin.removeprefix("sha256:"))
    if codec_pin != "sha256:" + conversion["codec"]["binary_sha256"]:
        raise ValueError("Packed codec differs from the independently checked conversion")
    bindings = {(row["binding"]["manifest_sha256"], row["binding"]["chunk_index"]): row
                for row in conversion["sections"]}
    if len(entries) != len(bindings) or len(entries) != 19:
        raise ValueError("Expected all nineteen original packed members")
    codec = Packing(binary)
    dirs = [mapping.parent / name for name, _ in entries.values()]
    if any(path.resolve(strict=True) != path for path in dirs):
        raise ValueError("Packed member must resolve inside the validated derivative")
    for path in dirs:
        tmpfs(path)

    def resident():
        return resident_packed(mapping.parent, dirs, codec)

    before = resident()
    for key, (name, pin) in entries.items():
        saved = bindings[key]
        if (name, pin) != (saved["binding"]["directory"], saved["binding"]["seek_sha256"]):
            raise ValueError("Member root differs from the independently checked conversion")
        with open_member(mapping.parent / name, pin, codec=codec, prefix_samples=PREFIX) as reader:
            if (reader.manifest_sha256 != key[0] or reader.chunk.model_dump(mode="json") != saved["original"]
                    or reader.counts()["payload_bytes"] != 0):
                raise ValueError("Original member metadata differs before acquisition")
    return before, resident


def run(root):
    from adaptive_raw_trial import launch, prepare, work
    from current_north_control import run as named
    from dense_geographic_trial import host
    from north_held_anchor_pair import tmpfs

    machine = host()
    git = ["git", "-C", str(HERE.parents[2])]
    revision = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
    if revision != MERGED or subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True):
        raise ValueError("Use the clean merged implementation for the timed comparison")
    tmpfs(root.parent)
    first = json.loads(gzip.decompress(checked(HERE/"measurements/north-strict-read.json.gz", FIRST_RECEIPT)))
    conversion_bytes, conversion = sealed_conversion(first, FIRST)
    before, packed = admitted_derivative(conversion)
    _, _, budget = frozen()
    clip, cache = work("north", root)
    original_before = cache()
    if clip != first["publication"]["plan"]["clip"] or machine != first["publication"]["plan"]["machine"]:
        raise ValueError("Original workload and measured machine settings must match both orders")
    root.mkdir()
    (root/"conversion.json").write_bytes(conversion_bytes)
    write(root/"plan.json", dict(machine=machine, clip=clip, resume_order=["named_v3", "packed_candidate"],
         target=1.6, arithmetic=budget, source=sha256(Path(__file__).read_bytes()).hexdigest(), revision=revision,
         first_pair=FIRST_RECEIPT, conversion_reused=True, original_before_both=original_before,
         packed_before_both=before))
    prepare("north", root/"candidate", strict=conversion["request"])
    named(root/"named", verify_after=False)
    write(root/"packed-before.json", packed())
    launch(root/"candidate")
    write(root/"packed-after.json", packed())


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    (run if args.action == "run" else score)(args.root)
