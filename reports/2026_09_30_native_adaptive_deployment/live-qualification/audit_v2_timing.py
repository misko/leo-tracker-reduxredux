#!/usr/bin/env python3
"""Audit source-counter timing invariants in native scanner event/v2 JSONL logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any


SCHEMA = "leo-native-scanner-event/v2"
AUDIT_SCHEMA = "leo-native-scanner-timing-audit/v1"


def tick_stats(values: list[int], rate: int) -> dict[str, Any] | None:
    if not values:
        return None
    ordered = sorted(values)
    p95 = ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
    median = statistics.median(ordered)

    def pair(value: int | float) -> dict[str, int | float]:
        return {"ticks": value, "ms": value * 1000.0 / rate}

    return {
        "count": len(values),
        "minimum": pair(ordered[0]),
        "median": pair(median),
        "p95": pair(p95),
        "maximum": pair(ordered[-1]),
    }


def violation(check: str, visit: Any, **details: Any) -> dict[str, Any]:
    return {"check": check, "visit": visit, **details}


def audit(path: Path, rate: int, transition_ms: int, revisit_ms: int) -> dict[str, Any]:
    transition = rate * transition_ms // 1000
    revisit_limit = rate * revisit_ms // 1000
    raw = path.read_bytes()
    visits: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    malformed: list[int] = []
    schemas: set[str] = set()
    visit_schemas: set[str] = set()
    line_count = 0

    for line_count, line in enumerate(raw.splitlines(), 1):
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            malformed.append(line_count)
            continue
        if isinstance(event, dict) and "schema" in event:
            schemas.add(str(event["schema"]))
        if isinstance(event, dict) and event.get("kind") == "visit":
            visit_schemas.add(str(event.get("schema")))
            visits.append(event)

    if malformed:
        problems.append(violation("valid_json", None, lines=malformed))
    if visit_schemas != {SCHEMA}:
        problems.append(violation("visit_event_schema", None,
            expected=SCHEMA, observed=sorted(visit_schemas)))
    if not visits:
        problems.append(violation("visit_records_present", None))

    selection_gaps: list[int] = []
    recall_snapshot_ages: list[int] = []
    recall_durations: list[int] = []
    guards: list[int] = []
    nominal_guards: list[int] = []
    late_guards: list[int] = []
    revisits: list[tuple[int, int, int, int]] = []
    last_start: dict[int, tuple[int, int]] = {}
    target_binding: dict[int, tuple[int, int]] = {}
    branch_counts = {"same_profile": 0, "nominal_recall": 0, "late_recall": 0}
    previous: dict[str, Any] | None = None
    required = (
        "visit", "target", "profile", "frequency_hz", "attested_profile_crc32",
        "valid_start", "valid_end", "selection_counter",
        "transition_counter_before", "transition_counter_after", "recalled",
    )

    for row_number, event in enumerate(visits):
        missing = [key for key in required if key not in event]
        if missing:
            problems.append(violation("required_fields", event.get("visit"), missing=missing))
            continue
        visit = event["visit"]
        target = event["target"]
        profile = event["profile"]
        frequency = event["frequency_hz"]
        start = event["valid_start"]
        end = event["valid_end"]
        selection = event["selection_counter"]
        before = event["transition_counter_before"]
        after = event["transition_counter_after"]
        recalled = bool(event["recalled"])

        if row_number and visit != visits[row_number - 1].get("visit", visit - 1) + 1:
            problems.append(violation("visit_sequence", visit,
                previous=visits[row_number - 1].get("visit")))
        if not event["attested_profile_crc32"] or frequency <= 0:
            problems.append(violation("profile_attestation", visit,
                profile=profile, frequency_hz=frequency,
                crc32=event["attested_profile_crc32"]))
        binding = (profile, frequency)
        if target in target_binding and target_binding[target] != binding:
            problems.append(violation("target_profile_binding", visit, target=target,
                expected_profile=target_binding[target][0],
                expected_frequency_hz=target_binding[target][1],
                actual_profile=profile, actual_frequency_hz=frequency))
        else:
            target_binding[target] = binding

        if end <= start:
            problems.append(violation("valid_interval", visit,
                valid_start=start, valid_end=end))
        if previous is not None:
            selection_gap = selection - previous["valid_end"]
            selection_gaps.append(selection_gap)
            if start < previous["valid_end"]:
                problems.append(violation("visit_overlap", visit,
                    previous_visit=previous["visit"], previous_valid_end=previous["valid_end"],
                    valid_start=start))
            expected_recall = profile != previous["profile"]
            if recalled != expected_recall:
                problems.append(violation("profile_transition", visit,
                    previous_profile=previous["profile"], profile=profile,
                    expected_recalled=expected_recall, actual_recalled=recalled))

        nominal = selection + transition
        if recalled:
            if not (selection <= before <= after):
                problems.append(violation("recall_counter_order", visit,
                    selection_counter=selection, counter_before=before, counter_after=after))
            recall_snapshot_ages.append(before - selection)
            recall_durations.append(after - before)
            guard = start - after
            guards.append(guard)
            if after <= nominal:
                branch_counts["nominal_recall"] += 1
                nominal_guards.append(guard)
                expected_start = nominal
                branch = "nominal_recall"
            else:
                branch_counts["late_recall"] += 1
                late_guards.append(guard)
                expected_start = after + transition
                branch = "late_recall"
        else:
            branch_counts["same_profile"] += 1
            expected_start = selection
            branch = "same_profile"
            if before != selection or after != selection:
                problems.append(violation("same_profile_transition", visit,
                    selection_counter=selection, counter_before=before, counter_after=after))
        if start != expected_start:
            problems.append(violation("physical_valid_start_formula", visit,
                branch=branch, expected_valid_start=expected_start, actual_valid_start=start,
                selection_counter=selection, counter_after=after,
                transition_ticks=transition))

        if target in last_start:
            prior_visit, prior_start = last_start[target]
            delta = start - prior_start
            revisits.append((delta, target, prior_visit, visit))
            if delta > revisit_limit:
                problems.append(violation("maximum_revisit", visit, target=target,
                    previous_visit=prior_visit, previous_valid_start=prior_start,
                    valid_start=start, delta_ticks=delta,
                    delta_ms=delta * 1000.0 / rate,
                    limit_ticks=revisit_limit, limit_ms=revisit_ms))
        last_start[target] = (visit, start)
        previous = event

    maximum_revisit = max(revisits, default=None)
    positive_gaps = sum(value > 0 for value in selection_gaps)
    zero_gaps = sum(value == 0 for value in selection_gaps)
    negative_gaps = sum(value < 0 for value in selection_gaps)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "line_count": line_count,
        "malformed_json_lines": malformed,
        "schemas": sorted(schemas),
        "visit_count": len(visits),
        "transition_branches": branch_counts,
        "fresh_snapshot_observation": {
            "selection_minus_previous_valid_end": tick_stats(selection_gaps, rate),
            "positive_count": positive_gaps,
            "zero_count": zero_gaps,
            "negative_count": negative_gaps,
            "recall_counter_before_minus_selection": tick_stats(recall_snapshot_ages, rate),
        },
        "recall_counter_duration": tick_stats(recall_durations, rate),
        "post_recall_guard": {
            "all": tick_stats(guards, rate),
            "nominal": tick_stats(nominal_guards, rate),
            "late": tick_stats(late_guards, rate),
        },
        "maximum_observed_revisit": None if maximum_revisit is None else {
            "ticks": maximum_revisit[0],
            "ms": maximum_revisit[0] * 1000.0 / rate,
            "target": maximum_revisit[1],
            "previous_visit": maximum_revisit[2],
            "visit": maximum_revisit[3],
        },
        "violation_count": len(problems),
        "violations": problems,
        "status": "pass" if not problems else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--sample-rate-hz", type=int, default=2_500_000)
    parser.add_argument("--transition-ms", type=int, default=20)
    parser.add_argument("--maximum-revisit-ms", type=int, default=3000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-failures", action="store_true",
        help="return success after recording violations (for historical comparisons)")
    args = parser.parse_args()
    if args.sample_rate_hz <= 0 or args.transition_ms <= 0 or args.maximum_revisit_ms <= 0:
        parser.error("rates and timing limits must be positive")

    results = [audit(path, args.sample_rate_hz, args.transition_ms,
        args.maximum_revisit_ms) for path in args.logs]
    auditor_path = Path(__file__).resolve()
    document = {
        "schema": AUDIT_SCHEMA,
        "auditor": {
            "path": str(auditor_path),
            "sha256": hashlib.sha256(auditor_path.read_bytes()).hexdigest(),
        },
        "configuration": {
            "sample_rate_hz": args.sample_rate_hz,
            "transition_ms": args.transition_ms,
            "maximum_revisit_ms": args.maximum_revisit_ms,
            "deadline_semantics": "committed valid_start to committed valid_start",
        },
        "checks": [
            "visit event/v2 schema and sequence",
            "nonzero profile attestation and stable target/profile/frequency binding",
            "profile change iff recalled after the first observed visit",
            "selection <= recall counter_before <= counter_after",
            "maintained nominal/late/same-profile valid_start formula",
            "non-overlapping valid intervals",
            "committed valid_start revisit <= maximum_revisit_ms",
        ],
        "logs": results,
        "status": "pass" if all(result["status"] == "pass" for result in results) else "fail",
    }
    rendered = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0 if args.allow_failures or document["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
