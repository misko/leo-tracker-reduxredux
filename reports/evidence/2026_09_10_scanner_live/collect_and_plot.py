"""Archive this bounded live campaign and plot measured duty/screening, without RF."""

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RUNS = (
    Path("/srv/bulk/leo/scanner-fair-live-20260910.gwClBZ"),
    Path("/srv/bulk/leo/scanner-fair-live-5m-20260910.YkrxOS"),
)
FIGURES = REPO / "reports/figures/2026_09_10_scanner_live"


def main():
    originals, cases = [], []
    for index, root in enumerate(RUNS):
        assert (root / "resumed.json").is_file(), (
            "Do not present unfinished maintenance as restored"
        )
        names = [
            "campaign.py",
            "legacy_recipe.py",
            "before.json",
            "paused.json",
            "resumed.json",
            "identity-preflight.json",
            "failure.json",
            "completed.json",
        ]
        for case in sorted(root.glob("case-*/summary.json")):
            result = json.loads(case.read_bytes())
            result["case_path"] = str(case.parent)
            cases.append(result)
            for name in (
                "summary.json",
                "public-receipt.json",
                "public-glrt.json",
                "preflight.json",
                "postflight.json",
                "attempt.json",
                "capture-result.json",
            ):
                names.append(str(case.parent.relative_to(root) / name))
        for name in names:
            source = root / name
            if not source.is_file():
                continue
            data = source.read_bytes()
            target = HERE / str(index) / (name + ".gz")
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = gzip.compress(data, mtime=0)
            if target.exists():
                assert target.read_bytes() == payload, "Never overwrite original evidence"
            else:
                target.write_bytes(payload)
            originals.append(
                dict(
                    path=str(target.relative_to(HERE)),
                    bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
    FIGURES.mkdir(parents=True, exist_ok=True)
    full = [case for case in cases if not case["smoke"]]
    labels = [
        f"{c['rate_hz'] / 1e6:g} MS/s\n{'adaptive ON' if c['detector_enabled'] else 'fixed OFF'}"
        for c in full
    ]
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.subplots_adjust(bottom=0.24, top=0.88, left=0.10, right=0.98)
    bars = ax.bar(
        labels,
        [c["valid_duty_ppm"] / 10000 for c in full],
        color=["#376b91", "#25997e", "#376b91"][: len(full)],
    )
    ax.bar_label(bars, fmt="%.2f%%", padding=4)
    ax.axhline(90, linestyle="--", color="0.45", label="90% duty target")
    ax.set(
        ylim=(0, 103),
        ylabel="Valid-IQ capture duty (%)",
        title="Real 300-second source spans, unchanged 120 ms dwells",
    )
    ax.legend(loc="lower right")
    fig.text(
        0.5,
        0.025,
        "Sequential changing sky; not an identical-hop sensitivity A/B. "
        "5 MS/s adaptive full run not attempted.",
        ha="center",
        fontsize=8,
    )
    fig.savefig(FIGURES / "live-duty.png", dpi=170)
    plt.close(fig)
    glrt = json.loads((RUNS[0] / "case-2-2500000-on-300s/public-glrt.json").read_bytes())
    receipt = json.loads((RUNS[0] / "case-2-2500000-on-300s/public-receipt.json").read_bytes())
    rows = glrt["evidence"]["results"]
    start = int(receipt["terminal"]["first_counter"])
    times = np.array([(int(r["valid_start"]) - start) / 2500000 for r in rows])
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), layout="constrained", sharex=True)
    for verdict, color in (("starlink", "#25997e"), ("unavailable", "#cf7f35")):
        selected = [i for i, r in enumerate(rows) if r["verdict"] == verdict]
        axes[0].scatter(
            times[selected], [rows[i]["margin"] for i in selected], s=5, color=color, label=verdict
        )
    axes[0].set(
        ylabel="Exact minus control GLRT margin",
        title="RX1 lightweight GLRT: 2.5 MS/s adaptive 300 s live scan",
    )
    axes[0].legend()
    axes[1].scatter(times, [r["wall_ms"] for r in rows], s=5, label="Measured classifier wall time")
    axes[1].axhline(
        120, linestyle="--", color="0.45", label="120 ms dwell (not a hard detector deadline)"
    )
    axes[1].set(xlabel="Device time since scan start (s)", ylabel="Wall time (ms)")
    axes[1].legend()
    fig.savefig(FIGURES / "live-rx1-screening.png", dpi=170)
    plt.close(fig)
    stats = dict(
        cases=cases,
        originals=originals,
        firmware_changed=False,
        expected_boot_id="442b22ea-9ec8-4e90-8c71-8add30d3fc3a",
        glrt_reasons=dict(Counter(r["reason"] for r in rows)),
        wall_ms_percentiles=dict(
            zip(
                ("p50", "p95", "p99", "max"),
                np.percentile([r["wall_ms"] for r in rows], [50, 95, 99, 100]).tolist(),
                strict=True,
            )
        ),
        figures=[
            dict(path=str(p.relative_to(REPO)), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(FIGURES.glob("*.png"))
        ],
    )
    (HERE / "index.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps({key: value for key, value in stats.items() if key != "originals"}, indent=2))


if __name__ == "__main__":
    main()
