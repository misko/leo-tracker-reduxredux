"""Frozen-finalist sensitivity to removing/resampling whole scans; not outer CV."""
import json
import sys
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools/research"))
from sixteen_joint_compare import score_location


def main():
    out = Path(__file__).resolve().parent
    points = json.loads((out / "common_finalists.json").read_text())
    scans = json.loads((out.parent / "2026_09_23_sixteen_scan_position_resolution/scans.json").read_text())
    scores = np.zeros((16, len(points)))
    weights = np.zeros(16)
    for i, scan in enumerate(scans):
        for j, point in enumerate(points):
            value = score_location(out / "joint/cache", [scan["session_id"]],
                                   point["latitude_deg"], point["longitude_deg"])
            weights[i] = sum(track.weight_s for track in value.tracks)
            scores[i, j] = value.weighted_mse_hz2
    totals = np.sum(scores*weights[:, None], axis=0)
    full = np.sqrt(totals/weights.sum())
    leave_one_out = np.sqrt((totals[None, :] - scores*weights[:, None]) /
                            (weights.sum()-weights)[:, None])
    rng = np.random.default_rng(92316)
    draws = rng.integers(0, 16, (1000, 16))
    sampled = np.sqrt(np.sum(scores[draws]*weights[draws, None], axis=1)/
                      np.sum(weights[draws], axis=1)[:, None])
    wins = np.bincount(np.argmin(sampled, axis=1), minlength=len(points))
    result = dict(scope="Frozen candidates and finalist set discovered using all scans; scan-removal/resampling sensitivity, not independent cross-validation or calibrated posterior",
        locations=points, session_ids=[s["session_id"] for s in scans],
        per_scan_weight=weights.tolist(), per_scan_mse_hz2=scores.tolist(),
        full_rms_hz=full.tolist(), leave_one_scan_out_rms_hz=leave_one_out.tolist(),
        leave_one_scan_out_winner=np.argmin(leave_one_out, axis=1).tolist(),
        bootstrap_seed=92316, bootstrap_draws=1000, bootstrap_winner_count=wins.tolist())
    (out / "stability.json").write_text(json.dumps(result, indent=2)+"\n")
    fig = Figure(figsize=(12, 4.5), layout="constrained")
    axes = fig.subplots(1, 2)
    labels = [p["location_id"].replace("_coordinate_mean", " mean").replace("joint_basin_", "basin ") for p in points]
    delta = leave_one_out - leave_one_out.min(axis=1)[:, None]
    image = axes[0].imshow(delta, aspect="auto", cmap="viridis_r")
    axes[0].set(xticks=np.arange(len(points)), xticklabels=labels,
                xlabel="Fixed finalist", ylabel="Omitted chronological scan index",
                title="Score above best after removing one scan")
    axes[0].tick_params(axis="x", rotation=30)
    fig.colorbar(image, ax=axes[0], label="RMS difference (Hz)")
    axes[1].bar(np.arange(len(points)), wins/10, color="#267b9f")
    axes[1].set(xticks=np.arange(len(points)), xticklabels=labels, ylabel="Selected in scan resampling (%)",
                title="Ranking stability, not position confidence")
    axes[1].tick_params(axis="x", rotation=30)
    fig.savefig(out / "stability.png", dpi=160)
    print(json.dumps({k:result[k] for k in ("full_rms_hz", "leave_one_scan_out_winner", "bootstrap_winner_count")}, indent=2))


if __name__ == "__main__":
    main()
