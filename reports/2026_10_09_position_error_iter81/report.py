"""Score-select eligible original/retry fits before evaluating reference errors."""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import error_km, read  # noqa: E402

from leo.contracts.regional_position import RegionalPrior  # noqa: E402


def main():
    original = []
    for path in sorted((REPORTS / "2026_10_09_position_error_iter71/results").glob("*.json")):
        row = read(path)
        original.append(dict(name=path.name, priority=0, arm=row["arm"], fit=row["fit"]))
    new = []
    for path in sorted((HERE / "retries").glob("*.json")):
        row = read(path)
        new.append(dict(name=path.name, priority=1, arm=row["arm"], fit=row["fit"]))
    assert len(original) == 882 and len(new) == 6
    selected = {}
    for arm in ("fitted-c", "zero-c"):
        selected[arm] = {}
        for name, rows in (("before", original), ("after", original + new)):
            eligible = [r for r in rows if r["arm"] == arm and r["fit"]["converged"]]
            selected[arm][name] = min(
                eligible, key=lambda r: (r["fit"]["objective"], r["priority"], r["name"])
            )
    # Reference coordinates become relevant only after winner selection.
    prior = RegionalPrior()
    reference = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    for rows in selected.values():
        for row in rows.values():
            row["error_km"] = error_km(prior, row["fit"]["vector"], reference)
    for row in new:
        row["error_km"] = error_km(prior, row["fit"]["vector"], reference)
    summary = dict(
        selected=selected, retries=new, raw_failures=sum(not r["fit"]["converged"] for r in new)
    )
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for ax, arm in zip(axes, ("fitted-c", "zero-c"), strict=True):
        rows = selected[arm]
        bars = ax.bar(
            list(rows), [r["error_km"] for r in rows.values()], color=("gray", "tab:green")
        )
        ax.bar_label(bars, labels=[f"{r['error_km']:.3f}" for r in rows.values()])
        ax.set(title=arm, ylabel="Score-selected position error, km", ylim=(0, 5.2))
        ax.axhline(1, color="black", linestyle="--", linewidth=0.7)
    fig.savefig(HERE / "recovery.png", dpi=170)
    plt.close(fig)
    print(
        {
            a: {
                n: (
                    r["name"],
                    r["error_km"],
                    r["fit"]["objective"],
                    r["fit"]["stationarity"],
                    r["fit"]["posterior_rms_hz"],
                )
                for n, r in rows.items()
            }
            for a, rows in selected.items()
        }
    )


if __name__ == "__main__":
    main()
