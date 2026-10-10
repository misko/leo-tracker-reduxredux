"""Sealed-result arithmetic and figures only; no estimator calls."""

import hashlib
import itertools
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def wilson(k, n):
    z = 1.959963984540054
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [float(max(0, c - h)), float(min(1, c + h))]


def metrics(rows):
    if not rows:
        return None
    e = np.array([r["error_hz"] for r in rows])
    bins, counts = np.unique([int(round(r["estimated_bin"])) for r in rows], return_counts=True)
    return {
        "n": len(rows),
        "bias_hz": float(e.mean()),
        "rms_hz": float(np.sqrt(np.mean(e * e))),
        "extra_bin_count": sum(abs(r["estimated_bin"]) > 0.5 for r in rows),
        "histogram": list(zip(bins.tolist(), counts.tolist(), strict=True)),
    }


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    result = json.loads((HERE / "result.json").read_text())
    assert (
        result["protocol_sha256"]
        == hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    )
    for path, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    rows = result["rows"]
    keys = ["phases_bins", "amplitudes", "cutoffs_s", "seeds"]
    assert len(rows) == result["native_calls"] == 480 and result["status"] == "complete"
    assert {(r["phase_bins"], r["amplitude"], r["cutoff_s"], r["seed"]) for r in rows} == set(
        itertools.product(*(plan[k] for k in keys))
    )
    for r in rows:
        assert abs(r["error_hz"] - (r["estimated_hz"] - r["injected_hz"])) < 1e-12
        assert r["passed"] == (r["margin"] >= 0.025)
        assert abs(r["estimated_bin"] - round(r["estimated_bin"])) < 1e-10
    groups = []
    for a, c, p in itertools.product(plan["amplitudes"], plan["cutoffs_s"], plan["phases_bins"]):
        group = [r for r in rows if (r["amplitude"], r["cutoff_s"], r["phase_bins"]) == (a, c, p)]
        admitted = [r for r in group if r["passed"]]
        groups.append(
            {
                "amplitude": a,
                "cutoff_s": c,
                "phase_bins": p,
                "passed": len(admitted),
                "wilson95": wilson(len(admitted), 16),
                "all": metrics(group),
                "admitted": metrics(admitted),
            }
        )
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
    for row, a in enumerate(plan["amplitudes"]):
        for c, color in zip(plan["cutoffs_s"], ["#b84d23", "#1972a0", "#398149"], strict=True):
            gs = [g for g in groups if g["amplitude"] == a and g["cutoff_s"] == c]
            x = [g["phase_bins"] for g in gs]
            ys = [
                [g["passed"] / 16 for g in gs],
                [
                    g["admitted"]["extra_bin_count"] / g["passed"] if g["passed"] else np.nan
                    for g in gs
                ],
                [g["admitted"]["rms_hz"] if g["passed"] else np.nan for g in gs],
            ]
            for j, y in enumerate(ys):
                axes[row, j].plot(x, y, "o-", color=color, label=f"Off at {c * 1000:g} ms")
        for j, title in enumerate(
            [
                "Margin-pass fraction",
                "Nonzero-bin fraction among passes",
                "CFO error RMS among passes (Hz)",
            ]
        ):
            axes[row, j].set(
                title=f"Amplitude {a}\n{title}", xlabel="Injected frequency / grid step"
            )
            axes[row, j].grid(alpha=0.2)
            if j < 2:
                axes[row, j].set_ylim(-0.05, 1.05)
        axes[row, 0].legend(fontsize=8)
    fig.suptitle(
        "Synthetic conditioned native GLRT · 16 shared seeds per cell · missing = no passes"
    )
    fig.savefig(HERE / "offgrid.png", dpi=160)
    plt.close(fig)
    elapsed = np.array([r["elapsed_s"] for r in rows])
    summary = {
        "groups": groups,
        "rows": 480,
        "failures": 0,
        "verified_sources": len(plan["source_sha256"]),
        "native_seconds": float(elapsed.sum()),
        "native_median_ms": float(np.median(elapsed) * 1000),
        "native_max_ms": float(elapsed.max() * 1000),
        "sha256": {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in ["protocol.json", "result.json", "native.so.build.json", "native.so"]
        },
    }
    assert summary["sha256"]["native.so"] == result["library_sha256"]
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2))
    table = [
        "# All 30 synthetic cells",
        "",
        "Every row contains 16 seeds. Extra-bin means a nonzero returned bin; all injected "
        "phases lie strictly inside bin0's nearest-bin cell. Bias/RMS in Hz. Missing "
        "admitted metrics are undefined, never zero-filled.",
        "",
        "| Amplitude | Off ms | Phase / Delta | Passes | Wilson95 | "
        "Extra-bin all / admitted | Admitted bias / RMS |",
        "|---:|---:|---:|---:|---|---|---|",
    ]
    for g in groups:
        m = g["admitted"]
        ci = g["wilson95"]
        error_text = f"{m['bias_hz']:.1f} / {m['rms_hz']:.1f}" if m else "—"
        table.append(
            f"| {g['amplitude']} | {g['cutoff_s'] * 1000:g} | {g['phase_bins']:g} | "
            f"{g['passed']}/16 | {ci[0]:.3f}–{ci[1]:.3f} | "
            f"{g['all']['extra_bin_count']} / {m['extra_bin_count'] if m else '—'} | {error_text} |"
        )
    (HERE / "ALL_CELLS.md").write_text("\n".join(table) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "groups"}, indent=2))


if __name__ == "__main__":
    main()
