"""Apply frozen pilot gates and report frequency fit separately from accuracy."""

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ARMS = ("fitted-c", "zero-c")


def main():
    protocol = json.loads((HERE / "protocol.json").read_text())
    variants = protocol["variants"]
    cases = []
    for label in protocol["cases"]:
        document = json.loads((HERE / "results" / f"{label}.json").read_text())
        row = dict(label=label, arms={})
        for arm in ARMS:
            raw = {r["variant"]: r for r in document["candidates"] if r["arm"] == arm}
            control = (
                raw["control"]
                if raw["control"]["converged"]
                else document["previous_operational"][arm]
            )
            row["arms"][arm] = {}
            for variant in variants:
                candidate = raw[variant]
                selected = candidate if candidate["converged"] else control
                row["arms"][arm][variant] = dict(
                    error_km=selected["error_km"],
                    rms_hz=selected["posterior_rms_hz"],
                    converged=candidate["converged"],
                    raw_error_km=candidate["error_km"],
                    stationarity=candidate["stationarity"],
                    fallback=not candidate["converged"],
                    max_satellite_offset_hz=float(
                        np.max(abs(np.asarray(candidate.get("satellite_offsets_hz", [0]))))
                    ),
                    max_satellite_slope_hz_s=float(
                        np.max(abs(np.asarray(candidate.get("satellite_slopes_hz_s", [0]))))
                    ),
                )
                if arm == "zero-c":
                    assert candidate["vector"][6] == 0
                    assert candidate["rf_drift_coefficients"] == [0, 0]
        cases.append(row)
    metrics = {}
    gates = {}
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    for column, arm in enumerate(ARMS):
        matrix = np.array([[r["arms"][arm][v]["error_km"] for v in variants] for r in cases])
        heat = axes[0, column].imshow(matrix, aspect="auto", cmap="viridis")
        for i, row in enumerate(cases):
            for j, variant in enumerate(variants):
                value = row["arms"][arm][variant]
                axes[0, column].text(
                    j,
                    i,
                    f"{value['error_km']:.3f}" + ("*" if value["fallback"] else ""),
                    ha="center",
                    va="center",
                    color="white",
                )
        axes[0, column].set_xticks(range(len(variants)), variants)
        axes[0, column].set_yticks(range(len(cases)), [r["label"] for r in cases])
        axes[0, column].set_title(f"{arm}: position error (km); * = fallback")
        figure.colorbar(heat, ax=axes[0, column])
        metrics[arm] = {}
        for variant in variants:
            rows = [r["arms"][arm][variant] for r in cases]
            metrics[arm][variant] = dict(
                mean_km=float(np.mean([r["error_km"] for r in rows])),
                worst_km=float(max(r["error_km"] for r in rows)),
                mean_rms_hz=float(np.mean([r["rms_hz"] for r in rows])),
                converged_count=sum(r["converged"] for r in rows),
            )
        axes[1, column].bar(variants, [metrics[arm][v]["mean_rms_hz"] for v in variants])
        axes[1, column].set(
            ylabel="Mean posterior frequency RMS (Hz)", title=f"{arm}: frequency fit"
        )
        axes[1, column].grid(axis="y", alpha=0.2)
    for variant in variants[1:]:
        gates[variant] = dict(
            all_arms_converged=all(r["arms"][a][variant]["converged"] for r in cases for a in ARMS),
            fitted_mean_below_1km=metrics["fitted-c"][variant]["mean_km"] < 1,
            fitted_mean_below_control=metrics["fitted-c"][variant]["mean_km"]
            < metrics["fitted-c"]["control"]["mean_km"],
            per_case_regression_guard=all(
                r["arms"]["fitted-c"][variant]["error_km"]
                <= r["arms"]["fitted-c"]["control"]["error_km"]
                + max(0.25, 0.1 * r["arms"]["fitted-c"]["control"]["error_km"])
                for r in cases
            ),
        )
    selected = next((v for v in variants[1:] if all(gates[v].values())), None)
    figure.savefig(HERE / "pilot-comparison.png", dpi=160)
    summary = dict(
        cases=cases,
        metrics=metrics,
        gates=gates,
        selected=selected,
        scope="Consumed-case mechanism pilot; not fresh validation",
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, indent=2))


if __name__ == "__main__":
    main()
