"""Report native-Hz differences of frozen RF-scaled receiver/band calibrations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from compare_dsx01_graph_receivers import ROOT, write_csv
from prototype_multilane_tracklets import GROUP_LABELS, OUTPUT, PERIOD, save_figure

RELATIONS = (
    ("RX2 - RX1, low", 2, 0),
    ("RX2 - RX1, high", 3, 1),
    ("High - low, RX1", 1, 0),
    ("High - low, RX2", 3, 2),
)


def main():
    rows, nodes, inputs = [], [], {}
    previous_path = ROOT / "reports/2026_10_17_dsx01_receiver_model/results.json"
    previous = json.loads(previous_path.read_text())
    inputs[str(previous_path.relative_to(ROOT))] = hashlib.sha256(
        previous_path.read_bytes()
    ).hexdigest()
    for source in (f"S{i:02}" for i in range(1, 6)):
        path = OUTPUT / "rf_scaled" / source / "results.json"
        inputs[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        calibration = json.loads(path.read_text())["calibration"]
        beta = np.array(calibration["beta"])
        a, drift = beta[:4], beta[4:] / 150
        groups = {g["group"]: g for g in calibration["groups"]}
        for g in groups.values():
            np.testing.assert_allclose(a[g["group"]], g["offset_at_150s_hz"])
            np.testing.assert_allclose(drift[g["group"]], g["drift_hz_s"])
            nodes.append({"source_id": source, **g})
        for name, minuend, subtrahend in RELATIONS:
            offset, slope = (
                float(a[minuend] - a[subtrahend]),
                float(drift[minuend] - drift[subtrahend]),
            )
            caveats = []
            for g in (groups[minuend], groups[subtrahend]):
                if not g["calibration_supported"]:
                    cause = (
                        "drift bound active"
                        if g["drift_bound_active"]
                        else "sparse calibration coverage"
                    )
                    caveats.append(f"{g['label']}: {cause}")
            historical, mismatch = None, None
            if (minuend, subtrahend) in ((2, 0), (3, 1)):
                bank = "CH1-4" if minuend == 2 else "CH5-8"
                old = next(
                    (
                        g
                        for g in previous["selected_calibration"]
                        if g["source_id"] == source and g["bank"] == bank
                    ),
                    None,
                )
                if old:
                    historical = old["offset_at_150s_hz"]
                    mismatch = float((offset - historical + PERIOD / 2) % PERIOD - PERIOD / 2)
                    if abs(mismatch) > 3000:
                        caveats.append("disagrees with earlier weak single-channel offset mode")
            rows.append(
                {
                    "source_id": source,
                    "relationship": name,
                    "minuend": GROUP_LABELS[minuend],
                    "subtrahend": GROUP_LABELS[subtrahend],
                    "offset_at_150s_hz": offset,
                    "relative_drift_hz_s": slope,
                    "offset_at_0s_hz": offset - 150 * slope,
                    "offset_at_300s_hz": offset + 150 * slope,
                    "prototype_calibration_checks_pass": all(
                        groups[g]["calibration_supported"] for g in (minuend, subtrahend)
                    ),
                    "caveats": "; ".join(caveats),
                    "earlier_same_channel_offset_hz": historical,
                    "difference_from_earlier_offset_hz": mismatch,
                }
            )
        # Four-node cycle closure independently checks signs and ordering.
        relevant = rows[-4:]
        for field in ("offset_at_150s_hz", "relative_drift_hz_s"):
            np.testing.assert_allclose(
                relevant[1][field] - relevant[0][field],
                relevant[3][field] - relevant[2][field],
                atol=1e-9,
            )
    write_csv(OUTPUT / "learned-shifts.csv", rows)
    write_csv(OUTPUT / "learned-calibration-nodes.csv", nodes)
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    palette = plt.get_cmap("tab10")
    for index, (name, _, _) in enumerate(RELATIONS):
        ax = axes.flat[index]
        for i, row in enumerate(r for r in rows if r["relationship"] == name):
            times = np.array([0, 150, 300])
            values = row["offset_at_150s_hz"] + row["relative_drift_hz_s"] * (times - 150)
            ax.plot(
                times,
                values / 1000,
                color=palette(i),
                label=row["source_id"],
                linestyle="--" if row["caveats"] else "-",
                lw=1.7,
            )
            ax.scatter(150, row["offset_at_150s_hz"] / 1000, color=palette(i), s=18)
        ax.set(
            title=name,
            xlabel="Seconds into the individual scan",
            ylabel="Hardware-term difference (kHz)",
            xlim=(0, 300),
        )
        ax.grid(alpha=0.2)
        ax.legend(fontsize=8)
    fig.suptitle(
        "RF-scaled prototype · scan-specific learned hardware-term differences\n"
        "Dashed: weak/bound-limited or prior-mode disagreement; "
        "not a complete cross-channel CFO correction"
    )
    save_figure(fig, OUTPUT, "learned-shifts")
    provenance = {
        "input_sha256": inputs,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "offset_reference_time_s": 150,
        "alias_period_hz": PERIOD,
        "interpretation": "Subtract additive native-Hz hardware terms before RF scaling; "
        "selected alias/calibration mode, not independent physical hardware calibration.",
    }
    (OUTPUT / "learned-shifts-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    for path, expected in inputs.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    print("Wrote 20 pairwise shifts, 20 node coordinates, plots and verified cycle closure.")


if __name__ == "__main__":
    main()
