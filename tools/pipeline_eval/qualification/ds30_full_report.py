"""Render the matched full-DS30 results from the same rows used for the figures."""

from statistics import median

from ..scoring import distribution
from .ds30_full_inputs import METHODS, OUT
from .ds30_full_score import belongs

NAMES = dict(zip(METHODS, ("Original", "Compact"), strict=True))
GROUPS = {
    "all": "All recordings",
    "new": "Previously unreported",
    "complete": "Complete captures",
    "incomplete": "Interrupted captures",
}


def number(value, places=3):
    return "—" if value is None else f"{value:.{places}f}"


def table(headers, rows):
    def line(cells):
        return "| " + " | ".join(map(str, cells)) + " |"

    return "\n".join([line(headers), line(["---"] * len(headers)), *(line(r) for r in rows)])


def matched_runtime(rows, pairs):
    fitted = {(r["case"], r["method"]): r for r in rows if r["calibration"] == "fitted_c"}
    tables = []
    for label, group, field, ratio in (
        ("Position solver · all", "all", "solver_wall_s", "solver_speedup"),
        ("Raw I/Q to result · all", "all", "end_to_end_wall_s", "end_to_end_speedup"),
        ("Raw I/Q to result · complete", "complete", "end_to_end_wall_s", "end_to_end_speedup"),
        (
            "Raw I/Q to result · interrupted",
            "incomplete",
            "end_to_end_wall_s",
            "end_to_end_speedup",
        ),
    ):
        timed = [
            p
            for p in pairs
            if p["calibration"] == "fitted_c" and p[ratio] is not None and belongs(p, group)
        ]
        cells = [label, len(timed)]
        for method in METHODS:
            times = distribution(fitted[p["case"], method][field] / 60 for p in timed)
            cells.extend([number(times["p50"], 2), number(times["p95"], 2)])
        speedup = median(p[ratio] for p in timed) if timed else None
        tables.append([*cells, number(speedup, 2)])
    return tables


def report(rows, pairs, summaries, comparisons, repeated, folder=OUT):
    stats = {(s["group"], s["method"], s["calibration"]): s for s in summaries}
    fitted = "fitted_c"
    errors, paired, calibration = [], [], []
    for group, label in GROUPS.items():
        for method in METHODS:
            s = stats[group, method, fitted]
            errors.append(
                [
                    label,
                    NAMES[method],
                    f"{s['fixes']}/{s['assigned']}",
                    *(number(s[f"p{p}_km"]) for p in (50, 90, 95)),
                    *(s[f"within_{k}km"] for k in (1, 2, 5)),
                ]
            )
        p = next(s for s in comparisons if s["group"] == group and s["calibration"] == fitted)
        paired.append(
            [
                label,
                p["common_scored"],
                p["original_only_fixes"],
                p["compact_only_fixes"],
                p["neither_fixes"],
                p["original_closer"],
                p["compact_closer"],
                number(p["paired_median_delta_km"]),
                f"{number(p['bootstrap_low_km'])} to {number(p['bootstrap_high_km'])}",
            ]
        )
    for method in METHODS:
        for arm in ("c0", fitted):
            s = stats["all", method, arm]
            calibration.append(
                [
                    NAMES[method],
                    "Fixed zero" if arm == "c0" else "Fitted",
                    f"{s['fixes']}/{s['assigned']}",
                    number(s["p50_km"]),
                    number(s["p95_km"]),
                    number(s["frequency_rms_hz_p50"], 2),
                    number(s["frequency_score_p50"], 2),
                ]
            )
    audit = stats["all", METHODS[0], fitted]
    repeated_fixes = sum(r["old_fix"] == r["current_fix"] for r in repeated)
    differences = [
        r["endpoint_difference_km"] for r in repeated if r["endpoint_difference_km"] is not None
    ]
    displacement = number(max(differences), 6) + " km" if differences else "unavailable"
    parts = [
        "# Full DS30 results on Gauss",
        "Original uses original GLRT and algo07v5 fast with no repair. Compact uses two-scan "
        "cancellation and the five-refresh compact v5 solver. Both use the same 25 km region "
        "and capture-era orbit files. This comparison measures the combined effect of the detector "
        "and solver changes. [Protocol](PROTOCOL.md) · [Replay instructions](README.md)",
        "## Position error",
        f"The operator's rooftop reference covers {audit['reference_eligible']} of "
        f"{audit['assigned']} recordings. Percentiles describe scored fixes. Each threshold counts "
        "how many of the assigned recordings yielded a position within that distance. "
        "[Recording results](recordings.csv) · [Group summaries](summary.csv)",
        table(
            [
                "Recordings",
                "Pipeline",
                "Fixes",
                "Median km",
                "P90 km",
                "P95 km",
                "≤1 km",
                "≤2 km",
                "≤5 km",
            ],
            errors,
        ),
        "![Cumulative horizontal error with fitted and fixed-zero calibration](position-error.png)",
        "## Comparing the same recordings",
        "The error change is compact minus original on recordings with two scored fixes. Negative "
        "values favor compact. The interval resamples whole recordings 5,000 times. These repeated "
        "measurements describe one roof. [Paired results](paired.csv) · "
        "[Paired summaries](paired-summary.csv)",
        table(
            [
                "Recordings",
                "Both scored",
                "Original only",
                "Compact only",
                "Neither",
                "Original closer",
                "Compact closer",
                "Median change km",
                "95% bootstrap interval km",
            ],
            paired,
        ),
        "## Runtime",
        "Each row includes recordings with both measurements on the same Gauss CPU. Original and "
        "compact run serially within each recording. The raw timing includes I/Q read, integrity "
        "checks, acquisition and positioning. A fresh, uninterrupted measurement qualifies for "
        "that timing. The raw pairs come from the subset without an archived original detection. "
        "For an archived detection, the measured interval starts at the solver. Times include both "
        "calibration fits and any configured retry.",
        table(
            [
                "Measured interval",
                "Pairs",
                "Original median min",
                "Original P95 min",
                "Compact median min",
                "Compact P95 min",
                "Median paired speedup ×",
            ],
            matched_runtime(rows, pairs),
        ),
        "![Cumulative Gauss runtimes on matched recordings](runtime.png)",
        "## Calibration",
        "Each pipeline uses the same receiver observations, orbit files, priors and search budgets "
        "in its two calibration fits. The RF residual describes agreement with that pipeline's own "
        "frequencies. Position error is scored independently against the roof reference. "
        "The compact solver exposes its RF residual.",
        table(
            [
                "Pipeline",
                "RF calibration",
                "Fixes",
                "Median km",
                "P95 km",
                "Median frequency RMS Hz",
                "Median reported score",
            ],
            calibration,
        ),
        "## Replay of the earlier panel",
        f"On the previously published compact two-scan panel, {repeated_fixes}/{len(repeated)} "
        "recording/calibration pairs reproduced the earlier fix decision. The largest endpoint "
        f"displacement among the {len(differences)} jointly returned estimates was {displacement}. "
        "[Earlier-panel comparison](repeated-panel.csv)",
        "DS30 uses one station and one search region. The station authority associates the radio "
        "and capture times with an operator-supplied roof position of unknown survey uncertainty. "
        "[Reference audit](reference-audit.json) · [Prediction lock](prediction-lock.json) · "
        "[Failure details](failures.csv) · [Independent verification](verification.json)",
    ]
    (folder / "RESULTS.md").write_text("\n\n".join(parts) + "\n")
