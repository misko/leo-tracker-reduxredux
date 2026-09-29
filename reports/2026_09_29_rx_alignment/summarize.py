"""Independent QR audit and matched-population alignment comparison."""
# ruff: noqa: E501 -- Generated report tables.

import math
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import HERE, ROOT, read, save, verify

CORE = ("median", "constant", "drift", "slope", "both")


def qr_coefficients(x, y):
    q, r = np.linalg.qr(x, mode="reduced")
    return np.linalg.solve(r, q.T @ y)


def main():
    verify(read(HERE / "seal.json")["sha256"])
    assert int((HERE / "exit-code.txt").read_text()) == 0
    plan = read(HERE / "plan.json")
    source = read(ROOT / plan["source"])["scans"]
    results = read(HERE / "result.json")["scans"]
    assert len(source) == len(results) == 72
    all_rows = []
    for scan, result in zip(source, results, strict=True):
        assert result["session_id"] == scan["session_id"] and result["dataset"] == scan["dataset"]
        pairs = sorted(
            [p for p in scan["pairs"] if p["selected"]], key=lambda p: (p["rx0"], p["rx1"])
        )
        assert len(pairs) == len(result["rows"])
        features = []
        for pair, row in zip(pairs, result["rows"], strict=True):
            assert row["rx0"] == pair["rx0"] and row["rx1"] == pair["rx1"]
            assert row["channel"] == pair["channel"] and row["rf_hz"] == pair["rf_hz"]
            m = np.array(pair["training"], bool)
            t = np.array(pair["times_s"])[m]
            y = (np.array(pair["rx0_hz"])[m] + np.array(pair["rx1_hz"])[m]) / 2
            center = float(np.median(t))
            z = (t - center) / 10
            design = np.column_stack([np.ones(len(t)), z, z * z])
            qualified = (
                len(t) >= 5
                and np.ptp(t) >= 5
                and np.linalg.matrix_rank(design) == 3
                and np.linalg.cond(design) <= 1e4
            )
            assert row["feature"]["qualified"] == bool(qualified)
            if qualified:
                c = qr_coefficients(design, y - y.mean())
                f = {
                    "center_s": center,
                    "slope_hz_s": float(c[1] / 10),
                    "acceleration_hz_s2": float(c[2] / 50),
                }
                for name, v in f.items():
                    assert abs(v - row["feature"][name]) < 1e-7
            else:
                f = None
            features.append(f)
        for i, (pair, row) in enumerate(zip(pairs, result["rows"], strict=True)):
            donor_indices = [
                j
                for j, p in enumerate(pairs)
                if j != i and p["channel"] == pair["channel"] and p["rf_hz"] == pair["rf_hz"]
            ]
            assert row["donor_ids"] == [[pairs[j]["rx0"], pairs[j]["rx1"]] for j in donor_indices]
            assert row["held_available"] == pair["evaluation"]["held_available"]
            assert set(row["models"]) == set(plan["models"])
            for name, entry in row["models"].items():
                f = entry["fit"]
                assert f["donors"] == len(donor_indices)
                if len(donor_indices) < 4:
                    assert (
                        not f["qualified"]
                        and f["reason"] == "fewer_than_four_donors"
                        and "held" not in entry
                    )
                    continue
                if any(features[j] is None for j in donor_indices):
                    assert (
                        not f["qualified"]
                        and f["reason"] == "donor_polynomial_unqualified"
                        and "held" not in entry
                    )
                    continue
                t = np.array([features[j]["center_s"] for j in donor_indices])
                s = np.array([features[j]["slope_hz_s"] for j in donor_indices])
                y = np.array([pairs[j]["offset_hz"] for j in donor_indices])
                reference = float(t.mean())
                time = name in ("drift", "both", "drift_permuted")
                slope = name in ("slope", "both", "slope_permuted")
                if name == "drift_permuted":
                    t = np.r_[t[-1], t[:-1]]
                if name == "slope_permuted":
                    s = np.r_[s[-1], s[:-1]]
                columns = [np.ones(len(t))]
                if time:
                    columns.append((t - reference) / 100)
                if slope:
                    columns.append(s / 1000)
                x = np.column_stack(columns)
                if np.linalg.matrix_rank(x) != x.shape[1] or np.linalg.cond(x) > 1000:
                    assert (
                        not f["qualified"]
                        and f["reason"] == "alignment_rank"
                        and "held" not in entry
                    )
                    continue
                b = qr_coefficients(x, y)
                intercept = float(np.median(y)) if name == "median" else float(b[0])
                drift = float(b[1] / 100) if time else 0
                lag = float(b[-1] / 1000) if slope else 0
                for key, v in (
                    ("intercept_hz", intercept),
                    ("drift_hz_s", drift),
                    ("slope_coefficient_s", lag),
                    ("reference_s", reference),
                ):
                    assert abs(v - f[key]) < 1e-6, (scan["session_id"], name, key, v, f[key])
                qualified = abs(drift) <= 20 and abs(lag) <= 5
                assert bool(qualified) == f["qualified"]
                assert f["reason"] == ("qualified" if qualified else "coefficient_bound")
                available = qualified and features[i] is not None and row["held_available"]
                assert ("held" in entry) == bool(available)
                if not available:
                    continue
                held = np.array(pair["held"], bool)
                t = np.array(pair["times_s"])[held]
                target = features[i]
                derivative = target["slope_hz_s"] + target["acceleration_hz_s2"] * (
                    t - target["center_s"]
                )
                prediction = intercept + drift * (t - reference) + lag * derivative
                e = entry["held"]
                np.testing.assert_allclose(prediction, e["prediction_hz"], atol=1e-5, rtol=1e-10)
                residual = np.array(pair["difference_hz"])[held] - np.array(e["prediction_hz"])
                assert e["count"] == len(residual)
                assert float(np.median(abs(residual))) == e["median_abs_hz"]
                assert float(np.quantile(abs(residual), 0.9)) == e["p90_abs_hz"]
                assert e["shape_pass"] == bool(
                    np.median(abs(residual)) <= 100 and np.quantile(abs(residual), 0.9) <= 300
                )
                score = float(
                    np.sum(
                        math.lgamma(2.5)
                        - math.lgamma(2)
                        - 0.5 * math.log(80000 * math.pi)
                        - 2.5 * np.log1p(residual**2 / 80000)
                    )
                )
                assert abs(score - e["log_score"]) < 1e-8
                if name == "median":
                    old = pair["evaluation"]
                    assert old["donor_offset_hz"] == f["intercept_hz"]
                    assert old["donor_held_median_abs_hz"] == e["median_abs_hz"]
                    assert old["donor_held_p90_abs_hz"] == e["p90_abs_hz"]
                    assert old["donor_held_shape_pass"] == e["shape_pass"]
            all_rows.append({"dataset": scan["dataset"], "session_id": scan["session_id"], **row})
    assert len(all_rows) == 913
    aggregates = []
    comparisons = []
    coverage = []
    for ds in ("DS7", "DS8", "DS9"):
        rows = [r for r in all_rows if r["dataset"] == ds]
        common = [r for r in rows if all("held" in r["models"][m] for m in CORE)]
        for m in plan["models"]:
            coverage.append(
                {
                    "dataset": ds,
                    "model": m,
                    "targets": len(rows),
                    "held_available": sum("held" in r["models"][m] for r in rows),
                    "fit_reasons": dict(Counter(r["models"][m]["fit"]["reason"] for r in rows)),
                }
            )
        for m in CORE:
            outcomes = [r["models"][m]["held"] for r in common]
            aggregates.append(
                {
                    "dataset": ds,
                    "model": m,
                    "targets": len(common),
                    "scans": len({r["session_id"] for r in common}),
                    "shape_pass": sum(e["shape_pass"] for e in outcomes),
                    "median_abs_hz": float(np.median([e["median_abs_hz"] for e in outcomes]))
                    if outcomes
                    else None,
                }
            )
        for a, b in (
            ("median", "drift"),
            ("constant", "drift"),
            ("constant", "slope"),
            ("drift", "both"),
            ("drift_permuted", "drift"),
            ("slope_permuted", "slope"),
        ):
            paired = (
                common
                if "permuted" not in a
                else [r for r in rows if "held" in r["models"][a] and "held" in r["models"][b]]
            )
            delta = [
                (r["models"][b]["held"]["log_score"] - r["models"][a]["held"]["log_score"])
                / r["models"][b]["held"]["count"]
                for r in paired
            ]
            comparisons.append(
                {
                    "dataset": ds,
                    "from": a,
                    "to": b,
                    "targets": len(paired),
                    "better": sum(d > 0 for d in delta),
                    "median_change_nats_per_observation": float(np.median(delta))
                    if delta
                    else None,
                }
            )
    save(
        HERE / "summary.json",
        {
            "audit_passed": True,
            "coverage": coverage,
            "common_population": aggregates,
            "comparisons": comparisons,
        },
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for i, m in enumerate(CORE):
        rows = [r for r in aggregates if r["model"] == m]
        axes[0].bar(
            np.arange(3) + (i - 2) * 0.16, [r["median_abs_hz"] for r in rows], width=0.16, label=m
        )
        axes[1].bar(
            np.arange(3) + (i - 2) * 0.16,
            [r["shape_pass"] / r["targets"] for r in rows],
            width=0.16,
            label=m,
        )
    axes[0].axhline(100, color="gray", linestyle="--")
    axes[0].set_ylabel("Median of target held absolute-error medians (Hz)")
    axes[1].set_ylabel("Fraction passing held shape thresholds")
    axes[1].set_ylim(0, 1)
    for ax in axes:
        ax.set_xticks(range(3), ["DS7 (65 targets)", "DS8 (34 targets)", "DS9 (46 targets)"])
        ax.grid(axis="y", alpha=0.2)
    axes[0].legend(fontsize=8, ncol=2)
    fig.suptitle("Matched qualified targets only; 25 of 72 scans represented")
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"alignment.{suffix}", dpi=160)
    plt.close(fig)
    print({"common_population": aggregates, "comparisons": comparisons}, flush=True)


if __name__ == "__main__":
    main()
