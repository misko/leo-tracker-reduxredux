"""Independent numerical audit of the DS8 alignment export."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

ROLES = ("reception", "held_frequency")
THRESHOLDS = (500, 1500)
BINS = ((0, 30, "0-30"), (30, 60, "30-60"), (60, 90, "60-90"), (90, math.inf, "90+"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left, right) -> None:
    if isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            close(left[key], right[key])
    elif isinstance(left, list):
        assert len(left) == len(right)
        for a, b in zip(left, right, strict=True):
            close(a, b)
    elif isinstance(left, float):
        assert math.isclose(left, float(right), rel_tol=0, abs_tol=1e-12)
    else:
        assert left == right


def mean(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    names = rows[0]["metrics"]
    return {
        "windows": len(rows),
        "metrics": {
            name: math.fsum(r["metrics"][name] for r in rows) / len(rows) for name in names
        },
    }


def compute(dataset: dict) -> tuple[dict, dict]:
    exported = {}
    record_rows: dict[str, list[dict]] = defaultdict(list)
    state_error = 0.0
    for lane in dataset["lanes"]:
        sid = lane["lane"]["session_id"]
        period = float(lane["alias_period_hz"])
        nominees = lane["components"][:-1]
        logs = [float(row["log_prior"]) for row in nominees]
        peak = max(logs)
        weights = [math.exp(value - peak) for value in logs]
        total = math.fsum(weights)
        weights = [value / total for value in weights]
        origin = min(w["prediction_utc_ns"] for w in lane["windows"] if w["role"] == "reception")
        for window in lane["windows"]:
            observations = window["observed"]
            metrics = {
                "rx0_observed": float(bool(observations["rx0"])),
                "rx1_observed": float(bool(observations["rx1"])),
                "prior_weighted_visible": math.fsum(
                    weight * bool(prediction["visible"])
                    for weight, prediction in zip(weights, window["predictions"], strict=True)
                ),
            }
            states_by_threshold = {}
            for threshold in THRESHOLDS:
                states = []
                for prediction in window["predictions"]:
                    visible = bool(prediction["visible"])
                    mu = float(prediction["mu_canonical_rx0_hz"])
                    state = []
                    for receiver in ("rx0", "rx1"):
                        values = [float(c["canonical_rx0_hz"]) for c in observations[receiver]]
                        nearest = min(
                            (
                                abs((value - mu + period / 2) % period - period / 2)
                                for value in values
                            ),
                            default=math.inf,
                        )
                        state.append(visible and nearest <= threshold)
                    states.append(tuple(state))
                states_by_threshold[threshold] = states
                for index, receiver in enumerate(("rx0", "rx1")):
                    metrics[f"{receiver}_within_{threshold}hz"] = math.fsum(
                        w * s[index] for w, s in zip(weights, states, strict=True)
                    )
                for label, target in (
                    ("both", (True, True)),
                    ("rx0_only", (True, False)),
                    ("rx1_only", (False, True)),
                    ("neither", (False, False)),
                ):
                    metrics[f"paired_{threshold}hz_{label}"] = math.fsum(
                        w for w, s in zip(weights, states, strict=True) if s == target
                    )
                state_error = max(
                    state_error,
                    abs(
                        math.fsum(
                            metrics[f"paired_{threshold}hz_{x}"]
                            for x in ("both", "rx0_only", "rx1_only", "neither")
                        )
                        - 1
                    ),
                )
            elapsed = (window["prediction_utc_ns"] - origin) / 1e9
            label = next(label for low, high, label in BINS if low <= elapsed < high)
            row = {"role": window["role"], "elapsed_bin": label, "metrics": metrics}
            exported[window["source_window_id"]] = metrics
            record_rows[sid].append(row)
    records = {}
    for sid, rows in record_rows.items():
        roles = {role: mean([r for r in rows if r["role"] == role]) for role in ROLES}
        bins = {}
        for role in ROLES:
            for _, _, label in BINS:
                value = mean([r for r in rows if r["role"] == role and r["elapsed_bin"] == label])
                if value:
                    bins[f"{role}:{label}"] = value
        records[sid] = {"windows": len(rows), "roles": roles, "elapsed_bins": bins}
    aggregates = {"roles": {}, "elapsed_bins": {}}
    for role in ROLES:
        rows = [r["roles"][role] for r in records.values()]
        names = rows[0]["metrics"]
        aggregates["roles"][role] = {
            "records": len(rows),
            "windows": sum(r["windows"] for r in rows),
            "metrics": {n: math.fsum(r["metrics"][n] for r in rows) / len(rows) for n in names},
        }
    for role in ROLES:
        for _, _, label in BINS:
            key = f"{role}:{label}"
            rows = [r["elapsed_bins"][key] for r in records.values() if key in r["elapsed_bins"]]
            if rows:
                names = rows[0]["metrics"]
                aggregates["elapsed_bins"][key] = {
                    "records": len(rows),
                    "windows": sum(r["windows"] for r in rows),
                    "metrics": {
                        n: math.fsum(r["metrics"][n] for r in rows) / len(rows) for n in names
                    },
                }
    return {"records": records, "aggregate_equal_record": aggregates}, {
        "maximum_paired_state_sum_error": state_error,
        "windows": len(exported),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = json.loads(args.results.read_text())
    dataset = json.loads(args.dataset.read_text())
    evidence = json.loads(args.evidence.read_text())
    dataset_hash = digest(args.dataset)
    assert results["dataset_sha256"] == dataset_hash
    key = "reports/2026_09_28_rx_ds8_confirmation/dataset.json"
    assert evidence[key] == dataset_hash
    expected, checks = compute(dataset)
    close(expected["records"], results["records"])
    close(expected["aggregate_equal_record"], results["aggregate_equal_record"])
    assert checks["maximum_paired_state_sum_error"] <= 1e-12
    output = {
        "schema": "rx-ds8-alignment-audit/v1",
        "status": "passed",
        "source_sha256": {
            "results": digest(args.results),
            "dataset": dataset_hash,
            "evidence": digest(args.evidence),
        },
        "checks": checks,
        "sessions": sorted(expected["records"]),
        "thresholds_hz": list(THRESHOLDS),
        "empty_or_invisible_contribution": 0.0,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
