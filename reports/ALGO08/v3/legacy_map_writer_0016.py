"""Time the merged legacy map receipt writer on the complete original DS30-0016 fix."""

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import legacy_block_all_0016 as original
from visit_frame_raw_0016 import checked, digest, read


PRIOR = Path("/dev/shm/leo-v3-legacy-all-0016-result02")
PRIOR_PIN = "9a13cc45e8933106a6be91c5ddfd575c87c311773499420131a094b44113b557"
ORDINARY_PIN = "7e5f44b388a0674ab276282478122d218ef39adf9985acb31ef3e5a4d3b6afa0"
WRITER_PIN = "sha256:8a9155c1219fa1b88d9a547c12483dddcc6a245ca8c47061407b49f8e567387b"
AUDIT = "indexed/legacy-map-acquisition.json"
RUNTIME_UPDATES = {
    "reports/ALGO08/v3/legacy_block_raw_entry.py": "sha256:1eccf6d5529965a3587e2a001613f4f5eb174949facd9676663823ee7dc29a64",
    "reports/ALGO08/v3/legacy_block_multi.py": "sha256:f987c3ffdcb31221a664a3a8f029c457c1b2b91e8c9349f6f86d0f85da69e6e4",
}
SOURCES = (Path(__file__).name, "legacy-map-writer-0016-protocol.md", "legacy_map_receipt.py")
PATH_OPTIONS = ("--output", "--legacy-map-custody", "--legacy-map-library")
CLOCK_FIELDS = {"cpu_s", "elapsed_s", "cpu_ns", "wall_ns", "input_blocks"}


def prior_result():
    value = checked(PRIOR / "result.json", PRIOR_PIN)
    if (not value["qualified"] or not all(value["checks"].values())
            or value["ordinary_control_sha256"] != ORDINARY_PIN
            or value["input"]["totals"].get("ordinary_members", 0)
            or value["prediction_seal"] != digest(PRIOR / "prediction-seal.json")):
        raise ValueError("The exact earlier all-member publication and matched ordinary comparator are required")
    seal = read(PRIOR / "prediction-seal.json")
    if digest(PRIOR / AUDIT) != seal[AUDIT]:
        raise ValueError("The previously verified full map audit changed")
    return value


def check_sources(value):
    old = value["admission"]["sources"] | {
        "reports/ALGO08/v3/legacy_block_all_score.py": value["scorer"]["at_verification"]}
    if original.runtime_pins() != old | RUNTIME_UPDATES or digest(HERE / "legacy_map_receipt.py") != WRITER_PIN:
        raise ValueError("Only the merged audit write and the unused map-generation helper may differ from the earlier runtime")


def command_shape(argv):
    if Path(argv[5]).name != "legacy_block_all_entry.py":
        raise ValueError("The all-member production-shaped entry must be used")
    shape = list(argv)
    shape[5] = "legacy_block_all_entry.py"
    for key in PATH_OPTIONS:
        if shape.count(key) != 1:
            raise ValueError(f"Expected one explicit {key} path")
        shape[shape.index(key) + 1] = key
    return shape


