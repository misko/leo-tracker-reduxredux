"""Plot matched position decisions against the four original v5 configurations."""

import hashlib
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from textwrap import fill

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator, PercentFormatter

from .qualification.embedded_figures import TITLES as EMBEDDED_TITLES
from .scoring import (
    POSITION_FAILURES,
    ROLES,
    arm_outcome,
    distance_km,
    terminal_position_decision,
    validate_result,
)

TITLES = {
    "v5_lean": "V5 without evidence rendering",
    "glrt_batch": "Batched pilot-bank GLRT",
    "iq_stream": "Streamed IQ decoding",
    "glrt_cascade": "Early screening in the pilot-bank GLRT",
    "orbit_interp": "Reusing orbital states",
    "shape_score": "Horizon screening for Doppler scoring",
    "track_reduce": "Compressing Doppler tracks",
    "track_link": "Causal track linking",
    "iq_position": "Position from bounded raw-IQ replay",
    "projected_fit": "Fitting position with per-track offsets removed",
    "native-to-v5": "Full ordinary native GLRT with the v5 solver",
    "native_winner": "Native fractional winner gate with the v5 solver",
    "single_rx0": "Full raw replay through one physical receiver input",
    "single_rx0_factors": "RX0 position from two archived detector sources",
    "pilot_confirmation": "Late pilot confirmation at the proposed epoch and CFO",
    "spectral_grid": "Shared sliding tones for coarse pilot acquisition",
    "off_region_test": "Longitude controls on Doppler arc predictions",
    "point_votes": "Cold-start localization by GLRT point voting",
    "rate_triplets": "Cold-start localization from GLRT rate triplets",
    "folded_doppler": "Cold-start localization from folded GLRT Doppler",
    "v5_batched_salvage": "Batched salvage in the compact v5 finish",
    "v5_catalogue_memory": "Batched ECEF propagation in the compact v5 finish",
    "v5_stream_prepare": "Compact v5 with incremental GLRT input preparation",
    "pass_geometry": "Position from Doppler pass geometry",
    "v5_one_seed": "V5 with one discovery seed",
    "v5_first_ranked": "V5 with one ranked initial branch",
    "v5_initial_rank1": "V5 first-ranked and best-of-three initial fixes",
    "v5_prefix_180": "Compact v5 with 180 seconds of detector factors",
    "v5_prefix_180_raw": "Compact v5 after 180 seconds of raw-IQ replay",
    "v5_shared_search": "Compact v5 with shared branch search",
    "joint_pass_id": "Satellite identity from native carrier and frame timing",
    "robust_em": "Robust satellite association and position fit",
    "refine_bank": "Fused GLRT refinement through v5",
    "v5_core": "Reduced v5 through the cavity fit",
    "shared_doppler": "Doppler fit with shared receiver and satellite corrections",
    "anchor_receiver": "Accelerated pilot acquisition with the v5 position fit",
    "glrt_odd_channels": "V5 using all visits to odd RF channels",
    "glrt_even_channels": "V5 using all visits to even RF channels",
    "orbit_projector": "V5 with compact orbital projection",
    "arc_validation": "Verify satellite assignments on later Doppler samples",
    "sweep_schedule": "Observe alternate complete eight-channel sweeps",
    "catalogue_checksum": "Full v5 with bytewise orbital element checksums",
    "compact_finish": "Compact v5 with the final position repairs",
    "pilot_kernel": "Reorder the pilot correlation sums before the v5 fit",
    "native_geometry": "Native wideband pilot acquisition on 20 ms visits",
    "v5_stop_initial": "V5 stopped after the initial satellite assignment",
    "v5_stop_conservative": "V5 stopped after the conservative refit",
    "v5_stop_family": "V5 stopped after the satellite-family refit",
    "v5_stop_signed": "V5 stopped after the signed orbit correction",
    "v5_stop_cavity": "V5 stopped after the cavity fit",
    **EMBEDDED_TITLES,
}
COLORS = {
    "baseline": "#30395e",
    "selective-gap": "#6874a4",
    "omitted-track-one": "#656f87",
    "omitted-tracks": "#8990ad",
    "four": "#00785f",
    "four_forced": "#447d8a",
    "global": "#a65a12",
    "global_forced": "#a65a12",
    "one": "#a65a12",
    "one_native_factors": "#a65a12",
    "one_forced": "#447d8a",
    "stock": "#a65a12",
    "all_visits": "#664a87",
}
LABELS = {
    "baseline": "v5 · no repair",
    "selective-gap": "v5 · selective gap",
    "omitted-track-one": "v5 · one omitted",
    "omitted-tracks": "v5 · two omitted",
    "four": "Four tiles · published",
    "four_forced": "Four tiles · forced",
    "global": "Global search · published",
    "global_forced": "Global search · diagnostic",
    "one": "Single tile · published",
    "one_native_factors": "RX0 · ordinary native factors",
    "one_forced": "Single tile · forced",
    "stock": "Compact v5 · matched stock",
    "all_visits": "All visits · published",
}
ORDER = (
    *ROLES,
    "four",
    "global",
    "one",
    "one_native_factors",
    "stock",
    "all_visits",
    "four_forced",
    "global_forced",
    "one_forced",
)
STYLES = {
    "four": "-",
    "global": "-.",
    "global_forced": "--",
    "one": "-.",
    "one_native_factors": "-.",
    "four_forced": "--",
    "one_forced": "--",
    "stock": "-.",
    "all_visits": ":",
}
RX0_FACTOR_LABELS = {
    "one": "RX0 · capture-era factors",
    "one_native_factors": LABELS["one_native_factors"],
}
COLD_START_LABELS = {
    "global": LABELS["global"],
    "one": "Supplied tile · published",
    "global_forced": LABELS["global_forced"],
    "one_forced": "Supplied tile · diagnostic",
}
MEMORY_LABELS = {
    "v5_batched_salvage": {"one": "Batched salvage · published", "stock": LABELS["stock"]},
    "v5_catalogue_memory": {"one": "Batched catalogue · published", "stock": LABELS["stock"]},
    "v5_stream_prepare": {"one": "Incremental reader · published", "stock": LABELS["stock"]},
}
DETECTOR_FIT_LABELS = {
    "spectral_grid": {"one": "Sliding tones · sampled IQ", "stock": "Capture-era GLRT · stock"},
    "native_geometry": {"one": "Wideband GLRT · sampled IQ", "stock": "Capture-era GLRT · stock"},
    "pilot_confirmation": {
        "one": "Pilot gate · sampled visits",
        "stock": "Ordinary native GLRT · stock",
        "all_visits": "Pilot gate · all visits",
    },
    "v5_one_seed": {"one": "One seed · published", "stock": "Full search · matched"},
    "v5_first_ranked": {"one": "First ranked · published", "stock": "Full search · matched"},
    "v5_first_ranked_broad": {"one": "First ranked · published", "stock": "Full search · matched"},
    "v5_initial_rank1": {
        "one": "First ranked · initial fix",
        "stock": "Best of three · initial fix",
    },
    "v5_prefix_180": {"one": "180-second prefix · published", "stock": "Full exposure · matched"},
    "v5_prefix_180_raw": {
        "one": "180-second raw replay · published",
        "stock": "Full ordinary exposure · matched",
    },
    "v5_shared_search": {
        "one": "Shared search · published",
        "stock": "Compact finish · matched stock",
    },
    "refine_bank": {"one": "Refined GLRT · sampled IQ", "stock": "Capture-era GLRT · stock"},
    "raw_robust": {
        "one": "Robust · ordinary",
        "one_forced": "Robust · forced",
        "stock": "Robust · capture-era",
        "all_visits": "V5 · ordinary",
    },
    "periodic_anchor": {
        "one": "Reference sweep every 64",
        "stock": "Ordinary native GLRT",
        "all_visits": "Capture-era GLRT",
    },
    "v5_two_refresh": {"one": "Two phase refreshes", "stock": "Full phase budget"},
    "v5_likelihood_reuse": {"one": "Reused likelihood", "stock": "Stock likelihood"},
    "region_challenge": {
        "one": "Region challenge · published",
        "one_forced": "Region challenge · forced",
        "stock": "Archived joint pass",
    },
    "robust_orbit_fit": {
        "one": "Orbit-aware robust fit",
        "one_forced": "Orbit-aware fit · forced",
        "stock": "Original robust fit",
    },
    "raw_orbit_fit": {
        "one": "Orbit-aware robust fit",
        "one_forced": "Orbit-aware fit · forced",
        "stock": "Original robust fit",
    },
    "v5_secant_fit": {"one": "Secant steps", "stock": "Stock bounded solver"},
    "v5_secant_two_refresh": {
        "one": "Secant and two refreshes",
        "stock": "Full compact fit",
        "one_native_factors": "Secant steps only",
        "all_visits": "Two phase refreshes only",
    },
    "conditioned_cfo_bank": {
        "one": "Conditioned CFO · sampled IQ",
        "stock": "Capture-era archive control",
    },
}
PARTIAL_IQ_CAPTION = (
    "16 scheduled IQ windows per recording use the accelerated detector. "
    "Remaining detections come from the archive. Both v5 fits rerun."
)


