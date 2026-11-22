"""Describe how receiver selections changed on the same admitted RF opportunities."""
import argparse
from collections import Counter
import json
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore


def bound_native(root, run):
    receipt = run["receipt"]
    workspace = FastScanStore(root).automatic_workspace(receipt["run_id"], create=False)
    terminal = json.loads((workspace / "terminal.json").read_bytes())
    detection_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    native = json.loads(detection_path.read_bytes())
    if (canonical_digest(terminal) != receipt["terminal_sha256"]
            or canonical_digest(native) != terminal["native_sha256"]
            or terminal["session_id"] != receipt["session_id"]
            or native["source"]["session_id"] != receipt["session_id"]
            or native["source"]["raw_recording_authority_digest"] != run["raw_authority"]):
        raise ValueError("Different terminal or native input")
    return native


def bound_rows(root, run):
    return bound_native(root, run)["source"]["probes"]


def selection(row):
    candidates = row["candidates"]
    if not candidates:
        return "none"
    factor, = candidates
    return {0: "primary", 1: "residual"}[factor["candidate_rank"]]


def changes(before, after):
    transitions, channels = Counter(), Counter()
    changed = []
    for a, b in zip(before, after, strict=True):
        a_meta = {k: v for k, v in a.items() if k != "candidates"}
        b_meta = {k: v for k, v in b.items() if k != "candidates"}
        if a_meta != b_meta:
            raise ValueError("Different admitted RF opportunity or ordering")
        if a["candidates"] == b["candidates"]:
            continue
        first, second = selection(a), selection(b)
        transitions[f"{first}_to_{second}"] += 1
        channels[str(a["channel"])] += 1
        changed.append(dict(visit=a["visit_index"], receiver=a["receiver_id"], channel=a["channel"],
                            actual_rf_hz=a["actual_rf_hz"], baseline=a["candidates"], candidate=b["candidates"]))
    return dict(opportunities=len(before), changed=len(changed), transitions=dict(transitions),
                changes_by_channel=dict(channels), rows=changed)


def selection_summary(before, after):
    """Separate missing or changed winning ranks from numerical field changes."""
    delta = changes(before, after)
    field_counts, maximum = Counter(), Counter()
    for row in delta["rows"]:
        left, right = row["baseline"], row["candidate"]
        if not left or not right or left[0]["candidate_rank"] != right[0]["candidate_rank"]:
            continue
        a, b = left[0], right[0]
        if a.keys() != b.keys():
            raise ValueError("Selected factors have different fields")
        for name, value in a.items():
            if value != b[name]:
                field_counts[name] += 1
                if type(value) in (float, int) and type(b[name]) in (float, int):
                    maximum[name] = max(maximum[name], abs(value - b[name]))
    return dict(opportunities=delta["opportunities"], changed=delta["changed"],
                selections={key: sum(len(r["candidates"]) for r in rows)
                            for key, rows in (("baseline", before), ("candidate", after))},
                transitions_on_changed_rows=delta["transitions"],
                same_rank_field_counts=dict(field_counts), same_rank_max_abs_delta=dict(maximum))


def compare(pair, *, summary=False):
    doc = json.loads(pair.read_bytes())
    before, after = (doc["runs"][name] for name in ("baseline", "candidate"))
    if (before["raw_authority"] != after["raw_authority"]
            or before["receipt"]["region"] != after["receipt"]["region"]):
        raise ValueError("Expected one sealed recording and the same regional offer")
    evaluate = selection_summary if summary else changes
    return evaluate(bound_rows(pair.parent / "baseline", before),
                    bound_rows(pair.parent / "candidate", after))


def compare_candidates(earlier, later):
    """Compare published candidate outputs on one matched recording across two stages."""
    cases = [json.loads(path.read_bytes()) for path in (earlier, later)]
    if any(cases[0][key] != cases[1][key] for key in ("archive", "recording")):
        raise ValueError("Recording or causal archive differs between candidate stages")
    runs = [case["runs"]["candidate"] for case in cases]
    before, after = runs
    if (before["raw_authority"] != after["raw_authority"] or
            any(before["receipt"][key] != after["receipt"][key]
                for key in ("session_id", "region", "window_count", "counts"))):
        raise ValueError("Candidate stages must share raw authority, regional offer and capture coverage")
    digests = [canonical_digest(case["candidate_specification"]) for case in cases]
    if digests != [case["candidate_specification_digest"] for case in cases]:
        raise ValueError("Candidate specification digest mismatch")
    rows = [bound_rows(path.parent / "candidate", run)
            for path, run in zip((earlier, later), runs, strict=True)]
    return dict(candidate_digests=digests, session=before["receipt"]["session_id"],
                raw_authority=before["raw_authority"], selected=selection_summary(*rows),
                same_decision=before["receipt"]["decision"] == after["receipt"]["decision"],
                same_withhold_reason=before["reason"] == after["reason"],
                same_arms=before["arms"] == after["arms"],
                same_owners=before["owners"] == after["owners"],
                same_grid_and_path=before["scientific_digests"] == after["scientific_digests"],
                same_encoded_figures=before["artifacts"] == after["artifacts"],
                figure_counts=[len(run["artifacts"]) for run in runs])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pair", type=Path)
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--summary", action="store_true", help="Count field changes among same-rank selections")
    mode.add_argument("--earlier-candidate", type=Path, help="Compare to the candidate from this earlier pair receipt")
    args = cli.parse_args()
    result = (compare_candidates(args.earlier_candidate, args.pair) if args.earlier_candidate
              else compare(args.pair, summary=args.summary))
    print(json.dumps(result, indent=2, allow_nan=False))
