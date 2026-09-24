"""Plot the retained long-dwell phase artifact with explicit per-source R cut."""

import json
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parents[2]
    source = root / "reports/figures/2026_09_16_dual_rx_pilot_phase/105915-coherent-pilot-20ms.json"
    artifact = json.loads(source.read_text())
    rows = [
        w
        for w in artifact["windows"]
        if w["both_qualified"] and all(t.get("resultant_length", 0) > 0.8 for t in w["tracks"])
    ]
    out = root / "reports/figures/2026_09_24_long_dwell_threshold"
    out.mkdir(exist_ok=True)
    fig, axs = plt.subplots(2, 1, figsize=(13, 8), constrained_layout=True)
    for ax in axs:
        ax.scatter(
            [w["center_s"] for w in rows],
            [w["differential_phase_deg"] for w in rows],
            s=9,
            alpha=0.6,
            color="tab:red",
            label=f"Channel 4 upper · {len(rows)} windows",
        )
        ax.set(
            ylabel="Saved two-source phase difference (degrees)",
            xlabel="Time since capture start (s)",
        )
        ax.grid(alpha=0.2)
        ax.legend()
    axs[0].set(xlim=(0, 60), ylim=(-180, 180), title="Full 60-second recording")
    axs[0].axvspan(*artifact["interval_s"], color="tab:red", alpha=0.08)
    axs[0].text(
        1,
        135,
        "Saved phase extraction only covers the shaded interval; blank regions are unmeasured",
    )
    axs[1].set(xlim=artifact["interval_s"], title="Zoom: complete saved two-source overlap")
    fig.suptitle(
        "Long dwell: both source resultants R > 0.8 and both sources qualified\n"
        "20 ms windows, 10 ms stride · saved model-restored phase · no new fit"
    )
    fig.savefig(out / "phase-R08-full-dwell.png", dpi=160)
    summary = dict(
        capture=artifact["capture"],
        available_windows=len(artifact["windows"]),
        selected_windows=len(rows),
        interval_s=artifact["interval_s"],
        criterion="both_qualified and both per-source resultant_length > 0.8",
        points=[
            dict(
                time_s=w["center_s"],
                phase_deg=w["differential_phase_deg"],
                minimum_source_R=min(t["resultant_length"] for t in w["tracks"]),
            )
            for w in rows
        ],
    )
    (out / "points.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{len(rows)}/{len(artifact['windows'])} selected")


if __name__ == "__main__":
    main()
