"""Replay batch-fit objectives with scalar log-domain HMM and audit score arithmetic."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import expit

from tools.rx_paired_state_cv import controlled, prepare_fold
from tools.rx_paired_state_model import BETA_SD, score_lane

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def close(a, b, tolerance=1e-7):
    assert math.isclose(float(a), float(b), rel_tol=0, abs_tol=tolerance), (a, b)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    dataset = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
    document = json.loads(dataset.read_bytes())
    audited = []
    starts, converged, windows_checked = 0, 0, 0
    for fold in range(6):
        assert (HERE / f"fold-{fold}-exit-code.txt").read_text().strip() == "0"
        result_path = HERE / f"fold-{fold}.json"
        result = json.loads(result_path.read_text())
        assert result["dataset_sha256"] == digest(dataset)
        launch = json.loads((HERE / f"fold-{fold}-launch.json").read_text())
        for path, expected in launch["sha256"].items():
            assert digest(ROOT / path) == expected, path
        training, held, receipt = prepare_fold(document, fold)
        for key, value in receipt.items():
            assert result[key] == value, key
        # Check exact membership directly, independently of preparation helper.
        raw_training = [
            w
            for lane in document["lanes"]
            if lane["recording_split"] == "calibration"
            and lane["lane"]["session_id"] != result["held_session"]
            for w in lane["windows"]
            if w["role"] == "reception"
        ]
        assert (
            sorted(w["source_window_id"] for w in raw_training)
            == receipt["training_source_window_ids"]
        )
        categories = [
            int(bool(w["observed"]["rx0"])) + 2 * int(bool(w["observed"]["rx1"]))
            for w in raw_training
        ]
        expected_bg = (np.bincount(categories, minlength=4) + 0.5) / (len(categories) + 2)
        np.testing.assert_array_equal(expected_bg, result["background"])
        for fit in result["fits"].values():
            dimension = len(fit["selected"]["beta"])
            for candidate in fit["candidates"]:
                starts += 1
                converged += int(candidate["success"])
                theta = np.array(candidate["parameters"])
                selected = {
                    "beta": theta[:dimension],
                    "occupancy": float(expit(theta[-2])),
                    "tau_s": math.exp(theta[-1]),
                }
                score = math.fsum(
                    math.fsum(score_lane(lane, selected)["relative_log_scores"])
                    for lane in training
                )
                penalty = 0.5 * np.sum((theta[:dimension] / BETA_SD[:dimension]) ** 2)
                penalty += 0.5 * (theta[-2] / 2) ** 2 + 0.5 * (theta[-1] / 1.5) ** 2
                close(score, candidate["calibration_relative_log_evidence"])
                close(penalty, candidate["map_penalty"])
                close(score - penalty, candidate["map_gain"])
            best = max((c for c in fit["candidates"] if c["success"]), key=lambda c: c["map_gain"])
            close(fit["selected"]["map_gain"], max(0, best["map_gain"]))
            if not fit["selected"]["null_selected"]:
                np.testing.assert_allclose(
                    fit["selected"]["beta"], best["parameters"][:dimension], rtol=0, atol=0
                )
                close(fit["selected"]["occupancy"], expit(best["parameters"][-2]))
                close(fit["selected"]["tau_s"], math.exp(best["parameters"][-1]))
        for name, evaluation in result["evaluations"].items():
            lanes = held if name in ("P", "U", "O") else controlled(held, name)
            selected = result["fits"][name if name in ("P", "U", "O") else "O"]["selected"]
            rows = []
            for lane, exported in zip(lanes, evaluation["lanes"], strict=True):
                replay = score_lane(lane, selected)
                assert exported["lane"] == lane["lane"]
                assert [r["source_window_id"] for r in exported["windows"]] == lane["ids"]
                for key in ("relative", "reference", "full"):
                    np.testing.assert_allclose(
                        [r[key + "_log_score"] for r in exported["windows"]],
                        replay[key + "_log_scores"],
                        rtol=0,
                        atol=1e-12,
                    )
                np.testing.assert_allclose(
                    np.sum(exported["state_posteriors"], axis=1), 1, rtol=0, atol=1e-12
                )
                rows.extend(exported["windows"])
                windows_checked += len(exported["windows"])
            for role, total in evaluation["roles"].items():
                subset = [r for r in rows if r["role"] == role]
                assert total["windows"] == len(subset)
                for key in ("relative_log_score", "reference_log_score", "full_log_score"):
                    value = math.fsum(r[key] for r in subset)
                    close(value, total[key])
                    close(value / len(subset), total[key + "_per_window"])
        audited.append({"fold": fold, "result_sha256": digest(result_path)})
    output = {
        "status": "pass",
        "optimizer_starts": starts,
        "converged_starts": converged,
        "window_scores_replayed": windows_checked,
        "folds": audited,
        "audit_source_sha256": digest(Path(__file__)),
        "scope": ("Independent scalar HMM recurrence vs batched fitting; "
                  "shared emissions and preparation."),
    }
    with (HERE / "audit-results.json").open("x") as stream:
        json.dump(output, stream, indent=2)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