@dataclass(frozen=True)
class Mark:
    dataset: str
    recording: str
    series: str
    decision: str
    error_km: float | None


def best_guess_field(method, endpoint):
    if "forced_latlon" in endpoint:
        return "forced_latlon"
    # The projected fit stores the pooled point as its published position when accepted.
    if method == "projected_fit" and endpoint.get("latlon") is not None:
        return "latlon"
    return None


def marks(refs, single, multi, method, arm, *, additional_modes=None, diagnostic_modes=()):
    """Every offered case gets one row per displayed series, including abstentions."""
    ids = {r["id"] for r in refs}
    if not ids or len(ids) != len(refs):
        raise ValueError("a figure requires a nonempty unique recording roster")
    modes = {} if single is None else {"one": single}
    if multi is not None:
        modes["four"] = multi
    if additional_modes:
        modes.update(additional_modes)
    for records in modes.values():
        if set(records) - ids:
            raise ValueError("figure contains a recording outside its reference roster")
        for record in records.values():
            result = record["result"]
            validate_result(result)
            if result["metrics"].get("position_attempted") is False and any(
                endpoint.get(k) is not None
                for endpoint in result.get("arms", {}).values()
                for k in ("latlon", "forced_latlon")
            ):
                raise ValueError("an unattempted fit cannot supply a position")
    diagnostic = "four" if multi is not None else "one"
    diagnostic_arms = [
        r["result"].get("arms", {}).get(arm, {})
        for r in modes.get(diagnostic, {}).values()
        if r["result"]["metrics"].get("position_attempted") is not False
    ]
    diagnostics = set(diagnostic_modes)
    if any(best_guess_field(method, endpoint) for endpoint in diagnostic_arms):
        diagnostics.add(diagnostic)
    rows = []
    for case in refs:
        dataset, recording = case["group"], case["recording"]
        for role in ROLES:
            original = case["reference"][role][arm]
            error = original["error_km"]
            decision = "published" if error is not None else original["status"]
            rows.append(Mark(dataset, recording, role, decision, error))
        for mode, records in modes.items():
            result = records.get(case["id"], {}).get("result", {})
            endpoint = result.get("arms", {}).get(arm)
            status, _ = arm_outcome(result, endpoint or {})
            unattempted = result.get("metrics", {}).get("position_attempted") is False
            stage_only = unattempted and not terminal_position_decision(result)
            if (stage_only and status in ("ok", "withheld")) or (
                endpoint is None and status == "ok"
            ):
                status = "stage_only"
            endpoint = endpoint or {}
            fix = endpoint.get("latlon")
            decision = "published" if fix is not None else "withheld" if status == "ok" else status
            rows.append(Mark(dataset, recording, mode, decision, distance_km(fix, case["truth"])))
            if mode in diagnostics:
                estimate = endpoint.get(best_guess_field(method, endpoint))
                state = (
                    "diagnostic"
                    if estimate is not None
                    else ("no_estimate" if status in ("ok", "withheld") else status)
                )
                rows.append(
                    Mark(
                        dataset,
                        recording,
                        mode + "_forced",
                        state,
                        distance_km(estimate, case["truth"]),
                    )
                )
    return rows


