"""Build reproducible tables and figures from a fixed-window adaptive audit."""

# Narrative paragraphs are kept intact for the generated Markdown report.
# ruff: noqa: E501

import argparse
import csv
import gzip
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def median(values):
    values = [v for v in values if v is not None and np.isfinite(v)]
    return float(np.median(values)) if values else None


def fmt(value):
    return "—" if value is None else f"{value:,.2f}"


def eligibility(track):
    short = track["span_s"] < 7
    sparse = track["observation_count"] < 14
    return (
        "short+sparse"
        if short and sparse
        else "short"
        if short
        else "sparse"
        if sparse
        else "eligible"
    )


def table(headers, rows):
    return "\n".join(
        ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
        + ["| " + " | ".join(map(str, row)) + " |" for row in rows]
    )


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build(input_dir, output):
    output.mkdir(parents=True, exist_ok=True)
    sessions = [json.loads(p.read_text()) for p in sorted(input_dir.glob("scan-*.json"))]
    summary = json.loads((input_dir / "summary.json").read_text())
    sessions.sort(key=lambda s: s.get("created_utc_ns", 0))
    tracks, candidates, reviews, ledger = [], [], [], []
    for s in sessions:
        p = s.get("tracking", {}).get("product") or {}
        rate = s.get("sample_rate_hz", 0) / 1e6
        base = {"session_id": s["session_id"], "rate_msps": rate}
        by_id = {t["tracklet_id"]: t for t in p.get("tracklets", [])}
        for t in by_id.values():
            row = {
                **base,
                "tracklet_id": t["tracklet_id"],
                "channel": t["channel"],
                "edge": t["edge"],
                "span_s": (t["end_utc_ns"] - t["start_utc_ns"]) / 1e9,
                "observation_count": t["observation_count"],
                "local_rms_hz": t["residual_rms_hz"],
                "rate_hz_s": t["normalized_rate_hz_per_s"],
            }
            row["eligibility"] = eligibility(row)
            tracks.append(row)
        for c in p.get("tle_candidates", []):
            t = by_id.get(c["representative_tracklet_id"], {})
            candidates.append(
                {
                    **base,
                    "group_id": c["physical_group_id"],
                    "tracklet_id": c["representative_tracklet_id"],
                    "channel": t.get("channel"),
                    "edge": t.get("edge"),
                    "span_s": c["support_span_s"],
                    "norad": c["leading_catalog_number"],
                    "accepted": not c["abstention_recommended"],
                    "reasons": ";".join(c["abstention_reasons"]),
                    "tau_s": c["selected_tau_s"],
                    "evaluation_rank": c["training_leader_heldout_rank"],
                    "runner_nll_margin": c["heldout_runner_negative_log_score_margin"],
                    "nominal_nll": c["nominal_heldout_negative_log_score"],
                    "radio_null_nll": c["radio_null_heldout_negative_log_score"],
                    "minus500_nll": c["wrong_time_minus_500_heldout_negative_log_score"],
                    "plus500_nll": c["wrong_time_plus_500_heldout_negative_log_score"],
                }
            )
        for r in p.get("track_reviews", []):
            top = r["candidates"][0] if r["candidates"] else {}
            runner = r["candidates"][1] if len(r["candidates"]) > 1 else {}
            match = next(
                (
                    c
                    for c in p.get("tle_candidates", [])
                    if c["representative_tracklet_id"] == r["tracklet_id"]
                ),
                None,
            )
            a, b = (
                top.get("randomized_evaluation_rms_hz"),
                runner.get("randomized_evaluation_rms_hz"),
            )
            reviews.append(
                {
                    **base,
                    "tracklet_id": r["tracklet_id"],
                    "channel": r["channel"],
                    "edge": r["edge"],
                    "start_s": r["start_s"],
                    "span_s": r["end_s"] - r["start_s"],
                    "observations": r["observation_count"],
                    "norad": top.get("catalog_number"),
                    "runner_norad": runner.get("catalog_number"),
                    "fit_rms_hz": top.get("fit_rms_hz"),
                    "evaluation_rms_hz": a,
                    "runner_evaluation_rms_hz": b,
                    "runner_ratio": b / a if a and b is not None else None,
                    "tau_s": top.get("selected_tau_s"),
                    "production_norad": match["leading_catalog_number"] if match else None,
                    "production_accepted": not match["abstention_recommended"] if match else None,
                    "png": f"http://gauss:8090/api/v1/scanner/tracking/{s['session_id']}/{r['artifact_name']}.png?sha256="
                    + next(a["sha256"] for a in p["artifacts"] if a["name"] == r["artifact_name"]),
                }
            )
        ledger.append(
            {
                **base,
                "utc": datetime.fromtimestamp(s.get("created_utc_ns", 0) / 1e9, UTC).isoformat(),
                "duty_pct": s.get("valid_duty_pct"),
                "lane_count": len(s.get("visit_lanes", {})),
                "sideband_policy": "mixed"
                if any("upper" in k for k in s.get("visit_lanes", {}))
                and any("lower" in k for k in s.get("visit_lanes", {}))
                else "single-side",
                "metrics": s.get("metrics", {}).get("state"),
                "tracking": s.get("tracking", {}).get("state"),
                "tracklets": len(by_id),
                "eligible_groups": p.get("eligible_group_count", 0),
                "attempted_groups": p.get("attempted_group_count", 0),
                "deferred_groups": p.get("deferred_group_count", 0),
                "survived": sum(
                    not c["abstention_recommended"] for c in p.get("tle_candidates", [])
                ),
                "reviews": len(p.get("track_reviews", [])),
                "pngs_verified": sum(a["verified"] for a in s.get("artifacts", [])),
                "problems": ";".join(s.get("problems", [])),
            }
        )
    for name, rows in (
        ("sessions", ledger),
        ("tracks", tracks),
        ("associations", candidates),
        ("reviews", reviews),
    ):
        write_csv(output / (name + ".csv"), rows)
    with gzip.open(output / "full-audit.json.gz", "wt") as handle:
        json.dump({"summary": summary, "sessions": sessions}, handle)
    rates = sorted({x["rate_msps"] for x in ledger})
    rate_rows = []
    for rate in rates:
        ss = [x for x in ledger if x["rate_msps"] == rate]
        tt = [x for x in tracks if x["rate_msps"] == rate]
        cc = [x for x in candidates if x["rate_msps"] == rate]
        rr = [x for x in reviews if x["rate_msps"] == rate]
        rate_rows.append(
            [
                rate,
                len(ss),
                fmt(median(x["duty_pct"] for x in ss)),
                len(tt),
                fmt(len(tt) / len(ss)),
                fmt(median(x["span_s"] for x in tt)),
                fmt(median(x["local_rms_hz"] for x in tt)),
                len(cc),
                sum(x["accepted"] for x in cc),
                fmt(100 * sum(x["accepted"] for x in cc) / len(cc) if cc else None),
                sum(x["deferred_groups"] for x in ss),
                fmt(median(x["evaluation_rms_hz"] for x in rr)),
            ]
        )
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    for rate in rates:
        ss = [x for x in ledger if x["rate_msps"] == rate]
        tt = [x for x in tracks if x["rate_msps"] == rate]
        ax[0, 0].scatter(
            [datetime.fromisoformat(x["utc"]) for x in ss],
            [x["tracklets"] for x in ss],
            s=16,
            label=f"{rate:g} MS/s",
        )
        ax[0, 1].scatter(
            [x["span_s"] for x in tt],
            [x["local_rms_hz"] for x in tt],
            s=9,
            alpha=0.4,
            label=f"{rate:g}",
        )
    ax[0, 0].set(
        ylabel="Reconstructed tracklets / capture", title="Detection and tracking timeline"
    )
    ax[0, 0].legend()
    fig.autofmt_xdate()
    ax[0, 1].set(
        xlabel="Track span (s)",
        ylabel="Local linear residual RMS (Hz)",
        yscale="log",
        title="Length and local fit quality",
    )
    ax[1, 0].bar([str(r) for r in rates], [float(row[9]) for row in rate_rows])
    ax[1, 0].set(xlabel="Native rate (MS/s)", ylabel="Groups surviving controls (%)", ylim=(0, 100))
    ax[1, 1].boxplot(
        [
            [
                x["evaluation_rms_hz"]
                for x in reviews
                if x["rate_msps"] == rate and x["evaluation_rms_hz"] is not None
            ]
            for rate in rates
        ],
        tick_labels=[str(r) for r in rates],
        showfliers=False,
    )
    ax[1, 1].set(
        xlabel="Native rate (MS/s)",
        ylabel="Top RMS-review evaluation RMS (Hz)",
        title="Descriptive comparison; unpaired captures",
    )
    fig.tight_layout()
    fig.savefig(output / "sample-rate-comparison.png", dpi=150)
    plt.close(fig)
    reasons = Counter(r for c in candidates for r in c["reasons"].split(";") if r)
    fig, ax = plt.subplots(1, 2, figsize=(15, 6))
    labels = list(reasons)
    ax[0].barh(
        [s.replace("-on-randomized-evaluation", "") for s in labels], [reasons[x] for x in labels]
    )
    ax[0].set(
        xlabel="Candidate-group rows (reasons overlap)", title="Association rejection reasons"
    )
    er = Counter(t["eligibility"] for t in tracks)
    ax[1].bar(er.keys(), er.values())
    ax[1].set(ylabel="Unique tracklets", title="14 observations / 7 s eligibility")
    fig.tight_layout()
    fig.savefig(output / "failure-funnel.png", dpi=150)
    plt.close(fig)
    channel_rows = []
    for ch in range(1, 5):
        for edge in ("lower", "upper"):
            tt = [x for x in tracks if x["channel"] == ch and x["edge"] == edge]
            cc = [x for x in candidates if x["channel"] == ch and x["edge"] == edge]
            visits = sum(s.get("visit_lanes", {}).get(f"CH{ch}{edge}", 0) for s in sessions)
            channel_rows.append(
                [
                    f"CH{ch} {edge}",
                    visits,
                    len(tt),
                    fmt(len(tt) * 1000 / visits if visits else None),
                    fmt(median(x["span_s"] for x in tt)),
                    fmt(median(x["local_rms_hz"] for x in tt)),
                    len(cc),
                    sum(x["accepted"] for x in cc),
                ]
            )
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    ax[0].bar(
        [r[0] for r in channel_rows], [float(r[3]) if r[3] != "—" else 0 for r in channel_rows]
    )
    ax[0].tick_params(axis="x", rotation=45)
    ax[0].set(ylabel="Tracklets / 1,000 visits", title="Channel yield normalized by visit exposure")
    bins = [(0, 7), (7, 14), (14, 30), (30, 60), (60, float("inf"))]
    length_rows = []
    for lo, hi in bins:
        tt = [t for t in tracks if lo <= t["span_s"] < hi]
        cc = [c for c in candidates if lo <= c["span_s"] < hi]
        length_rows.append(
            [
                f"{lo}–{hi:g}",
                len(tt),
                sum(t["eligibility"] == "eligible" for t in tt),
                len(cc),
                sum(c["accepted"] for c in cc),
                fmt(median(t["local_rms_hz"] for t in tt)),
            ]
        )
    ax[1].bar([r[0] for r in length_rows], [r[3] for r in length_rows], label="Compared groups")
    ax[1].bar([r[0] for r in length_rows], [r[4] for r in length_rows], label="Survived controls")
    ax[1].legend()
    ax[1].set(xlabel="Support span (s)", ylabel="Groups", title="Association by support length")
    fig.tight_layout()
    fig.savefig(output / "channels-lengths.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    for rate in rates:
        rr = [
            x
            for x in reviews
            if x["rate_msps"] == rate and x["runner_evaluation_rms_hz"] is not None
        ]
        ax[0].scatter(
            [x["evaluation_rms_hz"] for x in rr],
            [x["runner_evaluation_rms_hz"] for x in rr],
            s=12,
            alpha=0.5,
            label=f"{rate:g} MS/s",
        )
        cc = [
            x for x in candidates if x["rate_msps"] == rate and x["runner_nll_margin"] is not None
        ]
        ax[1].scatter(
            [x["span_s"] for x in cc], [x["runner_nll_margin"] for x in cc], s=12, alpha=0.5
        )
    ax[0].plot([1, 100000], [1, 100000], "k--", lw=1)
    ax[0].set(
        xscale="log",
        yscale="log",
        xlabel="Top fit-ranked TLE evaluation RMS (Hz)",
        ylabel="Runner-up evaluation RMS (Hz)",
        title="Above diagonal favors top TLE",
    )
    ax[0].legend()
    ax[1].axhline(0, color="k", lw=1)
    ax[1].set(
        xlabel="Group support span (s)",
        ylabel="Evaluation runner NLL margin",
        title="Positive margin favors retained leader",
    )
    fig.tight_layout()
    fig.savefig(output / "rank-separation.png", dpi=150)
    plt.close(fig)
    disagreed = [
        r
        for r in reviews
        if r["production_norad"] is not None and r["norad"] != r["production_norad"]
    ]
    near = [
        t
        for t in tracks
        if t["eligibility"] != "eligible" and t["observation_count"] >= 12 and t["span_s"] >= 5
    ]
    write_csv(output / "near-eligibility.csv", near)
    write_csv(output / "ranking-disagreements.csv", disagreed)
    totals = {
        "sessions": len(sessions),
        "tracklets": len(tracks),
        "comparisons": len(candidates),
        "survived": sum(c["accepted"] for c in candidates),
        "reviews": len(reviews),
        "eligibility": dict(er),
        "reasons": dict(reasons),
        "near_eligibility": len(near),
        "rms_vs_production_disagreements": len(disagreed),
        "deferred": sum(x["deferred_groups"] for x in ledger),
        "no_track_sessions": sum(x["tracklets"] == 0 for x in ledger),
        "no_candidate_sessions": sum(x["attempted_groups"] == 0 for x in ledger),
        "comparable_rankings": sum(r["production_norad"] is not None for r in reviews),
        "evaluated_top_beats_runner": sum(
            r["runner_ratio"] is not None and r["runner_ratio"] > 1 for r in reviews
        ),
        "sessions_with_surviving_candidate": sum(x["survived"] > 0 for x in ledger),
    }
    (output / "statistics.json").write_text(json.dumps(totals, indent=2) + "\n")
    parts = [
        "# Adaptive scanner: comprehensive 48-hour audit",
        "",
        f"Frozen capture window: **{datetime.fromtimestamp(summary['start_ns'] / 1e9, UTC).isoformat()} to {datetime.fromtimestamp(summary['end_ns'] / 1e9, UTC).isoformat()}**. Selection uses the capture publication index timestamp. No new RF was acquired for this report. Audit completed {summary['audited_at']}.",
        "",
        "## Coverage and verification",
        "",
        table(
            ["Quantity", "Count"], [[k, v] for k, v in totals.items() if not isinstance(v, dict)]
        ),
        "",
        f"PNG content/digest checks passed: {summary['verified_pngs']}. Recorded audit problems: {len(summary['problems'])}. Metrics states: {summary['metrics_states']}; tracking states: {summary['tracking_states']}.",
        "",
        "Each PNG was fetched from production, checked for image/png, decoded, and compared with its manifest SHA-256. Per-track review images must be 2250×2100. Tracking JSON must match the current store product and bind the capture and metrics digests. This verifies the API assets used by the UI; it is not a browser screenshot test for every session.",
        "",
        "## Sample-rate comparison",
        "",
        table(
            [
                "MS/s",
                "Captures",
                "Median duty %",
                "Tracks",
                "Tracks/capture",
                "Median span s",
                "Local RMS Hz",
                "Compared",
                "Survived",
                "Survived %",
                "Deferred",
                "Review RMS Hz",
            ],
            rate_rows,
        ),
        "",
        "![Rate comparison](sample-rate-comparison.png)",
        "",
        "Rates are interleaved in time, not simultaneous views of the same signals. These descriptive differences combine RF conditions, satellites in view, channel choice, and selection. They cannot establish a causal bandwidth gain. Local linear-fit RMS, TLE-review RMS, and likelihood scores are different quantities and must not be substituted for one another.",
        "",
        "## Channel and sideband comparison",
        "",
        table(
            [
                "Lane",
                "Visits",
                "Tracks",
                "Tracks/1k visits",
                "Median span s",
                "Local RMS Hz",
                "Compared",
                "Survived",
            ],
            channel_rows,
        ),
        "",
        "Visit-normalized counts correct sampling exposure, but not antenna gain, satellite visibility, transmit activity or SNR. Adaptive dwell selection makes exposure outcome-dependent. Upper/lower groups are distinct observations, not automatically independent satellites.",
        "",
        "![Channels and support length](channels-lengths.png)",
        "",
        "## Track length and eligibility",
        "",
        table(
            [
                "Span s",
                "Tracklets",
                "Eligible tracklets",
                "Compared groups",
                "Survived",
                "Local RMS Hz",
            ],
            length_rows,
        ),
        "",
        "Trajectory extraction requires at least 8 observations, 4 seconds of span, and gaps no larger than 4 seconds. Catalogue eligibility requires 14 observations and 7 seconds. The tracker compares at most four eligible groups across hypotheses per capture; other eligible groups are deferred. Tracklets, physical groups across hypotheses, and independent satellites are not interchangeable counts.",
        "Longer tracks can have larger local linear-fit RMS because real orbital Doppler has curvature; this is not automatically noisier GLRT. The TLE residual is the appropriate shape-aware quantity for evaluating an orbit. Neither residual is a frame-timing error or a UTC accuracy measurement.",
        "",
        "## Successes, near misses, and misses",
        "",
        table(["Association rejection reason", "Rows"], reasons.most_common()),
        "",
        "![Failure and eligibility funnel](failure-funnel.png)",
        "",
        f"There are {len(near)} near-eligibility tracks, defined in this report as at least 12 observations and 5 seconds but failing 14/7. These are engineering near misses, not independently verified satellites. The full ledger identifies whether each track fails span, support count, or both.",
        "",
        "A no-track result means no trajectory met the configured extraction criteria. It does not prove absence of a satellite. There is no labeled truth set or calibrated antenna field-of-view inventory for this window, so detection recall, false-negative rate, and missed-satellite counts cannot be measured from these products alone.",
        "",
        "## Catalogue discrimination",
        "",
        "![Rank separation](rank-separation.png)",
        "",
        f"The per-track RMS report and production association select different leaders in **{len(disagreed)}** directly comparable representative-track rows. The report ranks constant-offset/time-shift residual RMS; production uses uncertainty-aware likelihood and control comparisons. An attractive rank-1 PNG is not automatically a production acceptance. See ranking-disagreements.csv for every case.",
        "",
        "Current evaluation partitions observations deterministically at random (60% fit, 40% evaluation), rather than holding out the end of a pass. Fixed TLE elements are propagated; a constant CFO offset and bounded ±5 s time shift are fitted. Legacy JSON fields containing training/heldout refer to this randomized policy. Polynomial and ±500 s wrong-time controls test alternative explanations. A control must improve NLL by at least 0.01 per evaluation observation to trigger its material-advantage rejection.",
        "",
        "The per-track middle-right panel fits polynomials to the TLE residual as a diagnostic. A runner-up whose RMS collapses after polynomial subtraction has systematic slope/curvature mismatch. Those extra coefficients should not be silently used to rescue its physical TLE fit. Conversely, a smooth top-candidate residual can reflect calibration or timing error and deserves investigation. Scalar RMS alone is insufficient to assign a calibrated identity probability.",
        "",
        "## What works, what does not, and improvements",
        "",
        "- **Working:** counter-relative GLRT trajectories, current V10 randomized comparisons, per-track review JSON, and digest-versioned PNG publication can be audited end to end. Candidate survival means it passed the implemented controls, not that identity is independently established.",
        "- **Coverage gap:** the four-group comparison cap leaves eligible groups without production control scoring even when their RMS plots exist. Use resumable group jobs in the existing processing queue to finish all groups, with explicit per-group pending/completed status.",
        "- **Scientific consistency:** reuse one candidate bank, nuisance fit and ranking implementation for both production and plots. Expose both likelihood and RMS when they intentionally differ; show the production disposition beside each review.",
        "- **Short/sparse tracks:** test gap-aware candidate linking and reacquisition on labeled retained-IQ cases. Do not lower support thresholds solely to increase accepted counts; measure recovered true tracks and new false associations.",
        "- **Residual structure:** publish smooth residual amplitude, remaining scatter, and correlation diagnostics for the top candidates. Calibrate thresholds on synthetic offsets, wrong-catalogue controls and independently identified tracks before using them as acceptance gates.",
        "- **Absolute timing:** the 2 s qualification policy is an operational relaxation, not improved clock accuracy. Better firmware UTC/counter binding and calibrated RF offsets would reduce nuisance freedom and strengthen identity separation.",
        "- **Bandwidth study:** decimate identical native-rate IQ and apply the same probe schedule and candidate selection to compare rates. Interleaved captures cannot isolate the sampling-rate effect.",
        "- **PSS:** standard products here are GLRT/trajectory/TLE evidence. There is no standard per-capture PSS output in this pipeline; absence of PSS PNGs must not be reported as successful PSS analysis. The prior September 18 PSS replay found approximately microsecond conditional repeatability and unresolved pilot-only false-positive controls. It was a different cohort, not a new measurement in this window.",
        "",
        "## Reproducibility and complete ledgers",
        "",
        "Run `tools/audit_adaptive_window.py` with the frozen end timestamp, then `tools/report_adaptive_window_audit.py`. Input authority is the deployed capture/analysis stores and production API; all rows and digests are preserved in [full-audit.json.gz](full-audit.json.gz).",
        "",
        "- [Every capture](sessions.csv)\n- [Every reconstructed track](tracks.csv)\n- [Every production comparison and rejection](associations.csv)\n- [Every per-track RMS review and PNG URL](reviews.csv)\n- [Near eligibility misses](near-eligibility.csv)\n- [RMS/likelihood leader disagreements](ranking-disagreements.csv)\n- [Summary statistics](statistics.json)",
        "",
        "## Session-by-session inventory",
        "",
        table(
            [
                "Session",
                "MS/s",
                "GLRT",
                "Tracking",
                "Tracks",
                "Compared / eligible",
                "Deferred",
                "Survived",
                "3×2 PNGs",
                "Verified PNGs",
            ],
            [
                [
                    x["session_id"],
                    x["rate_msps"],
                    x["metrics"],
                    x["tracking"],
                    x["tracklets"],
                    f"{x['attempted_groups']} / {x['eligible_groups']}",
                    x["deferred_groups"],
                    x["survived"],
                    x["reviews"],
                    x["pngs_verified"],
                ]
                for x in ledger
            ],
        ),
    ]
    quality_rows = []
    for rate in rates:
        rr = [r for r in reviews if r["rate_msps"] == rate and r["runner_ratio"] is not None]
        quality_rows.append(
            [
                rate,
                len(rr),
                sum(r["runner_ratio"] > 1 for r in rr),
                fmt(median(r["runner_ratio"] for r in rr)),
                sum(r["runner_ratio"] >= 2 for r in rr),
                sum(abs(r["tau_s"]) == 5 for r in rr),
            ]
        )
    # Session bootstrap preserves within-capture correlation between track rows.
    rng = np.random.default_rng(20260920)
    uncertainty_rows = []
    for rate in rates:
        ss = [s for s in ledger if s["rate_msps"] == rate]
        grouped = [[c for c in candidates if c["session_id"] == s["session_id"]] for s in ss]
        fractions = []
        for _ in range(2000):
            sample = [c for i in rng.integers(0, len(ss), len(ss)) for c in grouped[i]]
            if sample:
                fractions.append(100 * sum(c["accepted"] for c in sample) / len(sample))
        low, high = np.percentile(fractions, [2.5, 97.5]) if fractions else (np.nan, np.nan)
        uncertainty_rows.append([rate, fmt(low), fmt(high)])
    examples = sorted(
        [r for r in reviews if r["production_accepted"] and r["norad"] == r["production_norad"]],
        key=lambda r: -(r["runner_ratio"] or 0),
    )[:6]
    supplemental = [
        "## How decisive are the residual rankings?",
        "",
        table(
            [
                "MS/s",
                "Reviews",
                "Top beats runner on evaluation",
                "Median runner/top RMS",
                "Runner ≥2× worse",
                "Top tau on ±5 s boundary",
            ],
            quality_rows,
        ),
        "",
        "The top five satellites are selected by fit RMS. The evaluation column compares those frozen fits. A runner/top ratio above one supports the fit leader; a ratio below one is a rank reversal between these two. This does not test all alternative satellites or establish a posterior identity probability.",
        "",
        "### Uncertainty in survival fractions",
        "",
        table(["MS/s", "95% bootstrap lower %", "95% bootstrap upper %"], uncertainty_rows),
        "",
        "Intervals use 2,000 resamples of entire captures, deterministic seed 20260920. They preserve within-capture track correlation but not correlation between adjacent passes; treat them as descriptive uncertainty, not a rate-effect test.",
        "",
        "### Strong successful examples",
        "",
        table(
            [
                "Session",
                "Lane",
                "Span s",
                "RMS leader",
                "Evaluation Hz",
                "Runner Hz",
                "Runner/top",
                "Figure",
            ],
            [
                [
                    r["session_id"],
                    f"CH{r['channel']} {r['edge']}",
                    fmt(r["span_s"]),
                    r["norad"],
                    fmt(r["evaluation_rms_hz"]),
                    fmt(r["runner_evaluation_rms_hz"]),
                    fmt(r["runner_ratio"]),
                    f"[3×2 PNG]({r['png']})",
                ]
                for r in examples
            ],
        ),
        "",
        "These examples have a surviving production comparison and agreement between the production and RMS leaders. They are selected illustrations, not a representative success-rate estimate.",
        "",
        "### Representative ranking disagreements",
        "",
        table(
            [
                "Session",
                "Lane",
                "Span s",
                "RMS leader",
                "Production leader",
                "Production survived",
                "Figure",
            ],
            [
                [
                    r["session_id"],
                    f"CH{r['channel']} {r['edge']}",
                    fmt(r["span_s"]),
                    r["norad"],
                    r["production_norad"],
                    r["production_accepted"],
                    f"[3×2 PNG]({r['png']})",
                ]
                for r in disagreed[:12]
            ],
        ),
        "",
        "### Tracks closest to the support threshold",
        "",
        table(
            ["Session", "Lane", "Observations", "Span s", "Failure"],
            [
                [
                    r["session_id"],
                    f"CH{r['channel']} {r['edge']}",
                    r["observation_count"],
                    fmt(r["span_s"]),
                    r["eligibility"],
                ]
                for r in sorted(near, key=lambda r: (-r["observation_count"], -r["span_s"]))[:15]
            ],
        ),
        "",
    ]
    policy_rows = []
    for policy in ("mixed", "single-side"):
        for rate in rates:
            ss = [s for s in ledger if s["sideband_policy"] == policy and s["rate_msps"] == rate]
            ids = {s["session_id"] for s in ss}
            tt = [t for t in tracks if t["session_id"] in ids]
            cc = [c for c in candidates if c["session_id"] in ids]
            rr = [r for r in reviews if r["session_id"] in ids]
            policy_rows.append(
                [
                    policy,
                    rate,
                    len(ss),
                    fmt(len(tt) / len(ss) if ss else None),
                    fmt(median(t["span_s"] for t in tt)),
                    fmt(median(r["evaluation_rms_hz"] for r in rr)),
                    len(cc),
                    sum(c["accepted"] for c in cc),
                ]
            )
    policy_section = [
        "## Scan policy is a material confounder",
        "",
        table(
            [
                "Policy",
                "MS/s",
                "Captures",
                "Tracks/capture",
                "Median span s",
                "Review RMS Hz",
                "Compared",
                "Survived",
            ],
            policy_rows,
        ),
        "",
        "The mixed cohort visits seven lanes across both sidebands; the single-side cohort visits four. These policies occur at different times. Shorter revisit intervals can improve track support without any change in sample rate. The table stratifies the observations but does not remove differences in satellites or RF conditions.",
        "",
    ]
    parts[
        parts.index("## Channel and sideband comparison") : parts.index(
            "## Channel and sideband comparison"
        )
    ] = policy_section
    parts[
        parts.index("## What works, what does not, and improvements") : parts.index(
            "## What works, what does not, and improvements"
        )
    ] = supplemental
    (output / "report.md").write_text("\n".join(parts) + "\n")
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.input, args.output)
