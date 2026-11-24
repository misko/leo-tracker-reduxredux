"""Replay the frozen physical strict packed history+Cairo entry once on saved South."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
PRIOR = Path("/dev/shm/leo-v3-south-strict-result01")
PHYSICAL = Path("/dev/shm/leo-v3-strict-cairo-0016-score01.json")
PHYSICAL_PIN = "cc2268406d1e6cc9c3d3a8aec364c92ef89783b1904ba61630d466f301591d6d"
PINS = {
    "plan.json": "b3eaa7525961c2bbfe27b21dbe8fa0a4c7477c53bb56cfb5a829a72ac2e0ecbf",
    "conversion.json": "4b85a992e95d481480e0ddb98a79521a850907d96e137538b3f2adfc565f60e9",
    "result.json": "2bc6a1e927092fdda5e1e845b71fb45b55f1b78f0da6c14e4c2ad4501b1c1898",
    "named/clock.json": "6465d65481276419f62957c6f1b871a6910c5d79e85eaa52dfce5f1ac6e4d81a",
    "named/binding.json": "12f40ce46e0fd6f617d7b6992bdd67b178ced24bfa6bed14d6b969126d3c88ef",
    "named/stock.stdout": "fbee6c809141b3451f9d72bea88c7768aab2d91fe35dbf33547f613149a7367a",
    "candidate/binding.json": "16fe3b65d074f2ab961106f096eaff1c6b0ad9fb3d89d2952c9701fbd5c4e6a8",
}
LIBRARIES = ("--short-binary", "--geographic-library", "--regional-track-library", "--frontier-block-library")
REPLACEMENTS = ("--recording", "--archive", "--region", "--archive-sha256", "--output",
                "--packed-ci16-map", "--packed-ci16-map-sha256", "--packed-ci16-codec")
FLAGS = ("--history-risk-route", "--cairo-six-sheets", "--strict-packed-eight")


def archived(path):
    from empty_bootstrap import checked

    return json.loads(checked(PRIOR/path, PINS[path]))


def candidate_command(command, request, packed, destination):
    if (Path(command[5]).name != "exact_named_raw.py" or len(command) != 6 + len(FLAGS) + 2*(len(REPLACEMENTS)+len(LIBRARIES))
            or any(command.count(flag) != 1 for flag in FLAGS + REPLACEMENTS + LIBRARIES)):
        raise ValueError("Expected only the qualified physical strict-history-Cairo flags")
    args = list(command)
    args[5] = str(HERE/"exact_named_raw.py")
    values = (request["recording"], request["archive"]["root"], request["offers"]["containing"],
              request["archive"]["snapshots_sha256"], destination, packed["map"], packed["map_sha256"], packed["codec"])
    for flag, value in zip(REPLACEMENTS, values, strict=True):
        args[args.index(flag)+1] = str(value)
    return args


def verify_map(entries, sections, chunks, manifest):
    expected = {}
    for row, chunk in zip(sections, chunks, strict=True):
        binding = row["binding"]
        if (row["original"] != chunk or binding["manifest_sha256"] != "sha256:"+manifest
                or binding["chunk_index"] != chunk["chunk_index"]
                or row["checked_derivative"]["decoded_bytes"] != chunk["uncompressed_bytes"]
                or row["checked_derivative"]["full_checks"] != chunk["window_count"]):
            raise ValueError("Independent full readback must bind the original signed member")
        expected[binding["manifest_sha256"], binding["chunk_index"]] = binding["directory"], binding["seek_sha256"]
    if not expected or len(expected) != len(chunks) or entries != expected:
        raise ValueError("The derivative map must describe exactly the original signed inventory")


def setup(conversion, request, chunks):
    from empty_bootstrap import checked
    from exact_named_raw import staged_path
    from north_strict_read import resident_packed
    from packed_combined_input import member_map
    from reports.ALGO08.v3.ci16_packing import Packing
    from seekable_eight_raw import PREFIX
    from seekable_member import open_member

    config = conversion["request"]
    mapping, binary = (staged_path(Path(config[key]), root=PRIOR) for key in ("map", "codec"))
    codec_pin, entries = member_map(checked(mapping, config["map_sha256"][7:]), strict_eight=True)
    if codec_pin != "sha256:"+conversion["codec"]["binary_sha256"]:
        raise ValueError("Unexpected verified packed codec")
    checked(binary, codec_pin[7:])
    codec = Packing(binary)
    sections = conversion["sections"]
    verify_map(entries, sections, chunks, request["manifest_sha256"])
    folders = [staged_path(mapping.parent/row["binding"]["directory"], root=PRIOR) for row in sections]
    for folder, row in zip(folders, sections, strict=True):
        pin = row["binding"]
        with open_member(folder, pin["seek_sha256"], codec=codec, prefix_samples=PREFIX) as member:
            if (member.manifest_sha256 != pin["manifest_sha256"] or member.chunk.model_dump(mode="json") != row["original"]
                    or member.counts()["payload_bytes"]):
                raise ValueError("Expected authenticated strict metadata without a waveform read")
    return resident_packed(mapping.parent, folders, codec), folders, codec


def read_json(path):
    return json.loads(path.read_bytes())


def seal(root):
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sorted(root.rglob("*"))
            if path.is_file() and path.relative_to(root).parts[0] not in ("fonts", "tmp")
            and path.name not in ("prediction-seal.json", "result.json")}


def run(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import checked, clock, now
    from exact_named_raw import staged_path
    from north_strict_read import resident_packed
    from short_raw_diagnostic import measure
    from south_cfo_route import admissible, assigned, residency
    from south_strict_transfer import causal_cache

    start = now()
    if root.parent != Path("/dev/shm") or root.exists():
        raise ValueError("Provide a fresh dedicated tmpfs output")
    staged_path(PRIOR)
    plan = archived("plan.json")
    expected = plan["request"]
    for path in (expected["recording"], expected["archive"]["root"], *expected["offers"].values(), expected["saved_inventory"]):
        staged_path(Path(path))
    current = host()
    request, chunks = assigned()
    prior = archived("result.json")
    stock_binding = archived("named/binding.json")
    stock_clock = archived("named/clock.json")
    original = residency(chunks)
    causal = causal_cache(request)
    if (request != expected or current != plan["machine"] or not admissible(original)
            or causal != stock_binding["causal"] or stock_clock != prior["named_clock"] or stock_clock["exit_code"]):
        raise ValueError("The current South input, resident scope or host differs from the fresh named comparison")
    reference = json.loads(checked(PHYSICAL, PHYSICAL_PIN))
    checkout = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=ROOT).strip()
    conversion = archived("conversion.json")
    if not reference["qualified"] or conversion != prior["conversion"]:
        raise ValueError("Expected the frozen physical finalist and independently verified South derivative")
    command = candidate_command(reference["admission"]["command"], request, conversion["request"], root/"candidate")
    pins = archived("candidate/binding.json")["libraries"]
    for flag in LIBRARIES:
        pin = pins[flag]
        if command[command.index(flag)+1] != pin["path"]:
            raise ValueError(f"South and physical finalist use different native libraries: {flag}")
        checked(Path(pin["path"]), pin["sha256"])
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(PRIOR/"candidate/fonts", root/"fonts")
    common = clock(start)
    ready_start = now()
    packed, folders, codec = setup(conversion, request, chunks)
    ready = clock(ready_start)
    write(root/"admission.json", dict(revision=checkout, machine=current, request=request, command=command,
          library_pins={flag: pins[flag] for flag in LIBRARIES}, physical_sha256=PHYSICAL_PIN,
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), controls=PINS,
          named_children=0, containing_children=1, omitted_children=0, original_pages=original,
          causal=causal, packed_before=packed, common_setup=common, candidate_ready=ready))
    measured = measure(command, environment_for(root), root/"candidate")
    write(root/"candidate-clock.json", measured)
    write(root/"packed-after.json", resident_packed(Path(conversion["request"]["map"]).parent, folders, codec))
    write(root/"prediction-seal.json", seal(root))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    run(cli.parse_args().root)
