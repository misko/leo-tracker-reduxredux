#!/usr/bin/env python3
"""Independently audit the frozen presence-geometry result receipt."""

import argparse
import hashlib
import json
import math
from pathlib import Path

ARMS = ("D", "S", "T", "swap", "reverse", "D_shift", "S_shift", "T_shift")
CONTRASTS = (
    ("S", "D"),
    ("T", "S"),
    ("T", "swap"),
    ("T", "reverse"),
    ("D", "D_shift"),
    ("S", "S_shift"),
    ("T", "T_shift"),
)
EXPECTED_GRID = {(0.0, 1.0)} | {
    (occupancy, tau) for occupancy in (0.01, 0.1, 0.5) for tau in (0.1, 1.0, 10.0)
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def absent_scores(dataset: dict, lambdas: list[float]) -> dict:
    output = {}
    for lane in dataset["lanes"]:
        if lane["recording_split"] != "evaluation":
            continue
        sid = lane["lane"]["session_id"]
        row = output.setdefault(sid, {"held_windows": 0, "absent_log_score": 0.0})
        period = float(lane["alias_period_hz"])
        for window in lane["windows"]:
            if window["role"] != "held_frequency":
                continue
            row["held_windows"] += 1
            for index, receiver in enumerate(("rx0", "rx1")):
                count = len(window["observed"][receiver])
                rate = float(lambdas[index])
                row["absent_log_score"] += -rate + count * math.log(rate / period)
    return output


def audit(results: dict, source_hashes: dict[str, str], datasets: dict, model: dict) -> dict:
    if results.get("schema") != "rx-presence-geometry/v1" or results.get("status") != "complete":
        raise ValueError("results are not complete presence-geometry evidence")
    if results.get("source_sha256") != source_hashes:
        raise ValueError("results source hashes differ from supplied inputs")
    selections = {}
    for arm in ("D", "S", "T"):
        selection = results["state_selections"][arm]
        grid = selection["grid"]
        if len(grid) != len(EXPECTED_GRID):
            raise ValueError("state selection grid must contain ten prespecified points")
        keys = [(row["occupancy"], row["tau_s"]) for row in grid]
        if set(keys) != EXPECTED_GRID or len(keys) != len(EXPECTED_GRID):
            raise ValueError("state selection grid differs from the prespecified points")
        expected = min(
            grid,
            key=lambda row: (
                -row["calibration_log_score"],
                row["occupancy"],
                row["tau_s"],
            ),
        )
        if selection["selected"] != expected:
            raise ValueError(f"{arm} selection is not the deterministic grid maximum")
        occupancy = float(expected["occupancy"])
        selections[arm] = {
            "occupancy": occupancy,
            "initial_absent_probability": 1.0 - occupancy,
            "tau_s": expected["tau_s"],
            "grid_max_log_score": expected["calibration_log_score"],
            "grid_points": len(grid),
        }
    panels = {}
    combined_values = {f"{left}-{right}": {} for left, right in CONTRASTS}
    combined_absent = {arm: {} for arm in ("D", "S", "T")}
    for panel_name, panel in results["panels"].items():
        evaluations = panel["evaluations"]
        if set(evaluations) != set(ARMS):
            raise ValueError(f"{panel_name} evaluation arms differ from frozen design")
        denominator = None
        recomputed = {}
        analytical_absent = absent_scores(datasets[panel_name], model["clutter_intensities"])
        for arm in ARMS:
            records = evaluations[arm]["records"]
            current_denominator = {sid: row["held_windows"] for sid, row in records.items()}
            if denominator is None:
                denominator = current_denominator
            elif current_denominator != denominator:
                raise ValueError(f"{panel_name} control denominators differ")
            means = []
            recomputed[arm] = {}
            for sid, row in records.items():
                count = int(row["held_windows"])
                if count <= 0:
                    raise ValueError("record held denominator must be positive")
                raw_absent = analytical_absent.get(sid)
                if (
                    raw_absent is None
                    or raw_absent["held_windows"] != count
                    or not math.isclose(
                        raw_absent["absent_log_score"], row["absent_log_score"], abs_tol=1e-9
                    )
                ):
                    raise ValueError("analytical absent score does not match raw dataset")
                score = row["log_score"] / count
                versus_absent = (row["log_score"] - row["absent_log_score"]) / count
                if not math.isclose(score, row["score_per_window"], abs_tol=1e-12):
                    raise ValueError("record score mean does not recompute")
                if not math.isclose(versus_absent, row["versus_absent_per_window"], abs_tol=1e-12):
                    raise ValueError("record absent contrast does not recompute")
                means.append(versus_absent)
                recomputed[arm][sid] = {
                    "held_windows": count,
                    "score_per_window": score,
                    "versus_absent_per_window": versus_absent,
                }
                if arm in combined_absent:
                    combined_absent[arm][sid] = versus_absent
            if not math.isclose(
                sum(means) / len(means), evaluations[arm]["mean_vs_absent"], abs_tol=1e-12
            ):
                raise ValueError("equal-record absent mean does not recompute")
            exported_sums = {}
            exported_counts = {}
            for lane in evaluations[arm]["lanes"]:
                sid = lane["lane"]["session_id"]
                exported_sums[sid] = exported_sums.get(sid, 0.0) + sum(lane["held_log_scores"])
                exported_counts[sid] = exported_counts.get(sid, 0) + len(lane["held_log_scores"])
            for sid, row in records.items():
                if exported_counts.get(sid) != row["held_windows"] or not math.isclose(
                    exported_sums.get(sid, math.nan), row["log_score"], abs_tol=1e-9
                ):
                    raise ValueError("exported held scores do not sum to record score")
        contrasts = {}
        for left, right in CONTRASTS:
            values = {
                sid: recomputed[left][sid]["score_per_window"]
                - recomputed[right][sid]["score_per_window"]
                for sid in denominator
            }
            stored = panel["contrasts"][f"{left}-{right}"]
            if values != stored["records"] or not math.isclose(
                sum(values.values()) / len(values), stored["mean"], abs_tol=1e-12
            ):
                raise ValueError("stored contrast does not recompute")
            contrasts[f"{left}-{right}"] = {
                "records": values,
                "equal_record_mean": sum(values.values()) / len(values),
            }
            combined_values[f"{left}-{right}"].update(values)
        panels[panel_name] = {
            "record_count": len(denominator),
            "held_windows": denominator,
            "total_held_windows": sum(denominator.values()),
            "analytical_absent": analytical_absent,
            "evaluations": recomputed,
            "contrasts": contrasts,
        }
    combined = {
        "versus_absent": {
            arm: {"records": values, "equal_record_mean": sum(values.values()) / len(values)}
            for arm, values in combined_absent.items()
        },
        "contrasts": {
            name: {"records": values, "equal_record_mean": sum(values.values()) / len(values)}
            for name, values in combined_values.items()
        },
    }
    return {
        "schema": "rx-presence-geometry-result-audit/v1",
        "status": "pass",
        "source_sha256": source_hashes,
        "state_selections": selections,
        "panels": panels,
        "combined_equal_record": combined,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--confirmation", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = {key: sha256(getattr(args, key)) for key in ("pilot", "confirmation", "model")}
    datasets = {
        "pilot": json.loads(args.pilot.read_text()),
        "confirmation": json.loads(args.confirmation.read_text()),
    }
    result = audit(
        json.loads(args.results.read_text()),
        sources,
        datasets,
        json.loads(args.model.read_text()),
    )
    result["results_sha256"] = sha256(args.results)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
