"""Read-only export of original winning-peak scores keyed by frozen observation ID."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path


def score_records(document, context):
    """Join unchanged per-lane sequences and verify every winning CFO exactly."""
    raw_lanes, context_lanes = defaultdict(list), defaultdict(list)
    for probe in document["probes"]:
        eligible = [c for c in probe["candidates"] if c["passed_fractional_margin_gate"] is True]
        if not eligible:
            continue
        candidate = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
        key = (probe["receiver_id"] + 1, probe["channel"])
        raw_lanes[key].append(
            dict(
                fractional_margin=candidate["fractional_margin"],
                fractional_exact_score=candidate["fractional_exact_score"],
                fractional_control_score=candidate["fractional_control_score"],
                measured_cfo_hz=candidate["fractional_tracking_cfo_hz"],
                receiver=probe["receiver_id"] + 1,
                channel=probe["channel"],
                valid_start_counter=probe["valid_start_counter"],
                actual_rf_hz=probe["actual_rf_hz"],
            )
        )
    for row in context:
        context_lanes[row["receiver"], row["channel"]].append(row)
    if raw_lanes.keys() != context_lanes.keys():
        raise ValueError("raw/context lane inventory differs")
    result = {}
    for key in raw_lanes:
        raw = sorted(raw_lanes[key], key=lambda r: r["valid_start_counter"])
        rows = sorted(context_lanes[key], key=lambda r: r["time_s"])
        if len(raw) != len(rows):
            raise ValueError("raw/context lane observation count differs")
        for record, row in zip(raw, rows, strict=True):
            if (
                abs(record["measured_cfo_hz"] - row["measured_cfo_hz"]) > 1e-8
                or record["actual_rf_hz"] != row["actual_rf_hz"]
            ):
                raise ValueError("raw/context winning CFO or RF differs")
            oid = row["observation_id"]
            if oid in result:
                raise ValueError("duplicate observation identity")
            result[oid] = dict(record, context_time_s=row["time_s"])
    return result


def run():
    root = Path(__file__).resolve().parents[1]
    sources = json.loads(
        (root / "reports/2026_10_16_dsx01_fast_association_losses/sources.json").read_text()
    )
    result = {}
    context = [
        json.loads(line)
        for line in (
            root / "reports/2026_10_16_dsx01_fast_association_losses/context-observations.jsonl"
        )
        .read_text()
        .splitlines()
    ]
    for row in sources:
        raw = Path(row["tracking_input_path"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row["tracking_input_sha256"].removeprefix("sha256:"):
            raise ValueError("tracking source hash changed")
        result["DSX01-" + row["source_id"]] = dict(
            source_sha256=digest,
            scores=score_records(
                json.loads(raw)["source"],
                [r for r in context if r["source_id"] == row["source_id"]],
            ),
        )
    return result


if __name__ == "__main__":
    print(json.dumps(run()))
