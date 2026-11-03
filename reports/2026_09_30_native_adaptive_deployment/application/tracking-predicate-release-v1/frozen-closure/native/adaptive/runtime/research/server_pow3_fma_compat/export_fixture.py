#!/usr/bin/env python3
import json
import sys


def exact(value):
    return format(float(value), ".17g")


if len(sys.argv) != 4:
    raise SystemExit("usage: export_fixture.py PROJECTION.jsonl INPUT.tsv EXPECTED.tsv")

with open(sys.argv[1], encoding="utf-8") as source, \
     open(sys.argv[2], "w", encoding="utf-8") as inputs, \
     open(sys.argv[3], "w", encoding="utf-8") as expected:
    for line in source:
        record = json.loads(line)
        src = record["source"]
        candidate = record["candidate"]
        fields = [
            src["rate"], src["anchor_counter"], src["anchor_utc_ns"],
            src["generation"], src["visit"], src["window_counter"],
            src["probe_index"], src["receiver"], src["channel"],
            int(src["upper_edge"]), src["actual_rf_hz"],
            src["utc_bracket_width_ns"], src["input_digest"],
            src["analysis_digest"], int(src["continuity_qualified"]),
            candidate["rank"], candidate["integer_epoch"],
            candidate["fractional_offset"], candidate["tracking_cfo_hz"],
            candidate["exact_score"], candidate["control_score"],
            candidate["margin"], int(candidate["complete"]),
        ]
        inputs.write("\t".join(map(str, fields)) + "\n")
        oracle = record.get("expected")
        if oracle is None:
            expected.write("unavailable\n")
            continue
        expected.write("\t".join([
            oracle["candidate_id"], oracle["source_group_id"],
            str(oracle["support_start_utc_ns"]),
            str(oracle["support_center_utc_ns"]),
            str(oracle["support_end_utc_ns"]),
            exact(candidate["tracking_cfo_hz"]),
            exact(oracle["standard_uncertainty_hz"]),
            exact(oracle["factorial_support_moments_s"][2]),
            exact(oracle["factorial_support_moments_s"][3]),
        ]) + "\n")