def reopen(root, previous, session, inventory, authority, control_pin):
    from empty_bootstrap import clock, now
    from leo.storage.writer import _fsync_directory
    from reports.ALGO08.v3 import legacy_block_input as port, legacy_block_multi as multi

    started = now()
    value = prior_result()
    book = value["admission"]
    plan, pin = book["plan"], book["map_custody_sha256"]
    prep = book["preparation"]
    if (previous != PRIOR or control_pin != ORDINARY_PIN or prep["admitted_kinds"] != {"literal": 5, "exception": 8}
            or (plan["session"], plan["inventory"], plan["raw_authority"], plan["windows"]) != (session, inventory, authority, 808)):
        raise ValueError("Prepared maps must identify the unchanged complete original input")
    source, output = PRIOR / "maps", root / "maps"
    output.mkdir(mode=0o700)
    members = {row["map"]: (row["map_sha256"], multi.MAX_SIDECAR) for row in plan["members"]}
    if len(members) != 13 or None in members:
        raise ValueError("All thirteen authenticated maps must remain available")
    members.update({"custody.json": (pin, port.MAX_CUSTODY),
                    "legacy-block.so": (prep["build"]["binary_sha256"], 2_000_000)})
    for name, (expected, length) in members.items():
        port.checked_file(source / name, expected, length)
        (output / name).hardlink_to(source / name)
    _fsync_directory(output)
    _fsync_directory(root)
    if port.load_custody(output / "custody.json", pin) != plan:
        raise ValueError("Relocated maps do not preserve the verified custody")
    from legacy_block_raw_entry import parser

    command = original.projected_command(original.qualified_control(control_pin)["admission"]["commands"]["ordinary"],
        root / "indexed", output, pin, prep["build"]["binary_sha256"])
    if command_shape(command) != command_shape(book["commands"]["indexed"]):
        raise ValueError("Receiver, scientific options or native pins differ from the earlier published child")
    parser().parse_args(command[6:])
    return plan, pin, dict(prep, recovery_reuse=dict(clock=clock(started), raw_preparation_bytes=0,
        prior_score_sha256=PRIOR_PIN, prior_prediction_seal=value["prediction_seal"], writer_source_sha256=WRITER_PIN))


def launch(root):
    check_sources(prior_result())
    with (patch.object(original, "reuse_maps", reopen), patch.object(original, "SOURCES", (*original.SOURCES, *SOURCES))):
        original.launch(root, ORDINARY_PIN, reuse=PRIOR)


def scientific_audit(value):
    if isinstance(value, list):
        return [scientific_audit(row) for row in value]
    if isinstance(value, dict):
        return {key: ("measured clock" if key in CLOCK_FIELDS and type(field) in (int, float) else scientific_audit(field))
                for key, field in value.items()}
    return value


def score(root):
    import aperture_trial
    from legacy_block_all_score import score as verify_publication

    before = prior_result()
    check_sources(before)
    accepted = {}

    def collect(path, value):
        if path != root / "result.json" or accepted:
            raise ValueError("Expected one already verified scientific result")
        accepted.update(value)

    with (patch.object(aperture_trial, "write", collect),
          patch.object(original, "SOURCES", (*original.SOURCES, *SOURCES))):
        verify_publication(root, ORDINARY_PIN)
    prior_audit = read(PRIOR / AUDIT)
    new_path = root / AUDIT
    current = read(new_path)
    expected = (json.dumps(current, indent=2, sort_keys=True, allow_nan=False)+"\n").encode("utf-8")
    if (not accepted.get("qualified") or scientific_audit(current) != scientific_audit(prior_audit)
            or new_path.read_bytes() != expected or (root / "ordinary").exists()):
        raise ValueError("The emitted complete legacy audit or single-candidate scope differs")
    changes = {}
    for metric in ("elapsed_s", "cpu_s"):
        old, new = before["prices"][metric]["all_members"], accepted["prices"][metric]["all_members"]
        book = accepted["admission"]
        ready = book["ready_checks"][metric] + book["preparation"]["recovery_reuse"]["clock"][metric]
        changes[metric] = dict(previous_all_map_child=old, dedicated_writer_child=new, observed_child_delta=new-old,
            readiness=ready, new_child_with_readiness=new+ready, current_shared_admission=book["shared_admission"][metric],
            historical_ordinary=before["prices"][metric]["ordinary"], historical_five_maps=before["prices"][metric]["five_maps"],
            prior_all_map_first_use=before["prices"][metric]["all_observed_first_use_with_historical_preparation"],
            new_child_plus_historical_preparation=accepted["prices"][metric]["all_observed_first_use_with_historical_preparation"])
    accepted["dedicated_audit"] = dict(same_fields_and_non_timing_values=True, exact_canonical_format=True,
        previous_sha256=digest(PRIOR / AUDIT), new_sha256=digest(new_path), byte_count=len(expected),
        writer_source_sha256=WRITER_PIN, prior_process=before["products"]["indexed"]["process"],
        prior_child_phases=before["products"]["indexed"]["phases"], outcomes=changes)
    aperture_trial.write(root / "result.json", accepted)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    if args.action == "score":
        sys.path.insert(0, str(ROOT / "src"))
    {"launch": launch, "score": score}[args.action](args.root)
