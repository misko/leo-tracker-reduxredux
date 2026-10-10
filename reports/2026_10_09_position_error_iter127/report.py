"""Read-only new-noise replication summary, using125's reporting metrics."""

import hashlib
import importlib.util
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
spec = importlib.util.spec_from_file_location(
    "metrics125", HERE.parent / "2026_10_09_position_error_iter125/report.py"
)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    d = json.loads((HERE / "result.json").read_text())
    assert d["protocol_sha256"] == hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    rows = d["rows"]
    assert d["status"] == "complete" and len(rows) == d["native_calls"] == 480
    assert rows == [json.loads(line) for line in (HERE / "rows.jsonl").read_text().splitlines()]
    keys = ["phases_bins", "amplitudes", "cutoffs_s", "seeds"]
    actual = {
        (
            r["baseline"]["phase_bins"],
            r["baseline"]["amplitude"],
            r["baseline"]["cutoff_s"],
            r["baseline"]["seed"],
        )
        for r in rows
    }
    assert actual == set(itertools.product(*(plan[k] for k in keys)))
    groups = []
    for a, c, p in itertools.product(plan["amplitudes"], plan["cutoffs_s"], plan["phases_bins"]):
        rs = [
            r
            for r in rows
            if (r["baseline"]["amplitude"], r["baseline"]["cutoff_s"], r["baseline"]["phase_bins"])
            == (a, c, p)
        ]
        groups.append(
            {
                "amplitude": a,
                "cutoff_s": c,
                "phase_bins": p,
                "all": old.metrics(rs),
                "admitted": old.metrics([r for r in rs if r["baseline"]["passed"]]),
            }
        )
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
    for i, a in enumerate(plan["amplitudes"]):
        for j, c in enumerate(plan["cutoffs_s"]):
            gs = [g for g in groups if g["amplitude"] == a and g["cutoff_s"] == c]
            for v, label in zip(
                old.VARIANTS, ["Original bin", "Log parabola", "3-step Newton"], strict=True
            ):
                axes[i, j].plot(
                    [g["phase_bins"] for g in gs],
                    [g["admitted"][v]["rms_hz"] if g["admitted"] else np.nan for g in gs],
                    "o-",
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
    fig.suptitle("New127 noise seeds · fixed125 refinements · unchanged original admission")
    fig.savefig(HERE / "replication.png", dpi=160)
    plt.close(fig)
    seed_groups = []
    for seed in plan["seeds"]:
        m = old.metrics(
            [r for r in rows if r["baseline"]["seed"] == seed and r["baseline"]["passed"]]
        )
        seed_groups.append(
            {
                "seed": seed,
                "metrics": m,
                "rms_gain_hz": {
                    v: m["baseline"]["rms_hz"] - m[v]["rms_hz"] for v in old.VARIANTS[1:]
                },
            }
        )
    summary = {
        "complete": True,
        "rows": 480,
        "parity_failures": 0,
        "verified_sources": len(plan["source_sha256"]),
        "all": old.metrics(rows),
        "admitted": old.metrics([r for r in rows if r["baseline"]["passed"]]),
        "groups": groups,
        "seed_groups": seed_groups,
        "seed_rms_gain_dispersion": {},
        "fallback_reasons": {
            k: dict(Counter(r["refined"][k] for r in rows))
            for k in ["logparabola_reason", "newton_reason"]
        },
        "timings": {
            k: {
                "sum_s": sum(r[k] for r in rows),
                "median_ms": float(np.median([r[k] for r in rows]) * 1000),
            }
            for k in ["native_seconds", "python_correlation_seconds", "python_refinement_seconds"]
        },
        "sha256": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in [
                "protocol.json",
                "result.json",
                "rows.jsonl",
                "native.so.build.json",
                "native.so",
            ]
        },
    }
    for v in old.VARIANTS[1:]:
        gain = np.array([s["rms_gain_hz"][v] for s in seed_groups])
        summary["seed_rms_gain_dispersion"][v] = {
            "mean_hz": float(gain.mean()),
            "sample_sd_hz": float(gain.std(ddof=1)),
            "min_hz": float(gain.min()),
            "max_hz": float(gain.max()),
            "positive_groups": int(sum(gain > 0)),
        }
    assert summary["sha256"]["native.so"] == d["library_sha256"]
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2))
    lines = [
        "# All30 new-noise phase cells",
        "",
        "Original admission unchanged. Metrics are admitted-only; unconditional metrics "
        "and16 seed groups are in summary.json. Regressions count absolute-error increases "
        "greater than1Hz, descriptive only.",
        "",
        "| Amplitude | Off ms | Phase | n | Original RMS | Parabola RMS (regressions) | "
        "Newton RMS (regressions) |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in groups:
        m = g["admitted"]
        values = [
            f"{m[v]['rms_hz']:.2f} ({m[v]['regressions_gt_1hz']})" if m else "—"
            for v in old.VARIANTS
        ]
        lines.append(
            f"| {g['amplitude']} | {g['cutoff_s'] * 1000:g} | {g['phase_bins']} | "
            f"{m['baseline']['n'] if m else 0} | "
            + " | ".join(values)
            + " |"
        )
    (HERE / "ALL_CELLS.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in ["groups", "seed_groups"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
