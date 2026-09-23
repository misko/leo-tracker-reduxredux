"""Verify saved samples and reproduce figures without the radio corpus."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE / "result.json").read_text())
    assert result["source_digests_before_compute"] == result["source_digests_after_compute"]
    rows = result["results"]
    specs = [
        ("uniform_model_tau_refit", "model_tau_refit_heldout_rms_hz",
         "Synthetic, time offset refitted"),
        ("uniform_model_fixed_anchor_tau", "model_fixed_anchor_tau_heldout_rms_hz",
         "Synthetic, time offset fixed"),
        ("uniform_measured", "measured_heldout_rms_hz", "Recorded data"),
    ]
    for row in rows:
        for key, raw_key, _ in specs:
            samples = np.asarray([
                [np.inf if value is None else value for value in track[raw_key]]
                for track in row["raw_uniform_by_track"]
            ])
            np.testing.assert_allclose(
                np.percentile(samples[np.isfinite(samples)], 90),
                row[key]["pooled_rms"]["p90_hz"],
            )
            np.testing.assert_allclose(
                np.mean(samples < 200.), row[key]["coverage"]["pooled_track_survival_fraction"]
            )
            np.testing.assert_allclose(
                np.mean(np.all(samples < 200., axis=0)),
                row[key]["coverage"]["all_tracks_survive_fraction"],
            )
    spacings = [row["spacing_km"] for row in rows]
    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    for key, _, label in specs:
        ax.plot(spacings, [row[key]["pooled_rms"]["p90_hz"] for row in rows], "o-", label=label)
    ax.axhline(200, color="black", ls="--", label="200 Hz cutoff")
    ax.set(xscale="log", yscale="log", xlabel="Grid spacing (km)",
           ylabel="90th-percentile RMS (Hz)",
           title="Grid-spacing sensitivity · ten fixed satellite hypotheses")
    ax.set_xticks(spacings, [str(value) for value in spacings])
    ax.grid(alpha=.3)
    ax.legend()
    fig.savefig(HERE / "rms_p90_vs_spacing.png", dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5), constrained_layout=True)
    for key, _, label in (specs[0], specs[2]):
        for metric, style, suffix in (
            ("pooled_track_survival_fraction", "o-", "individual track trials"),
            ("all_tracks_survive_fraction", "s--", "all ten together"),
        ):
            ax.plot(spacings, [100 * row[key]["coverage"][metric] for row in rows], style,
                    label=f"{label}: {suffix}")
    ax.set(xscale="log", xlabel="Grid spacing (km)",
           ylabel="Trials below 200 Hz (%)", ylim=(0, 105),
           title="Survival across 32 sampled placements within a cell")
    ax.set_xticks(spacings, [str(value) for value in spacings])
    ax.grid(alpha=.3)
    ax.legend(fontsize=8)
    fig.savefig(HERE / "survival_vs_spacing.png", dpi=180)
    plt.close(fig)
    manifest = json.loads((HERE / "manifest.json").read_text())
    manifest["receipt_files"] = {
        str(path.relative_to(HERE)): "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(HERE.rglob("*"))
        if path.is_file() and path.name != "manifest.json" and "__pycache__" not in path.parts
    }
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