def cumulative(sample, x):
    """A fix is counted at its error threshold. Every requested recording is in the denominator."""
    errors = sorted(m.error_km for m in sample if m.error_km is not None)
    return np.searchsorted(errors, x, side="right") / len(sample)


@lru_cache(maxsize=1)
def _roof_recordings():
    from .corpus import references

    return {
        "DS26": {r["recording"] for r in references("ds26-common127")},
        "DS29": {r["recording"] for r in references("roof16") if r["group"] == "DS29"},
    }


def cohort_title(dataset, baseline):
    n = len(baseline)
    description = "recording" if n == 1 else "recordings"
    if (dataset, n) in (("DS26", 127), ("DS29", 8)) and {
        m.recording for m in baseline
    } == _roof_recordings()[dataset]:
        description = "common recordings" if dataset == "DS26" else "blind-panel recordings"
    return f"{dataset}  ·  {n} {description}"


def _axis(ax, lo, hi, *, by_decade=False):
    if lo == 0:
        ax.set_xscale("symlog", linthresh=0.03)
    else:
        ax.set_xscale("log")
    ticks = (
        (0, 0.01, 0.1, 1, 10, 100, 1000, 10000)
        if by_decade
        else (0, 0.01, 0.03, 0.1, 0.3, 1, 2, 5, 10, 30, 100, 300, 1000, 3000, 10000)
    )
    ax.set_xlim(lo, hi)
    ax.xaxis.set_major_locator(FixedLocator([v for v in ticks if lo <= v <= hi]))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
    ax.grid(axis="x", color="#dce2e5", linewidth=0.75)
    ax.spines[:].set_visible(False)
    ax.tick_params(length=0, pad=5, labelsize=9)
    ax.set_axisbelow(True)


