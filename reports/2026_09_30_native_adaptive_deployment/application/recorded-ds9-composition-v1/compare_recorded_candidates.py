"""Independent science comparison; reference receipts are validation inputs only."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


SCALAR_TOLERANCE = 1e-10
CFO_TOLERANCE_HZ = 1e-6
GATE = 0.025
INTEGER_FIELDS = (
    "acquired_cfo_hz", "integer_tracking_cfo_hz", "integer_exact_score",
    "integer_control_score", "integer_margin",
)
FRACTIONAL_FIELDS = (
    "fractional_offset", "tracking_cfo_hz", "exact_score", "control_score", "margin",
)
STATUSES = {"complete", "unbracketed", "not_evaluated"}


def event_candidates(stream):
    """Normalize public scanner ABI candidates; unavailable payloads have no value."""
    reader = csv.DictReader(stream, delimiter="\t")
    mapping = {
        "acquired_cfo_hz": "acquired_cfo_hz",
        "integer_tracking_cfo_hz": "tracking_cfo_hz",
        "integer_exact_score": "exact_score",
        "integer_control_score": "control_score", "integer_margin": "margin",
        "fractional_offset": "fractional_epoch_offset_samples",
        "tracking_cfo_hz": "fractional_tracking_cfo_hz",
        "exact_score": "fractional_exact_score",
        "control_score": "fractional_control_score", "margin": "fractional_margin",
    }
    required = set(mapping.values()) | {
        "kind", "visit", "receiver_id", "probe_index", "candidate_index",
        "epoch", "fractional_epoch_status", "detector_status",
    }
    if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not required <= set(reader.fieldnames)):
        raise ValueError("missing or duplicate event columns")
    result = {}
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("malformed event row")
        if row["kind"] != "5":
            continue
        key = tuple(int(row[name]) for name in (
            "visit", "receiver_id", "probe_index", "candidate_index"))
        if key in result or key[0] < 0 or key[1] not in (0, 1) or key[2] != 0:
            raise ValueError("invalid or duplicate candidate key")
        if not 0 <= key[3] < 8 or int(row["detector_status"]) != 0:
            raise ValueError("invalid candidate rank or failed detector")
        status = {0: "not_evaluated", 1: "complete", 2: "unbracketed"}.get(
            int(row["fractional_epoch_status"]))
        if status is None:
            raise ValueError("unknown fractional status")
        candidate = {"rank": key[3], "integer_epoch": int(row["epoch"]),
                     "fractional_status": status}
        for field, column in mapping.items():
            candidate[field] = (None if field in FRACTIONAL_FIELDS and status != "complete"
                                else finite(float(row[column])))
        result[key] = candidate
    return result


def indexed_candidates(receipts, side):
    """Index normalized receipts by original (visit, receiver, probe, rank)."""
    result = {}
    visits = set()
    for receipt in receipts:
        visit = receipt["visit"]
        if type(visit) is not int or visit < 0 or visit in visits:
            raise ValueError("invalid or duplicate visit")
        visits.add(visit)
        if receipt.get("status") != "pass":
            raise ValueError("reference receipt did not pass")
        receivers = receipt[side]
        if set(receivers) != {"0", "1"}:
            raise ValueError("expected both receivers")
        for rx, candidates in receivers.items():
            if len(candidates) != 8:
                raise ValueError("expected eight retained candidates per receiver")
            for rank, candidate in enumerate(candidates):
                if candidate["rank"] != rank:
                    raise ValueError("candidate rank/order mismatch")
                result[(visit, int(rx), 0, rank)] = candidate
    if not result:
        raise ValueError("empty comparison")
    return result


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("candidate field is not numeric")
    if not math.isfinite(value):
        raise ValueError("nonfinite candidate field")
    return value


def compare(actual, expected):
    """Require complete key coverage, structure, numeric tolerances and gates."""
    if not expected or actual.keys() != expected.keys():
        raise ValueError("candidate coverage mismatch")
    maxima = {name: 0.0 for name in INTEGER_FIELDS + FRACTIONAL_FIELDS}
    complete = passing = unavailable = 0
    for key in sorted(expected):
        left, right = actual[key], expected[key]
        for field in ("rank", "integer_epoch"):
            if type(left[field]) is not int or type(right[field]) is not int:
                raise ValueError(f"noninteger {field} at {key}")
            if left[field] != right[field]:
                raise ValueError(f"different {field} at {key}")
        status = left["fractional_status"]
        if status not in STATUSES or status != right["fractional_status"]:
            raise ValueError(f"fractional status mismatch at {key}")
        fields = INTEGER_FIELDS
        if status == "complete":
            complete += 1
            fields += FRACTIONAL_FIELDS
            left_pass = finite(left["margin"]) >= GATE
            right_pass = finite(right["margin"]) >= GATE
            if left_pass != right_pass:
                raise ValueError(f"gate mismatch at {key}")
            passing += left_pass
        else:
            unavailable += 1
            if any(left[name] is not None or right[name] is not None
                   for name in FRACTIONAL_FIELDS):
                raise ValueError(f"unavailable fractional field is populated at {key}")
        for field in fields:
            delta = abs(finite(left[field]) - finite(right[field]))
            tolerance = CFO_TOLERANCE_HZ if field.endswith("_hz") else SCALAR_TOLERANCE
            if delta > tolerance:
                raise ValueError(f"{field} exceeds tolerance at {key}: {delta}")
            maxima[field] = max(maxima[field], delta)
    return {"status": "PASS", "retained_candidates": len(expected),
            "complete_candidates": complete, "passing_candidates": passing,
            "unavailable_fractional_candidates": unavailable,
            "maximum_absolute_deltas": maxima}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--reference-directory", type=Path, required=True)
    parser.add_argument("--visits", type=int, nargs="+", required=True,
                        help="Externally expected original visits; never inferred from output")
    args = parser.parse_args()
    if len(set(args.visits)) != len(args.visits):
        parser.error("duplicate expected visits")
    paths = [args.reference_directory / f"visit-{visit:06d}.json" for visit in args.visits]
    receipts = [json.loads(path.read_text()) for path in paths]
    if [receipt["visit"] for receipt in receipts] != args.visits:
        raise ValueError("reference file/visit mismatch")
    with args.events.open() as stream:
        actual = event_candidates(stream)
    report = {"schema": "leo-recorded-candidate-comparison/v1",
              "scope": "candidate science only; excludes projection, tracking and location",
              "expected_visits": args.visits,
              "events_sha256": hashlib.sha256(args.events.read_bytes()).hexdigest(),
              "reference_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                   for path in paths},
              "native_host": compare(actual, indexed_candidates(receipts, "native")),
              "current_server": compare(actual, indexed_candidates(receipts, "current_server"))}
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
