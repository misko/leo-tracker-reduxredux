"""Explain the changed Sacramento incumbent using already-sealed evidence only."""

import json
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure


def main():
    root = Path(__file__).resolve().parent
    old = json.loads((root / "canary-status.json").read_text())["manifest"]["document"]
    new = json.loads((root / "v2-canary/document.json").read_text())
    assert old["evidence_sha256"] == new["evidence_sha256"]
    result = {"session_id": new["session_id"], "comparisons": {}}
    figure = Figure(figsize=(13, 5), layout="constrained")
    axes = figure.subplots(1, 2)
    for axis, prior in zip(axes, ("sacramento", "reno"), strict=True):
        before = {x["track_id"]: x for x in old["diagnostics"]["selected_track_scores"][prior]}
        after = {x["track_id"]: x for x in new["diagnostics"]["selected_track_scores"][prior]}
        assert before.keys() == after.keys()
        total_weight = sum(x["weight_s"] for x in before.values())
        rows = []
        for key, a in before.items():
            b = after[key]
            assert a["weight_s"] == b["weight_s"]

            def capped(x):
                return min(x["heldout_rms_hz"], 800) if x["heldout_rms_hz"] is not None else 800

            rows.append(
                dict(
                    track_id=key,
                    weight_s=a["weight_s"],
                    old_candidate=a["candidate_id"],
                    new_candidate=b["candidate_id"],
                    old_tau_s=a["tau_s"],
                    new_tau_s=b["tau_s"],
                    old_rms_hz=a["heldout_rms_hz"],
                    new_rms_hz=b["heldout_rms_hz"],
                    weighted_mse_change_hz2=(capped(b) ** 2 - capped(a) ** 2)
                    * a["weight_s"]
                    / total_weight,
                )
            )
        rows.sort(key=lambda x: abs(x["weighted_mse_change_hz2"]), reverse=True)
        delta = sum(x["weighted_mse_change_hz2"] for x in rows)
        pa = next(x for x in old["priors"] if x["name"] == prior)
        pb = next(x for x in new["priors"] if x["name"] == prior)
        expected = (
            pb["selected"]["capped_weighted_rmse_hz"] ** 2
            - pa["selected"]["capped_weighted_rmse_hz"] ** 2
        )
        assert np.isclose(delta, expected, atol=1e-8)
        result["comparisons"][prior] = dict(
            tracks=len(rows),
            changed_identity_count=sum(x["old_candidate"] != x["new_candidate"] for x in rows),
            changed_tau_count=sum(x["old_tau_s"] != x["new_tau_s"] for x in rows),
            old_score_hz=pa["selected"]["capped_weighted_rmse_hz"],
            new_score_hz=pb["selected"]["capped_weighted_rmse_hz"],
            old_reference_error_km=pa["selected"]["horizontal_error_m"] / 1000,
            new_reference_error_km=pb["selected"]["horizontal_error_m"] / 1000,
            weighted_mse_change_hz2=delta,
            tracks_by_absolute_contribution=rows,
        )
        shown = rows[:12]
        axis.barh(
            range(len(shown)),
            [x["weighted_mse_change_hz2"] for x in shown],
            color=[
                "tab:blue" if x["weighted_mse_change_hz2"] <= 0 else "tab:orange" for x in shown
            ],
        )
        axis.set_yticks(range(len(shown)), [x["track_id"][-8:] for x in shown])
        axis.invert_yaxis()
        axis.axvline(0, color="black", linewidth=0.7)
        axis.set(
            title=prior.title(),
            xlabel="Contribution to new − old weighted MSE (Hz²)",
            ylabel="Track suffix",
        )
        axis.grid(axis="x", alpha=0.2)
        if all(x["weighted_mse_change_hz2"] == 0 for x in rows):
            axis.set_yticks([])
            axis.text(
                0.5,
                0.5,
                "All 34 tracks unchanged\nSame associations, fitted time shifts, and RMS",
                transform=axis.transAxes,
                ha="center",
                va="center",
                bbox={"facecolor": "white", "edgecolor": "none"},
            )
    figure.suptitle(
        "Same scan and estimator · selected-cell changes after Sacramento radius 500 → 250 km\n"
        "Negative means a better selection score; it does not establish a more accurate position"
    )
    figure.savefig(root / "v2-canary/score-contributions.png", dpi=150)
    (root / "v2-canary/score-contributions.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: {a: b for a, b in v.items() if a != "tracks_by_absolute_contribution"}
                for k, v in result["comparisons"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
