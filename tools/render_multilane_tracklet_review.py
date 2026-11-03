"""Render review tables and the largest multi-lane group from frozen fits."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_dsx01_graph_receivers import load_tracks, write_csv
from numpy.polynomial import legendre as leg
from prototype_multilane_tracklets import OUTPUT, observation_arrays, save_figure


def main():
    tracks, _ = load_tracks()
    mapping = {t["key"]: t for t in tracks}
    calibration, groups, choices, hashes = [], [], [], {}
    for method in ("direct_cfo", "rf_scaled"):
        for path in sorted((OUTPUT / method).glob("S*/results.json")):
            hashes[str(path.relative_to(OUTPUT))] = hashlib.sha256(path.read_bytes()).hexdigest()
            r = json.loads(path.read_text())
            c, source = r["calibration"], r["source_id"]
            for g in c["groups"]:
                calibration.append(
                    {
                        "method": method,
                        "source_id": source,
                        **g,
                        "core_rms_hz": c["core_rms_hz"],
                        "anchor_pairs": c["anchor_pairs"],
                        "normal_rank": c["data_normal_rank"],
                    }
                )
            for i, f in enumerate(r["result"]["merged_groups"]):
                groups.append(
                    {
                        "method": method,
                        "source_id": source,
                        "group_index": i,
                        "fragments": len(f["members"]),
                        "lanes": len(f["diagnostics"]) - 1,
                        "points": f["points"],
                        "start_s": f["start_s"],
                        "end_s": f["end_s"],
                        "degree": f["degree"],
                        "rms_native_hz": f["rms_hz"],
                        "fully_supported": f["fully_supported"],
                        "calibration_supported": f["calibration_supported"],
                        "members": ";".join(f["members"]),
                    }
                )
                if method == "rf_scaled":
                    choices.append(
                        (len(f["diagnostics"]) - 1, len(f["members"]), f["points"], f, c)
                    )
    write_csv(OUTPUT / "calibration.csv", calibration)
    write_csv(OUTPUT / "merged-groups.csv", groups)
    _, _, _, fit, cal = max(choices, key=lambda v: v[:3])
    a = observation_arrays(fit["members"], mapping, np.array(cal["beta"]), True)
    pred = leg.legval(
        (a["t"] - fit["reference_time_s"]) / fit["time_scale_s"], fit["coefficients_hz"]
    )
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.5), constrained_layout=True)
    for j, (rx, ch) in enumerate(sorted(set(zip(a["rx"], a["ch"], strict=True)))):
        mask = (a["rx"] == rx) & (a["ch"] == ch)
        color = plt.get_cmap("tab10")(j)
        for col, y in enumerate(
            (a["original_y"] / 1000, a["y"] / a["q"] / 1000, a["y"] - a["q"] * pred)
        ):
            axes[col].scatter(
                a["t"][mask],
                y[mask],
                s=21,
                c=[color],
                alpha=0.85,
                marker="o" if rx == 1 else "^",
                label=f"RX{rx} CH{ch}",
            )
    t = np.linspace(fit["start_s"], fit["end_s"], 300)
    curve = leg.legval((t - fit["reference_time_s"]) / fit["time_scale_s"], fit["coefficients_hz"])
    axes[1].plot(t, curve / 1000, color="#333333", lw=1.2)
    axes[2].axhline(0, color="#666666", lw=0.8)
    for i, title in enumerate(
        (
            "Original lifted GLRT CFO",
            "Shared curve after calibration + RF scaling",
            f"Original-Hz residuals · RMS {fit['rms_hz']:.0f} Hz",
        )
    ):
        axes[i].set(
            title=title, xlabel="Seconds into scan", ylabel="Residual Hz" if i == 2 else "CFO kHz"
        )
        axes[i].grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    axes[2].set_ylim(-500, 500)
    fig.suptitle(
        f"{cal['source_id']} · {len(fit['members'])} Graph fragments across "
        f"{len(fit['diagnostics']) - 1} RX/channel lanes and both bands\n"
        f"All {fit['points']} original points retained · provisional short-lane support · "
        "no offset fitted per join"
    )
    save_figure(fig, OUTPUT, "seven-lane-example")
    (OUTPUT / "seven-lane-example-selection.json").write_text(
        json.dumps(
            {
                "source_id": cal["source_id"],
                "members": fit["members"],
                "points": fit["points"],
                "rms_native_hz": fit["rms_hz"],
            },
            indent=2,
        )
        + "\n"
    )
    (OUTPUT / "render-provenance.json").write_text(
        json.dumps(
            {
                "input_sha256": hashes,
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            },
            indent=2,
        )
        + "\n"
    )
    print("Rendered calibration/group tables and largest shared-curve example.")


if __name__ == "__main__":
    main()
