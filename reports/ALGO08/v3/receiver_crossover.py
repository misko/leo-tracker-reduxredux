"""Bind complete alternate packets and replay the pinned repaired v3 solver."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import BENCH, inputs, read, write


ALTERNATE = "sha256:d44c60320320be8281ed6e71285f8cb50cc0e204df9fa1eef53d36c514e51128"
DENSE_PAIR = Path("/tmp/ds30-v2-stage-covariance-375895/DS30-0008/pair.json")
CASES = ("DS30-0008", "south-containing", "south-far")
AUDIT = (*CASES, "north-containing")


def timing(native_path, terminal_path, run):
    delay = (terminal_path.stat().st_mtime_ns - native_path.stat().st_mtime_ns) / 1e9
    through_detection = run["terminal_file_s"] - delay
    if not 0 < through_detection < run["terminal_file_s"] <= run["elapsed_s"]:
        raise ValueError("Archived file order does not identify the acquisition boundary")
    return dict(detection_file_elapsed_s=through_detection, detection_to_terminal_elapsed_s=delay,
                terminal_file_elapsed_s=run["terminal_file_s"], complete_elapsed_s=run["elapsed_s"],
                complete_cpu_s=run["cpu_s"], input_blocks=run["input_blocks"])


def match_opportunities(stock, alternate):
    """Match source and clock authority while permitting different detections."""
    from leo.contracts.digests import canonical_digest

    exclude = {"analysis_manifest_sha256", "probes"}
    source = [{key: value for key, value in doc["source"].items() if key not in exclude}
              for doc in (stock, alternate)]
    for key in ("schema_version", "clock_anchor", "last_sample_counter", "delivery_clocks"):
        if stock[key] != alternate[key]:
            raise ValueError(f"Mismatched {key}")
    if source[0] != source[1]:
        raise ValueError("Different source authority")
    provenance = [{key: value for key, value in doc["provenance"].items()
                   if key not in ("detector_sha256", "run_id")} for doc in (stock, alternate)]
    if provenance[0] != provenance[1]:
        raise ValueError("Different capture coverage or rejected windows")
    probes = []
    audit = Counter()
    for before, after in zip(stock["source"]["probes"], alternate["source"]["probes"], strict=True):
        common = {key: value for key, value in before.items() if key != "candidates"}
        if common != {key: value for key, value in after.items() if key != "candidates"}:
            raise ValueError("Different ordered RF opportunity")
        probes.append(common)
        winners = [max((c for c in p["candidates"] if c["passed_fractional_margin_gate"]),
                       key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None)
                   for p in (before, after)]
        left, right = winners
        for name, winner in zip(("v3", "alternate"), winners, strict=True):
            if winner is not None:
                sign = "positive" if winner["fractional_tracking_cfo_hz"] >= 0 else "negative"
                audit[f"{name}_{sign}"] += 1
                audit[f"{name}_residual"] += winner["candidate_rank"] == 1
        if left is None or right is None:
            if left is not right:
                audit["lost" if right is None else "new"] += 1
        else:
            audit["rank_changed"] += left["candidate_rank"] != right["candidate_rank"]
            audit["cfo_changed"] += left["fractional_tracking_cfo_hz"] != right["fractional_tracking_cfo_hz"]
            audit["epoch_changed"] += any(left[key] != right[key] for key in
                                          ("integer_epoch_sample", "fractional_epoch_offset_samples"))
        audit["candidate_lists_changed"] += before["candidates"] != after["candidates"]
    return dict(opportunities=len(probes), opportunity_sha256=canonical_digest(probes),
                coverage=provenance[0], signed_selection_changes=dict(audit))


def bound(case):
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest

    stock, archive, offer, _, stock_identity = inputs(case)
    site = case.split("-")[0]
    dense = case == "DS30-0008"
    pair_path = DENSE_PAIR if dense else BENCH / f"covariance-{site}-inside/pair.json"
    pair = read(pair_path)
    spec = pair["candidate_specification"]
    if (pair["candidate_specification_digest"] != canonical_digest(spec)
            or "sha256:" + spec["detector_sha256"] != ALTERNATE):
        raise ValueError("Alternate binary is outside the frozen experiment")
    run = pair["runs"]["candidate"]
    receipt = run["receipt"]
    workspace = pair_path.parent / "candidate/fast-scan-automatic-work"
    terminal_path = workspace / receipt["run_id"] / "terminal.json"
    native_path, = workspace.glob("*/detections.json")
    terminal, native = read(terminal_path), read(native_path)
    if (canonical_digest(terminal) != receipt["terminal_sha256"]
            or canonical_digest(native) != terminal["native_sha256"]
            or native["provenance"]["detector_sha256"] != ALTERNATE
            or native["source"]["session_id"] != receipt["session_id"]
            or terminal["session_id"] != receipt["session_id"]
            or terminal["region"] != receipt["region"]
            or receipt["region"] != Algo08Region.parse(read(Path(pair["region"]))).document()
            or run["raw_authority"] != stock_identity["raw_authority"]
            or native["source"]["raw_recording_authority_digest"] != run["raw_authority"]
            or pair["archive"] != stock_identity["archive"]
            or native["provenance"]["window_count"] != receipt["window_count"]
            or any(native["provenance"][key] != receipt["counts"][receipt_key]
                   for key, receipt_key in (("processed_windows", "processed"),
                                             ("invalid_capture", "invalid_capture"),
                                             ("skipped_fast_score", "skipped_fast_score")))):
        raise ValueError("Alternate packet differs from its sealed origin")
    if not case.endswith("-far") and receipt["region"] != offer:
        raise ValueError("The archived containing offers differ")
    matched = match_opportunities(stock, native)
    identity = dict(stock_identity, detector_sha256=ALTERNATE, native_sha256=terminal["native_sha256"],
                    native_file_sha256=sha256(native_path.read_bytes()).hexdigest(),
                    pair_sha256=sha256(pair_path.read_bytes()).hexdigest(),
                    terminal_sha256=receipt["terminal_sha256"],
                    acquisition=timing(native_path, terminal_path, run))
    return native, archive, offer, None, identity, stock_identity, matched


def binding(row):
    return dict(candidate=row[4], v3=row[5], opportunity=row[6])


def freeze(output):
    write(output, {case: binding(bound(case)) for case in AUDIT})


def replay(case, lock, output):
    from blind_joint_trial import trial

    def load_saved_inputs():
        row = bound(case)
        if binding(row) != read(lock)[case]:
            raise ValueError("Saved crossover input changed after freezing")
        return row[:5]

    trial(case, output, repair=True, load_saved_inputs=load_saved_inputs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze_args = commands.add_parser("freeze")
    freeze_args.add_argument("output", type=Path)
    replay_args = commands.add_parser("replay")
    replay_args.add_argument("case", choices=CASES)
    replay_args.add_argument("lock", type=Path)
    replay_args.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    command = args.pop("command")
    {"freeze": freeze, "replay": replay}[command](**args)
