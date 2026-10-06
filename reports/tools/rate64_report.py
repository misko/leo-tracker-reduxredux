import argparse
import collections
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser(description="Reproduce the frozen 64+64 scan rate comparison.")
parser.add_argument("--input", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
src = args.input
out = args.output
out.mkdir(parents=True, exist_ok=True)
rows = json.loads((src / "metrics.json").read_text())
selection = {r["session_id"]: r for r in json.loads((src / "selection.json").read_text())}
assert len(rows) == 128 and collections.Counter(r["rate"] for r in rows) == {
    2500000: 64,
    10000000: 64,
}
for r in rows:
    s = selection[r["session_id"]]
    r["gain"] = s["recorded_manual_gain_db"]
    r["duration"] = s["nominal_duration_seconds"]
spec = [
    ("glrt", "pass_fraction", 100),
    ("glrt", "winner_margin_median", 1),
    ("glrt", "passed_candidates", 1),
    ("tracking", "tracklets", 1),
    ("tracking", "observations", 1),
    ("tracking", "long_tracks", 1),
    ("tracking", "median_span", 1),
    ("tracking", "median_rms", 1),
    ("tracking", "review_eval_rms", 1),
    ("tracking", "review_fit_rms", 1),
]
summary = {}
rng = np.random.default_rng(20261006)
strata = sorted(set((r["edge"], r["gain"], r["duration"]) for r in rows))
print(
    "strata",
    [
        (
            g,
            [
                sum((r["edge"], r["gain"], r["duration"]) == g and r["rate"] == rate for r in rows)
                for rate in (2500000, 10000000)
            ],
        )
        for g in strata
    ],
)
for sec, key, scale in spec:
    values = {
        rate: np.array(
            [r[sec][key] * scale for r in rows if r["rate"] == rate and r[sec][key] is not None]
        )
        for rate in (2500000, 10000000)
    }
    diffs = []
    weights = []
    means = []
    for g in strata:
        v = {
            rate: np.array(
                [
                    r[sec][key] * scale
                    for r in rows
                    if r["rate"] == rate
                    and (r["edge"], r["gain"], r["duration"]) == g
                    and r[sec][key] is not None
                ]
            )
            for rate in (2500000, 10000000)
        }
        if any(not len(a) for a in v.values()):
            continue
        samples = {
            rate: rng.choice(a, size=(20000, len(a)), replace=True).mean(axis=1)
            for rate, a in v.items()
        }
        weight = min(map(len, v.values()))
        diffs.append(samples[10000000] - samples[2500000])
        weights.append(weight)
        means.append([v[2500000].mean(), v[10000000].mean()])
    diff = np.average(diffs, axis=0, weights=weights)
    result = dict(
        means={rate: float(a.mean()) for rate, a in values.items()},
        medians={rate: float(np.median(a)) for rate, a in values.items()},
        adjusted_means=np.average(means, axis=0, weights=weights).tolist(),
        adjusted_difference=float(np.diff(np.average(means, axis=0, weights=weights))[0]),
        ci95=np.quantile(diff, [0.025, 0.975]).tolist(),
    )
    summary[key] = result
    print(key, result)
for rate in (2500000, 10000000):
    a = [r for r in rows if r["rate"] == rate]
    print(
        "COUNTS",
        rate,
        {
            k: sum(r["tracking"][k] for r in a)
            for k in [
                "reviews",
                "review_eval_below100",
                "review_eval_below500",
                "hypotheses",
                "no_abstention",
                "leader_persists",
                "beats_radio_null",
                "review_deferred",
            ]
        },
    )
    print("DUTY", rate, np.mean([r["duty"] for r in a]))
    for edge in ("lower", "upper"):
        b = [r for r in a if r["edge"] == edge]
        print(
            "EDGE",
            rate,
            edge,
            len(b),
            {
                key: round(np.mean([r[sec][key] * scale for r in b if r[sec][key] is not None]), 4)
                for sec, key, scale in spec
            },
        )
(out / "summary.json").write_text(
    json.dumps(
        dict(
            seed=20261006,
            bootstrap_replicates=20000,
            strata=strata,
            weighting="minimum rate count per shared edge/gain/duration stratum",
            metrics=summary,
        ),
        indent=2,
    )
)


# Sensitivity comparison: greedily pair closest capture times, without reusing
# scans, requiring matching edge/gain/duration and at most 90 minutes separation.
def epoch(r):
    return datetime.fromisoformat(r["captured_at"].replace("Z", "+00:00")).timestamp()


low = [r for r in rows if r["rate"] == 2500000]
high = [r for r in rows if r["rate"] == 10000000]
options = sorted(
    (abs(epoch(a) - epoch(b)), i, j)
    for i, a in enumerate(low)
    for j, b in enumerate(high)
    if (a["edge"], a["gain"], a["duration"]) == (b["edge"], b["gain"], b["duration"])
)
usedlow = set()
usedhigh = set()
pairs = []
for gap, i, j in options:
    if gap > 5400:
        break
    if i in usedlow or j in usedhigh:
        continue
    usedlow.add(i)
    usedhigh.add(j)
    pairs.append((low[i], high[j], gap))
paired = {}
for sec, key, scale in spec:
    a = np.array([lo[sec][key] * scale for lo, hi, gap in pairs])
    b = np.array([hi[sec][key] * scale for lo, hi, gap in pairs])
    d = b - a
    if any(v is None for v in d):
        continue
    ci = np.quantile(rng.choice(d, size=(20000, len(d)), replace=True).mean(axis=1), [0.025, 0.975])
    paired[key] = dict(
        low_mean=float(a.mean()),
        high_mean=float(b.mean()),
        difference=float(d.mean()),
        ci95=ci.tolist(),
    )
print("PAIRS", len(pairs), "median_gap_minutes", np.median([p[2] for p in pairs]) / 60)
for k in ("pass_fraction", "long_tracks", "review_eval_rms", "observations"):
    print("PAIRED", k, paired[k])
(out / "time-matched.json").write_text(
    json.dumps(
        dict(
            maximum_gap_minutes=90,
            seed=20261006,
            pairs=[
                dict(low=a["session_id"], high=b["session_id"], gap_seconds=g) for a, b, g in pairs
            ],
            metrics=paired,
        ),
        indent=2,
    )
)
plots = [
    ("glrt", "pass_fraction", "Probes with a GLRT pass (%)", 100),
    ("tracking", "long_tracks", "Tracklets lasting ≥30 seconds", 1),
    ("tracking", "observations", "Observations in tracklets", 1),
    ("tracking", "review_eval_rms", "Median orbital evaluation RMS (Hz)", 1),
]
fig, axs = plt.subplots(2, 2, figsize=(11, 8), layout="constrained")
colors = {"lower": "#197a9a", "upper": "#cc7c29"}
for ax, (sec, key, title, scale) in zip(axs.flat, plots, strict=True):
    for x, rate in enumerate((2500000, 10000000)):
        for edge, dx in [("lower", -0.14), ("upper", 0.14)]:
            vals = [
                r[sec][key] * scale
                for r in rows
                if r["rate"] == rate and r["edge"] == edge and r[sec][key] is not None
            ]
            jitter = rng.uniform(-0.055, 0.055, len(vals))
            ax.scatter(
                x + dx + jitter,
                vals,
                color=colors[edge],
                s=18,
                alpha=0.65,
                label=edge.title() + " edge" if x == 0 else None,
            )
            ax.plot([x + dx - 0.075, x + dx + 0.075], [np.mean(vals)] * 2, color=colors[edge], lw=3)
    ax.set(
        xticks=[0, 1],
        xticklabels=["2.5 MS/s (64 scans)", "10 MS/s (64 scans)"],
        title=title,
        xlim=(-0.4, 1.4),
    )
    ax.grid(axis="y", alpha=0.2)
axs[0, 0].legend(fontsize=9)
fig.suptitle(
    "128 recent completed scans — GLRT and satellite tracking\n"
    "One dot per scan; bars are edge-specific means. Different passes, not paired captures.",
    fontsize=13,
)
fig.savefig(out / "comparison.png", dpi=180)
with (out / "per-scan.csv").open("w") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(
        [
            "session_id",
            "rate_MSps",
            "edge",
            "gain_dB",
            "duration_s",
            "captured_Pacific",
            "duty_percent",
            "GLRT_passing_probe_percent",
            "median_winner_margin",
            "tracklets",
            "track_observations",
            "tracks_30s_plus",
            "median_orbital_evaluation_RMS_Hz",
            "reviewed_tracks",
            "reviewed_tracks_under_100Hz",
        ]
    )
    for r in rows:
        g, t = r["glrt"], r["tracking"]
        w.writerow(
            [
                r["session_id"],
                r["rate"] / 1e6,
                r["edge"],
                r["gain"],
                r["duration"],
                datetime.fromisoformat(r["captured_at"].replace("Z", "+00:00"))
                .astimezone(ZoneInfo("America/Los_Angeles"))
                .isoformat(),
                100 * r["duty"],
                100 * g["pass_fraction"],
                g["winner_margin_median"],
                t["tracklets"],
                t["observations"],
                t["long_tracks"],
                t["review_eval_rms"],
                t["reviews"],
                t["review_eval_below100"],
            ]
        )
