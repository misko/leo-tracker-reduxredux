"""Plot paired DS26 ALGO06 recovery results against full native GLRT coverage."""

import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr, spearmanr


OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / "2026_11_01_ds24_plus_error_comparison"
MANIFEST = Path("/srv/bulk/leo/research/ds26-20261030/dataset/manifest.json")
SITE = (37.849061591561885, -122.48574968092912)
METHOD = "72h_30s"
FIELDS = (
    "case", "recording_id", "side", "availability", "associated", "total",
    "associated_pct", "added_points", "recovery_status", "fitted_c_error_m",
    "c0_error_m", "algo05_fitted_c_error_m", "algo05_c0_error_m",
)


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def haversine_m(endpoint):
    lat, lon = json.loads(endpoint)
    a, b = map(math.radians, (lat, lon))
    c, d = map(math.radians, SITE)
    h = math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))


def main():
    manifest = json.loads(MANIFEST.read_text())
    roster = {
        f"DS26-{i:04d}": member["recording_id"]
        for i, member in enumerate(manifest["members"], 1)
        if member["recording_id"].startswith("fast8-")
    }
    assert len(roster) == 159
    assert len(set(roster.values())) == len(roster)

    selected = {}
    for row in read_csv(SOURCE / "position-errors.csv"):
        if row["dataset"] != "DS26" or row["method"] not in (METHOD, "ALGO05"):
            continue
        key = (row["case"], row["arm"], row["method"])
        assert key not in selected, key
        assert row["case"] in roster, key
        assert row["arm"] in ("fitted_c", "c0"), key
        associated, total = int(row["associated"]), int(row["total"])
        assert 0 <= associated <= total and total > 0, key
        assert math.isclose(float(row["associated_pct"]), 100 * associated / total, abs_tol=1e-9), key
        assert math.isclose(float(row["error_m"]), haversine_m(row["endpoint_latlon"]), abs_tol=1e-5), key
        selected[key] = row

    features = [r for r in read_csv(SOURCE / "scan-features.csv") if r["dataset"] == "DS26"]
    feature_by_case = {r["case"]: r for r in features}
    assert len(feature_by_case) == len(features) == 148
    cases = {key[0] for key in selected}
    assert cases == set(feature_by_case) and len(cases) == 148
    assert len(selected) == 148 * 2 * 2

    joined = []
    for case, recording_id in roster.items():
        record = dict.fromkeys(FIELDS, "")
        record.update(case=case, recording_id=recording_id,
                      side=recording_id.rsplit("-", 1)[-1],
                      availability="available" if case in cases else "unavailable")
        if case in cases:
            fitted = selected[(case, "fitted_c", METHOD)]
            zero = selected[(case, "c0", METHOD)]
            baseline = selected[(case, "fitted_c", "ALGO05")]
            baseline_zero = selected[(case, "c0", "ALGO05")]
            for arm_row in (zero, baseline, baseline_zero):
                assert arm_row["total"] == fitted["total"], case
            assert fitted["associated"] == zero["associated"], case
            assert fitted["added_points"] == zero["added_points"], case
            assert fitted["status"] == zero["status"], case
            assert int(fitted["associated"]) == int(baseline["associated"]) + int(fitted["added_points"]), case
            assert int(zero["associated"]) == int(baseline_zero["associated"]) + int(zero["added_points"]), case
            feature = feature_by_case[case]
            assert feature["recording_id"] == recording_id, case
            assert feature["side"] == record["side"], case
            assert int(feature["total"]) == int(fitted["total"]), case
            assert int(feature["associated"]) == int(baseline["associated"]), case
            record.update(
                associated=fitted["associated"], total=fitted["total"],
                associated_pct=fitted["associated_pct"],
                added_points=fitted["added_points"], recovery_status=fitted["status"],
                fitted_c_error_m=fitted["error_m"], c0_error_m=zero["error_m"],
                algo05_fitted_c_error_m=baseline["error_m"],
                algo05_c0_error_m=baseline_zero["error_m"],
            )
        joined.append(record)

    with (OUT / "joined-scans.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(joined)

    available = [r for r in joined if r["availability"] == "available"]
    assert len(available) == 148 and len(joined) == 159
    associated = sum(int(r["associated"]) for r in available)
    total = sum(int(r["total"]) for r in available)
    assert (associated, total) == (463453, 650404)
    summary = next(r for r in read_csv(SOURCE / "summary.csv")
                   if (r["dataset"], r["arm"], r["method"]) == ("DS26", "fitted_c", METHOD))
    assert (int(summary["n"]), int(summary["roster"])) == (148, 159)
    assert math.isclose(float(summary["associated_pct"]), 100 * associated / total, abs_tol=1e-9)

    stats = {"cohort": "DS26 fast", "algorithm": "ALGO06 causal residual-family v1",
             "policy": "72h_30s, no recency penalty", "available": len(available),
             "roster": len(joined), "associated": associated, "native_glrt_points": total,
             "point_weighted_association_pct": 100 * associated / total,
             "qualified_recoveries": sum(r["recovery_status"] == "qualified" for r in available),
             "added_points": sum(int(r["added_points"]) for r in available),
             "missing_cases": [r["case"] for r in joined if r["availability"] == "unavailable"]}
    x = np.array([float(r["associated_pct"]) for r in available])
    for arm, column, label, filename in (
        ("fitted_c", "fitted_c_error_m", "Fitted c", "fitted-c.png"),
        ("c0", "c0_error_m", "c = 0", "c-zero.png"),
    ):
        y = np.array([float(r[column]) / 1000 for r in available])
        stats[arm] = {"pearson_r": float(pearsonr(x, y).statistic),
                      "spearman_rho": float(spearmanr(x, y).statistic),
                      "mean_error_m": float(y.mean() * 1000),
                      "median_error_m": float(np.median(y) * 1000),
                      "max_error_m": float(y.max() * 1000),
                      "top_errors": [{"case": available[i]["case"], "error_m": float(y[i] * 1000),
                                      "associated_pct": float(x[i])}
                                     for i in np.argsort(y)[-5:][::-1]]}
        plot(available, x, y, stats[arm], label, filename)

    (OUT / "statistics.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats, indent=2))


def plot(rows, x, y, stats, arm_label, filename):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.dpi": 200})
    fig, ax = plt.subplots(figsize=(9.5, 6.2))
    fig.subplots_adjust(left=0.095, right=0.98, top=0.79, bottom=0.16)
    accepted = np.array([r["recovery_status"] == "qualified" for r in rows])
    ax.scatter(x[~accepted], y[~accepted], s=33, color="#27698c", alpha=0.7,
               edgecolors="none", label=f"Retained ALGO05 position (n={sum(~accepted)})")
    ax.scatter(x[accepted], y[accepted], s=48, color="#d77b28", alpha=0.88,
               edgecolors="white", linewidths=0.45,
               label=f"Qualified ALGO06 recovery (n={sum(accepted)})")
    offsets = [(8, 9), (9, -18), (8, 9), (-43, 8), (9, -16)]
    for i, offset in zip(np.argsort(y)[-5:][::-1], offsets):
        ax.annotate(rows[i]["case"], (x[i], y[i]), xytext=offset,
                    textcoords="offset points", fontsize=8.3, color="#202c38",
                    arrowprops={"arrowstyle": "-", "color": "#727b82", "lw": 0.7})
    ax.set(xlim=(35, 90), ylim=(0, 8), xticks=np.arange(40, 91, 10),
           yticks=np.arange(0, 9, 1), xlabel="Native GLRT points associated (%)",
           ylabel="Position error at evaluation site (km)")
    ax.grid(color="#d9dee2", linewidth=0.7)
    ax.set_axisbelow(True)
    fig.suptitle(f"DS26 fast scans · ALGO06 72 h / ±30 s · {arm_label}",
                 x=0.095, y=0.97, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.095, 0.91, "148 of 159 fast recordings have paired outcomes; 11 unavailable",
             fontsize=9.5, color="#4f5b66")
    ax.text(0.98, 0.97,
            f"Pearson r  {stats['pearson_r']:+.2f}\nSpearman ρ  {stats['spearman_rho']:+.2f}",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            bbox={"facecolor": "white", "edgecolor": "#d9dee2", "boxstyle": "round,pad=0.5"})
    fig.legend(*ax.get_legend_handles_labels(), loc="upper left", bbox_to_anchor=(0.095, 0.885),
               ncol=2, frameon=False, fontsize=9)
    fig.text(0.095, 0.025, "One dot per available scan · full native GLRT denominator · no recency penalty",
             fontsize=8.6, color="#56616b")
    fig.savefig(OUT / filename)
    plt.close(fig)


if __name__ == "__main__":
    main()