def _fit_page_width(fig, dot_axes):
    """Keep complete row labels inside their own column and headings on the page."""
    renderer = fig.canvas.get_renderer()
    width = fig.bbox.width
    padding = fig.dpi * 0.10
    previous_right = 0.0
    for ax in dot_axes:
        position = ax.get_position()
        leftmost = min(tick.get_window_extent(renderer).x0 for tick in ax.get_yticklabels())
        label_width = ax.bbox.x0 - leftmost
        width = max(width, (label_width + padding) / (position.x0 - previous_right))
        previous_right = position.x1
    for artist in (*fig.texts, *fig.legends):
        box = artist.get_window_extent(renderer)
        left_fraction = box.x0 / fig.bbox.width
        width = max(width, (box.width + padding) / (1 - left_fraction))
    if width > fig.bbox.width:
        fig.set_figwidth(width / fig.dpi)


def terminal_count_label(rows):
    states = {row.decision for row in rows}
    if not states & POSITION_FAILURES or not states <= POSITION_FAILURES | {"stage_only"}:
        return None
    label = next(iter(states)).replace("_", " ") if len(states) == 1 else "no result"
    suffix = " · unmeasured" if "stage_only" in states else ""
    return f"0/{len(rows)} · {label}{suffix}"


def draw(
    rows, method, arm, subtitle, *, title=None, series_labels=None, show_terminal_counts=False
):
    datasets = list(dict.fromkeys(m.dataset for m in rows))
    series = [k for k in ORDER if any(m.series == k for m in rows)]
    labels = dict(LABELS)
    cold = "global" in series
    if method == "v5_lean":
        labels["one"] = "Lean v5 · published"
    if method == "single_rx0_factors":
        labels.update(RX0_FACTOR_LABELS)
    if method == "conditioned_cfo_retry":
        labels["one"] = "Whole-acquisition retry"
    if method in MEMORY_LABELS:
        labels.update(MEMORY_LABELS[method])
    if "stock" in series and method in DETECTOR_FIT_LABELS:
        labels.update(DETECTOR_FIT_LABELS[method])
    if cold:
        labels.update(COLD_START_LABELS)
    if method in EMBEDDED_TITLES:
        labels["one"] = "Site forecast" if method == "early_stationary" else "Prototype · published"
    if series_labels:
        labels.update(series_labels)
    colors = dict(COLORS)
    if method == "v5_secant_two_refresh" or (
        series_labels and "one_native_factors" in series_labels
    ):
        colors["one_native_factors"] = "#447d8a"
    if "four" not in series:
        colors["one"] = COLORS["four"]
    style = {**STYLES, "one": "--" if "four" not in series else "-."}
    if cold:
        colors["one_forced"] = colors["one"]
        style["one"] = "-"
    values = [m.error_km for m in rows if m.error_km is not None]
    lo = min(0.055, 0.80 * min(values)) if values else 0.055
    hi = max(12.0, (max(values) * 1.15) if values else 0.0)
    fig, axes = plt.subplots(
        2,
        len(datasets),
        squeeze=False,
        figsize=(9.8 if len(datasets) == 1 else 7.3 * len(datasets), 8.25),
        height_ratios=(1, 1.12),
    )
    fig.subplots_adjust(
        left=0.174 if len(datasets) > 1 else 0.275,
        right=0.975,
        top=0.765 if cold else 0.78,
        bottom=0.125,
        wspace=0.54,
        hspace=0.40,
    )
    fig.suptitle(
        title or TITLES.get(method, method.replace("_", " ")),
        x=0.027,
        y=0.976,
        ha="left",
        fontsize=22,
        weight="bold",
        color="#192c36",
    )
    fig.text(
        0.028,
        0.927,
        fill(subtitle, 90 if len(datasets) == 1 else 163),
        va="top",
        fontsize=10.5,
        color="#384d58",
    )
    handles = [
        Line2D([], [], color=COLORS["baseline"], lw=3, label="v5 no repair"),
        Patch(facecolor="#a5accb", label="Range of four v5 options"),
    ]
    measured = {"published", "withheld", "diagnostic", "no_estimate"}
    plotted = [
        k
        for k in series
        if k not in ROLES and any(m.series == k and m.decision in measured for m in rows)
    ]
    handles.extend(
        Line2D([], [], color=colors[k], linestyle=style[k], lw=2.4, label=labels[k])
        for k in plotted
    )
    fig.legend(
        handles=handles,
        loc="upper left",
        bbox_to_anchor=(0.021, 0.878),
        ncol=min(len(handles), 3 if cold or len(datasets) == 1 else 5),
        frameon=False,
        fontsize=9.4 if cold else 9.7,
        handlelength=2.7,
    )
    for j, dataset in enumerate(datasets):
        group = [m for m in rows if m.dataset == dataset]
        data = {k: [m for m in group if m.series == k] for k in series}
        ax, dot = axes[:, j]
        for a in (ax, dot):
            _axis(a, lo, hi, by_decade=cold and hi > 1000)
        x = np.unique([lo, hi, *(m.error_km for m in group if m.error_km is not None)])
        curves = np.array([cumulative(data[k], x) for k in ROLES])
        ax.fill_between(
            x, curves.min(axis=0), curves.max(axis=0), step="post", color="#a5accb", alpha=0.92
        )
        ax.step(x, curves[0], where="post", color=colors["baseline"], linewidth=3.4)
        for k in (
            "four_forced",
            "global_forced",
            "one_forced",
            "four",
            "one",
            "global",
            "one_native_factors",
            "stock",
            "all_visits",
        ):
            if k in plotted and any(m.decision in measured for m in data[k]):
                ax.step(
                    x,
                    cumulative(data[k], x),
                    where="post",
                    color=colors[k],
                    linestyle=style[k],
                    lw=2.5 if k in ("four", "global") or (cold and k == "one") else 1.9,
                )
        n = len(data["baseline"])
        ax.set_title(
            cohort_title(dataset, data["baseline"]),
            fontsize=15,
            loc="left",
            pad=12,
            fontweight="bold",
        )
        ax.set_ylim(-0.035, 1.045)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        ax.grid(axis="y", color="#e9edef", linewidth=0.75)
        ax.set_xlabel("Horizontal position error (km)", fontsize=10)
        if j == 0:
            ax.set_ylabel("Fraction of all recordings", fontsize=10)
        publication = [
            m
            for k in ("four", "global", "one", "one_native_factors", "stock", "all_visits")
            for m in data.get(k, ())
        ]
        message = ""
        if all(m.decision == "stage_only" for m in publication):
            message = "Position was unmeasured in this stage run"
        elif all(m.decision == "withheld" for m in publication):
            message = (
                f"No global or supplied-tile fixes (0/{n} each)"
                if cold
                else f"No published fixes (0/{n})"
            )
        elif unavailable := {m.recording for m in publication if m.decision not in measured}:
            if series_labels:
                counts = Counter(m.decision for m in data.get("one", ()))
                outcomes = [
                    f"{counts[state]} {label}"
                    for state, label in (
                        ("failed", "failed"),
                        ("timed_out", "timed out"),
                        ("missing", "unmeasured"),
                        ("unavailable", "unavailable"),
                    )
                    if counts[state]
                ]
                message = (
                    "Candidate · " + " · ".join(outcomes)
                    if outcomes
                    else f"Control position unmeasured on {len(unavailable)}/{n} recordings"
                )
            else:
                message = f"Position unmeasured on {len(unavailable)}/{n} recordings"
        if message:
            ax.text(
                0.025,
                0.835,
                message,
                transform=ax.transAxes,
                fontsize=9,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=2),
                color="#355464",
            )
        ticks = []
        for i, k in enumerate(series):
            sample = data[k]
            points = [m for m in sample if m.error_km is not None]
            count = f"{len(points)}/{len(sample)}"
            if all(m.decision not in measured for m in sample) and k not in ROLES:
                terminal = terminal_count_label(sample) if show_terminal_counts else None
                count = terminal or (f"0/{len(sample)} · unmeasured" if cold else "unmeasured")
            ticks.append(f"{labels[k]}    {count}")
            if not points:
                continue
            noise = [
                int(hashlib.sha256(m.recording.encode()).hexdigest()[:4], 16) / 65535 - 0.5
                for m in points
            ]
            color = colors[k]
            dot.scatter(
                [m.error_km for m in points],
                i + 0.5 * np.array(noise),
                color=color,
                linewidth=0,
                alpha=0.43 if n > 20 else 0.72,
                s=17 if n > 20 else 32,
            )
            dot.scatter(
                float(np.median([m.error_km for m in points])),
                i,
                marker="D",
                s=47,
                facecolors="white",
                edgecolors=color,
                linewidths=1.7,
                zorder=4,
            )
        dot.set_yticks(range(len(series)), ticks, fontsize=8.7)
        dot.set_ylim(len(series) - 0.45, -0.55)
        dot.set_title("Each dot is one position estimate", loc="left", fontsize=11, pad=6)
        dot.set_xlabel("Horizontal position error (km)", fontsize=10)
    calibration = "fitted c" if arm == "fitted_c" else "c = 0"
    footer = (
        f"v5 uses {calibration}. Curves count every recording. "
        "Diamonds mark the median within each row."
    )
    if cold:
        footer += " Diagnostic curves use saved estimates, including those withheld."
    elif any(k.endswith("_forced") for k in series):
        footer += " Forced includes the receiver’s best guess when it withholds."
    fig.text(
        0.028,
        0.058,
        fill(footer, 98 if len(datasets) == 1 else 170),
        va="top",
        fontsize=9.3,
        color="#394d58",
    )
    _fit_page_width(fig, axes[1])
    return fig


def save_png(fig, path):
    from .__main__ import write

    image = BytesIO()
    fig.savefig(image, dpi=155, format="png", facecolor="white")
    write(Path(path), image.getvalue())


def run_caption(rows, method=None):
    if all(m.decision == "stage_only" for m in rows if m.series == "one"):
        return "This run measured an intermediate stage. The four v5 controls supply positions."
    if method == "anchor_receiver":
        return PARTIAL_IQ_CAPTION
    return "Single-tile receiver outputs and four original v5 settings on the same recordings."


def write_run_figures(refs, records, folder, method):
    for arm in ("fitted_c", "c0"):
        rows = marks(refs, records, None, method, arm)
        fig = draw(rows, method, arm, run_caption(rows, method))
        try:
            save_png(fig, folder / f"position-errors-{arm}.png")
        finally:
            plt.close(fig)
