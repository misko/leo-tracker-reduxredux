"""Read-only arithmetic over sealed results; no estimator or reconstruction."""

import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VARIANTS = ["baseline", "logparabola_hz", "newton_hz"]


def errors(rows, variant):
    return np.array(
        [
            (r["baseline"]["estimated_hz"] if variant == "baseline" else r["refined"][variant])
            - r["baseline"]["injected_hz"]
            for r in rows
        ]
    )


def metrics(rows):
    if not rows:
        return None
    baseline = abs(errors(rows, "baseline"))
    out = {}
    for variant in VARIANTS:
        e = errors(rows, variant)
        delta = abs(e) - baseline
        out[variant] = {
            "n": len(rows),
            "bias_hz": float(e.mean()),
            "rms_hz": float(np.sqrt(np.mean(e * e))),
            "p95_abs_hz": float(np.percentile(abs(e), 95)),
            "worst_abs_hz": float(max(abs(e))),
            "regressions_gt_1hz": int(sum(delta > 1)),
            "improvements_gt_1hz": int(sum(delta < -1)),
            "worst_absolute_error_increase_hz": float(max(delta)),
        }
    return out


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    d = json.loads((HERE / "result.json").read_text())
    assert d["protocol_sha256"] == hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    old_raw = (ROOT / plan["baseline_result"]).read_bytes()
    assert hashlib.sha256(old_raw).hexdigest() == plan["baseline_sha256"]
    old = json.loads(old_raw)["rows"]
    rows = d["rows"]
    assert d["status"] == "complete" and len(rows) == d["native_calls"] == 480
    assert [r["baseline"] for r in rows] == old
    groups = []
    for a, c, p in itertools.product([0.25, 1], [0.00015, 0.001, 0.02], [-0.4, -0.2, 0, 0.2, 0.4]):
        rs = [
            r
            for r in rows
            if (r["baseline"]["amplitude"], r["baseline"]["cutoff_s"], r["baseline"]["phase_bins"])
            == (a, c, p)
        ]
        assert len(rs) == 16
        groups.append(
            {
                "amplitude": a,
                "cutoff_s": c,
                "phase_bins": p,
                "all": metrics(rs),
                "admitted": metrics([r for r in rs if r["baseline"]["passed"]]),
            }
        )
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
    for i, a in enumerate([0.25, 1]):
        for j, c in enumerate([0.00015, 0.001, 0.02]):
            gs = [g for g in groups if g["amplitude"] == a and g["cutoff_s"] == c]
            for v, label, color in zip(
                VARIANTS,
                ["Original bin", "Log parabola", "3-step Newton"],
                ["#555555", "#176b9a", "#b55321"],
                strict=True,
            ):
                axes[i, j].plot(
                    [g["phase_bins"] for g in gs],
                    [g["admitted"][v]["rms_hz"] if g["admitted"] else np.nan for g in gs],
                    "o-",
                    color=color,
                    label=label,
                )
            axes[i, j].set(
                title=f"Amplitude {a}; off at {c * 1000:g} ms",
                xlabel="Injected frequency / bin",
                ylabel="Passed-only CFO RMS (Hz)",
            )
            axes[i, j].grid(alpha=0.2)
            if not any(g["admitted"] for g in gs):
                axes[i, j].text(
                    0.5,
                    0.5,
                    "No admitted measurements",
                    ha="center",
                    transform=axes[i, j].transAxes,
                )
    axes[0, 1].legend(fontsize=8)
    fig.suptitle(
        "Synthetic one-peak refinement · original admission unchanged · consumed122 inputs"
    )
    fig.savefig(HERE / "refinement.png", dpi=160)
    plt.close(fig)
    summary = {
        "complete": True,
        "rows": 480,
        "parity_failures": 0,
        "verified_sources": len(plan["source_sha256"]),
        "all": metrics(rows),
        "admitted": metrics([r for r in rows if r["baseline"]["passed"]]),
        "groups": groups,
        "fallback_reasons": {
            key: dict(Counter(r["refined"][key] for r in rows))
            for key in ["logparabola_reason", "newton_reason"]
        },
        "timings": {
            key: {
                "sum_s": sum(r[key] for r in rows),
                "median_ms": float(np.median([r[key] for r in rows]) * 1000),
            }
            for key in ["native_seconds", "python_correlation_seconds", "python_refinement_seconds"]
        },
        "sha256": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in ["protocol.json", "result.json", "native.so.build.json", "native.so"]
        },
    }
    seed_groups = []
    for seed in range(122000, 122016):
        selected = [r for r in rows if r["baseline"]["seed"] == seed and r["baseline"]["passed"]]
        m = metrics(selected)
        seed_groups.append(
            {
                "seed": seed,
                "n": len(selected),
                "metrics": m,
                "rms_gain_hz": {v: m["baseline"]["rms_hz"] - m[v]["rms_hz"] for v in VARIANTS[1:]},
            }
        )
    summary["seed_groups"] = seed_groups
    summary["seed_rms_gain_dispersion"] = {}
    for v in VARIANTS[1:]:
        gains = np.array([g["rms_gain_hz"][v] for g in seed_groups])
        summary["seed_rms_gain_dispersion"][v] = {
            "mean_hz": float(gains.mean()),
            "sample_sd_hz": float(gains.std(ddof=1)),
            "minimum_hz": float(gains.min()),
            "maximum_hz": float(gains.max()),
            "positive_seed_groups": int(sum(gains > 0)),
        }
    assert summary["sha256"]["native.so"] == d["library_sha256"]
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2))
    lines = [
        "# All30 phase cells, original admission",
        "",
        "Regressions/improvements mean absolute-error change exceeding1Hz, descriptive only. "
        "All unconditional metrics and fallback reasons are in summary.json. "
        "No admitted rows are silently replaced.",
        "",
        "| Amplitude | Off ms | Phase | n admitted | Original RMS | "
        "Parabola RMS (regressions) | Newton RMS (regressions) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in groups:
        m = g["admitted"]
        values = [
            f"{m[v]['rms_hz']:.2f} ({m[v]['regressions_gt_1hz']})" if m else "—" for v in VARIANTS
        ]
        lines.append(
            f"| {g['amplitude']} | {g['cutoff_s'] * 1000:g} | {g['phase_bins']} | "
            f"{m['baseline']['n'] if m else 0} | " + " | ".join(values) + " |"
        )
    (HERE / "ALL_CELLS.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "groups"}, indent=2))


if __name__ == "__main__":
    main()
