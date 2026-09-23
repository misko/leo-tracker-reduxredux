import json
from pathlib import Path

import matplotlib.pyplot as plt

HERE = Path(__file__).parent
x = json.loads((HERE / "sealed/results.json").read_text())
baseline = json.loads(
    (HERE.parent / "2026_09_23_long_training_search_multi/results/results.json").read_text()
)["views"][0]["searches"]
for metric, label, output in [
    ("selected_support_reserved", "Selected-support held capped RMS (Hz)", "selected_support.png"),
    ("all_3s_support_reserved", "Common all-3s held capped RMS (Hz)", "common_support.png"),
    ("reference_error_km", "Post-seal reference error (km)", "reference_error.png"),
]:
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for prior in ("sacramento", "reno"):
        start = next(s["selected"] for s in baseline if s["prior"] == prior)
        baseline_value = start[
            "reference_error_km" if metric == "reference_error_km"
            else "reserved_capped800_rmse_hz"
        ]
        rows = [
            (
                v["minimum_span_s"],
                next(s for s in v["searches"] if s["prior"] == prior)[metric]
                if metric == "reference_error_km" else
                next(s for s in v["searches"] if s["prior"] == prior)[metric]["capped800_rmse_hz"],
            )
            for v in x["variants"]
        ]
        rows.insert(0, (3, baseline_value))
        ax.plot(*zip(*rows, strict=True), marker="o", label=prior)
    ax.set(xlabel="Minimum track span (s)", ylabel=label, xticks=[3, 10, 20, 30])
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(HERE / output, dpi=180)
    plt.close(fig)
