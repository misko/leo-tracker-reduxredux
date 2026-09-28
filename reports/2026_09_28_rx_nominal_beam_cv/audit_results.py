"""Independent arithmetic, isolation, and MAP audit for nominal-beam CV folds."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import expit

from tools.rx_causal_geometry_cv import training_reception_document
from tools.rx_joint_geometry_fit import BETA_SD, calibration_score
from tools.rx_nominal_beam import beam_features, fit_shared_beam_scale
from tools.rx_nominal_beam_cv import prepare_five_record_training
from tools.rx_orbit_increment import attach_orbit_increment

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATASET = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
ARMS = ("D", "E", "B")
CONTROLS = (
    "B_swap",
    "B_geometry_reverse",
    "B_geometry_permute",
    "B_zero_motion",
    "B_reverse_motion",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected, atol=1e-8):
    if not math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=atol):
        raise AssertionError(f"{actual!r} != {expected!r}")


def penalty(parameters, dimension):
    theta = np.asarray(parameters, dtype=float)
    value = 0.5 * float(np.sum((theta[:dimension] / BETA_SD[:dimension]) ** 2))
    value += 0.5 * (theta[-2] / 2.0) ** 2
    value += 0.5 * (theta[-1] / 1.5) ** 2
    return value


def score_audit(evaluation):
    by_role = {}
    for role in ("reception", "held_frequency"):
        rows = [
            window
            for lane in evaluation["lanes"]
            for window in lane["windows"]
            if window["role"] == role
        ]
        reported = evaluation["roles"][role]
        relative = math.fsum(row["relative_log_score"] for row in rows)
        reference = math.fsum(row["reference_log_score"] for row in rows)
        close(relative, reported["relative_log_score"])
        close(reference, reported["reference_log_score"])
        close(relative + reference, reported["full_log_score"])
        if len(rows) != reported["windows"]:
            raise AssertionError("role window denominator mismatch")
        for key, total in (
            ("relative_log_score_per_window", relative),
            ("reference_log_score_per_window", reference),
            ("full_log_score_per_window", relative + reference),
        ):
            close(reported[key], total / len(rows), 1e-10)
        by_role[role] = {
            "windows": len(rows),
            "relative_per_window": relative / len(rows),
            "reference_per_window": reference / len(rows),
        }
    return by_role


def main():
    dataset_bytes = DATASET.read_bytes()
    document = json.loads(dataset_bytes)
    sessions = sorted(
        {
            lane["lane"]["session_id"]
            for lane in document["lanes"]
            if lane["recording_split"] == "calibration"
        }
    )
    if len(sessions) != 6:
        raise AssertionError("audit expected six calibration sessions")
    folds = []
    optimizer_starts = 0
    all_converged = True
    aggregates = {
        role: {name: [] for name in (*ARMS, *CONTROLS)}
        for role in ("reception", "held_frequency")
    }
    for index, expected_session in enumerate(sessions):
        result_path = HERE / f"fold-{index}.json"
        result = json.loads(result_path.read_text())
        launch = json.loads((HERE / f"corrected-fold-{index}-launch.json").read_text())
        if (HERE / f"corrected-fold-{index}-exit-code.txt").read_text().strip() != "0":
            raise AssertionError("nonzero corrected fold exit")
        for relative, expected in launch["sha256"].items():
            if digest(ROOT / relative) != expected:
                raise AssertionError(f"launch-bound source changed: {relative}")
        if result["dataset_sha256"] != digest(DATASET):
            raise AssertionError("dataset hash mismatch")
        if result["fold"] != index or result["held_session"] != expected_session:
            raise AssertionError("fold/session ordering mismatch")
        expected_training = sorted(set(sessions) - {expected_session})
        if result["training_sessions"] != expected_training:
            raise AssertionError("training membership mismatch")
        if set(result["training_source_window_ids"]) & set(result["held_source_window_ids"]):
            raise AssertionError("training and held source windows overlap")

        restricted = training_reception_document(document, expected_session)
        prepared = prepare_five_record_training(restricted)
        expected_ids = sorted(row["window_id"] for row in prepared["rows"])
        if result["training_source_window_ids"] != expected_ids:
            raise AssertionError("persisted training window IDs do not reconstruct")
        if result["background_model"] != prepared["background"]:
            raise AssertionError("persisted fold background does not reconstruct")
        np.testing.assert_allclose(result["feature_center"], prepared["center"], rtol=0, atol=0)
        np.testing.assert_allclose(result["feature_scale"], prepared["scale"], rtol=0, atol=0)
        orbit, _ = attach_orbit_increment(prepared["uniform"])
        scale = fit_shared_beam_scale(orbit)
        close(scale, result["beam_scale"], 1e-12)
        e_lanes = beam_features(orbit, scale, tilt_deg=0.0)
        b_lanes = beam_features(orbit, scale, tilt_deg=10.0)

        fit_summary = {}
        for arm, dimension, lanes in (("D", 3, e_lanes), ("E", 4, e_lanes), ("B", 4, b_lanes)):
            fit = result["fits"][arm]
            if len(fit["candidates"]) != 2:
                raise AssertionError("expected two optimizer starts per arm")
            for candidate in fit["candidates"]:
                optimizer_starts += 1
                all_converged &= bool(candidate["success"])
                theta = np.asarray(candidate["parameters"], dtype=float)
                observed = calibration_score(
                    lanes,
                    theta[:dimension],
                    float(expit(theta[-2])),
                    math.exp(theta[-1]),
                )
                close(observed, candidate["calibration_relative_log_evidence"], 1e-7)
                expected_penalty = penalty(theta, dimension)
                close(expected_penalty, candidate["map_penalty"], 1e-7)
                close(observed - expected_penalty, candidate["map_gain"], 1e-7)
            selected = fit["selected"]
            if selected["null_selected"]:
                if selected["map_gain"] != 0.0:
                    raise AssertionError("null selection has nonzero MAP gain")
            else:
                best = max(
                    (c for c in fit["candidates"] if c["success"]),
                    key=lambda c: c["map_gain"],
                )
                close(selected["map_gain"], best["map_gain"], 1e-8)
            fit_summary[arm] = {
                "slope": selected["beta"][3] if dimension == 4 else None,
                "tau_s": selected["tau_s"],
                "null_selected": selected["null_selected"],
            }

        role_scores = {}
        for name in (*ARMS, *CONTROLS):
            role_scores[name] = score_audit(result["evaluations"][name])
            for role in aggregates:
                aggregates[role][name].append(role_scores[name][role]["relative_per_window"])
        # Reference and exact window population must be common to every arm/control.
        base_windows = {
            (row["source_window_id"], row["role"]): row["reference_log_score"]
            for lane in result["evaluations"]["B"]["lanes"]
            for row in lane["windows"]
        }
        for name in (*ARMS, *CONTROLS):
            controlled = {
                (row["source_window_id"], row["role"]): row["reference_log_score"]
                for lane in result["evaluations"][name]["lanes"]
                for row in lane["windows"]
            }
            if controlled != base_windows:
                raise AssertionError(f"reference/window population changed for {name}")
        folds.append({
            "fold": index,
            "held_session": expected_session,
            "training_sessions": expected_training,
            "beam_scale": scale,
            "fits": fit_summary,
            "roles": role_scores,
            "result_sha256": digest(result_path),
        })

    if optimizer_starts != 36 or not all_converged:
        raise AssertionError("optimizer completion mismatch")
    summary = {}
    for role, values in aggregates.items():
        means = {name: math.fsum(scores) / 6 for name, scores in values.items()}
        comparisons = {}
        for left, right in (
            ("E", "D"), ("B", "D"), ("B", "E"), ("B", "B_swap"),
            ("B", "B_geometry_reverse"), ("B", "B_geometry_permute"),
            ("B", "B_zero_motion"), ("B", "B_reverse_motion"),
        ):
            paired = [a - b for a, b in zip(values[left], values[right], strict=True)]
            comparisons[f"{left}_minus_{right}"] = {
                "mean": math.fsum(paired) / 6,
                "positive": sum(value > 0 for value in paired),
                "negative": sum(value < 0 for value in paired),
                "per_record": paired,
            }
        summary[role] = {"means": means, "comparisons": comparisons}
    output = {
        "schema": "rx-nominal-beam-cv-independent-audit/v1",
        "status": "pass",
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "optimizer_starts": optimizer_starts,
        "all_optimizer_starts_converged": all_converged,
        "audited_source_sha256": {
            str(path.relative_to(ROOT)): digest(path)
            for path in (
                Path(__file__),
                ROOT / "tools/rx_nominal_beam.py",
                ROOT / "tools/rx_nominal_beam_cv.py",
                HERE / "PROTOCOL.md",
            )
        },
        "folds": folds,
        "aggregate": summary,
    }
    target = HERE / "audit-results.json"
    with target.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
