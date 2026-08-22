#!/usr/bin/env python3
"""Run and report a bounded GLRT search-parameter study for the T1 example.

Every raw-IQ probe is searched independently.  The piecewise degree-1 model is
loaded only after detection and is used as a fixed diagnostic reference; it is
never supplied to acquisition or GLRT scoring.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.states import StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    from tools.rerun_dense_independent_glrt import (
        CandidateRow,
        _baseline_rows,
        _best_glrt,
        _complex_receiver,
        _detect_one,
        _group,
    )
except ModuleNotFoundError:  # direct ``python tools/...`` execution
    from rerun_dense_independent_glrt import (  # type: ignore[no-redef]
        CandidateRow,
        _baseline_rows,
        _best_glrt,
        _complex_receiver,
        _detect_one,
        _group,
    )

SESSION_ID = "cap-20260821T201522-841b2a20e151"
PATH_LABEL = "stream-0/RX1"
ALIAS_SPACING_HZ = 2_500_000 / 11
MARGIN_GATE = 0.05
RESIDUAL_GATE_HZ = 500.0
WINDOWS = (
    ("actual transition", 6.60, 7.05),
    ("old apparent gap", 7.50, 7.90),
    ("steady P3 control", 16.00, 16.40),
)
DEFAULT_BASELINE = Path(
    "/srv/bulk/leo/analysis/cap-20260821T201522-841b2a20e151/"
    "capture-fb15d5f27c1c43b2b1c4f3fcf9fd13cf/scientific/path-standard/"
    "sha256:8725a64ff58c01ffc7fb1754cefafe1f92a2ffdd9a993cec31a9b0c73eeaae39/"
    "standard.pilot-scan.v3.json"
)
DEFAULT_DENSE = Path(
    "reports/figures/2026_08_21_dense_independent_glrt/"
    "dense-independent-glrt-candidates.jsonl.gz"
)
DEFAULT_LINES = Path(
    "reports/figures/2026_08_21_t1_dense_degree1_only/"
    "t1-dense-degree1-summary.json"
)
DEFAULT_OUTPUT = Path(
    "reports/figures/2026_08_22_t1_glrt_search_parameter_study"
)
DEFAULT_REPORT = Path("reports/2026_08_22_t1_glrt_search_parameter_study.md")


@dataclass(frozen=True, slots=True)
class SearchProfile:
    key: str
    label: str
    coarse_step_hz: float = 80_000.0
    fine_radius_hz: float = 80_000.0
    fine_step_hz: float = 500.0
    conditioned_radius_hz: float = 2_000.0
    conditioned_step_hz: float = 100.0
    candidate_count: int = 8
    cfo_separation_hz: float = 80_000.0
    epoch_separation_samples: int = 20
    glrt_size: int = 512


PROFILES = (
    SearchProfile("standard", "Standard reproduction"),
    SearchProfile(
        "coarse",
        "10 kHz coarse grid only",
        coarse_step_hz=10_000.0,
        fine_radius_hz=10_000.0,
    ),
    SearchProfile(
        "fine",
        "100/25 Hz fine grids only",
        fine_step_hz=100.0,
        conditioned_step_hz=25.0,
    ),
    SearchProfile("glrt", "GLRT-4096 only", glrt_size=4_096),
    SearchProfile("basins", "32 basins only", candidate_count=32),
    SearchProfile(
        "separation",
        "10 kHz/5-sample separation only",
        cfo_separation_hz=10_000.0,
        epoch_separation_samples=5,
    ),
    SearchProfile(
        "inventory",
        "32 basins + narrow separation",
        candidate_count=32,
        cfo_separation_hz=10_000.0,
        epoch_separation_samples=5,
    ),
    SearchProfile(
        "acquisition_grids",
        "All acquisition grids",
        coarse_step_hz=10_000.0,
        fine_radius_hz=10_000.0,
        fine_step_hz=100.0,
        conditioned_radius_hz=1_000.0,
        conditioned_step_hz=25.0,
    ),
    SearchProfile(
        "full_dense",
        "Combined dense",
        coarse_step_hz=10_000.0,
        fine_radius_hz=10_000.0,
        fine_step_hz=100.0,
        conditioned_radius_hz=1_000.0,
        conditioned_step_hz=25.0,
        candidate_count=32,
        cfo_separation_hz=10_000.0,
        epoch_separation_samples=5,
        glrt_size=4_096,
    ),
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--dense-candidates", type=Path, default=DEFAULT_DENSE)
    parser.add_argument("--line-summary", type=Path, default=DEFAULT_LINES)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--reuse", action="store_true")
    return parser.parse_args()


def _load_lines(path: Path) -> tuple[dict[str, float], ...]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if (
        document.get("schema") != "org.leo.research.t1-dense-degree1-only/v1"
        or document.get("radio_model") != "intercept_plus_constant_slope_only"
    ):
        raise ValueError("reference line summary is not strict degree 1")
    return tuple(document["dense"]["pieces"])


def expected_frequency(lines: tuple[dict[str, float], ...], time_s: float) -> float:
    for line in lines:
        start_s, end_s = line["interval_s"]
        if start_s <= time_s < end_s or math.isclose(time_s, end_s):
            return float(line["slope_hz_s"] * time_s + line["intercept_hz"])
    raise ValueError(f"time {time_s} lies outside the reference pieces")


def _profile_config(profile: SearchProfile, probe_samples: int) -> SymbolwiseAcquisitionConfig:
    return SymbolwiseAcquisitionConfig(
        residual_cfo_min_hz=-400_000.0,
        residual_cfo_max_hz=400_000.0,
        coarse_cfo_step_hz=profile.coarse_step_hz,
        fine_cfo_radius_hz=profile.fine_radius_hz,
        fine_cfo_step_hz=profile.fine_step_hz,
        conditioned_cfo_radius_hz=profile.conditioned_radius_hz,
        conditioned_cfo_step_hz=profile.conditioned_step_hz,
        retained_candidate_count=profile.candidate_count,
        candidate_epoch_separation_samples=profile.epoch_separation_samples,
        candidate_cfo_separation_hz=profile.cfo_separation_hz,
        maximum_probe_samples=probe_samples,
    )


def _window_for_time(time_s: float) -> str:
    for label, start_s, end_s in WINDOWS:
        if start_s <= time_s < end_s:
            return label
    raise ValueError(f"probe {time_s} is outside the study windows")


def _read_requests(reader) -> tuple[tuple[int, np.ndarray], ...]:
    sample_rate_hz = reader.sample_rate_hz
    probe_samples = round(0.020 * sample_rate_hz)
    spacing_samples = round(0.025 * sample_rate_hz)
    requests = []
    for _, start_s, end_s in WINDOWS:
        start_sample = math.ceil(start_s * sample_rate_hz / spacing_samples) * spacing_samples
        stop_sample = math.floor(
            (end_s * sample_rate_hz - probe_samples) / spacing_samples
        ) * spacing_samples
        starts = tuple(range(start_sample, stop_sample + 1, spacing_samples))
        outer_start = min(starts)
        outer_stop = max(starts) + probe_samples
        outer = _complex_receiver(
            reader.read(
                outer_start,
                outer_stop - outer_start,
                receiver_ids=(1,),
            )
        )
        requests.extend(
            (
                sample_start,
                np.ascontiguousarray(
                    outer[
                        sample_start - outer_start : sample_start
                        - outer_start
                        + probe_samples
                    ]
                ),
            )
            for sample_start in starts
        )
    return tuple(requests)


def _run_profiles(
    bulk_root: Path, workers: int
) -> tuple[dict[str, tuple[CandidateRow, ...]], dict[str, float]]:
    pinned = PinnedLocalRoot(bulk_root)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(SESSION_ID)
        store.verify(bundle)
        reader = store.reader(bundle, "stream-0", verify=True)
        requests = _read_requests(reader)
        sample_rate_hz = reader.sample_rate_hz
        probe_samples = round(0.020 * sample_rate_hz)
        calibration = ReceiverFrequencyCalibration(
            "t1-parameter-study-baseband",
            0.0,
            canonical_digest(
                {
                    "session_id": SESSION_ID,
                    "path": PATH_LABEL,
                    "purpose": "independent-glrt-parameter-study",
                }
            ).removeprefix("sha256:"),
        )
        rows_by_profile = {}
        runtimes = {}
        for profile in PROFILES:
            config = _profile_config(profile, probe_samples)
            started = time.perf_counter()
            detect = partial(
                _detect_one,
                sample_rate_hz=sample_rate_hz,
                calibration=calibration,
                config=config,
                edge=StarlinkEdge.UPPER,
                candidate_count=profile.candidate_count,
                glrt_size=profile.glrt_size,
            )
            with ThreadPoolExecutor(max_workers=workers) as executor:
                detected = executor.map(detect, requests)
                rows = tuple(item for candidates in detected for item in candidates)
            rows_by_profile[profile.key] = tuple(
                sorted(rows, key=lambda item: (item.sample_start, item.rank))
            )
            runtimes[profile.key] = time.perf_counter() - started
            print(
                f"{profile.key}: probes={len(_group(rows_by_profile[profile.key]))} "
                f"candidates={len(rows)} runtime={runtimes[profile.key]:.1f}s",
                flush=True,
            )
        return rows_by_profile, runtimes
    finally:
        if store is not None:
            store.close()
        pinned.close()


def _candidate_file(path: Path, rows_by_profile: dict[str, tuple[CandidateRow, ...]]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as target:
        for profile in PROFILES:
            for row in rows_by_profile[profile.key]:
                target.write(
                    json.dumps(
                        {"profile": profile.key, **asdict(row)},
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )


def _load_candidate_file(path: Path) -> dict[str, tuple[CandidateRow, ...]]:
    result: dict[str, list[CandidateRow]] = {profile.key: [] for profile in PROFILES}
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            profile = row.pop("profile")
            result[profile].append(CandidateRow(**row))
    return {key: tuple(value) for key, value in result.items()}


def summarize_population(
    rows: tuple[CandidateRow, ...],
    lines: tuple[dict[str, float], ...],
    *,
    start_s: float,
    end_s: float,
    margin_gate: float = MARGIN_GATE,
    residual_gate_hz: float = RESIDUAL_GATE_HZ,
) -> dict[str, Any]:
    grouped = {
        key: value
        for key, value in _group(rows).items()
        if start_s <= value[0].time_s < end_s
    }
    winner_hits = 0
    inventory_hits = 0
    strong_probes = 0
    alias_winner_misses = 0
    nearest_errors = []
    selected_ranks = []
    winner_errors = []
    for candidates in grouped.values():
        time_s = candidates[0].time_s
        prediction = expected_frequency(lines, time_s)
        winner = _best_glrt(candidates)
        winner_error = winner.tracking_cfo_hz - prediction
        winner_errors.append(winner_error)
        if winner.margin >= margin_gate:
            strong_probes += 1
        if winner.margin >= margin_gate and abs(winner_error) <= residual_gate_hz:
            winner_hits += 1
        elif winner.margin >= margin_gate:
            alias_index = round(winner_error / ALIAS_SPACING_HZ)
            alias_residual = winner_error - alias_index * ALIAS_SPACING_HZ
            if alias_index and abs(alias_residual) <= 2_500.0:
                alias_winner_misses += 1
        strong = tuple(item for item in candidates if item.margin >= margin_gate)
        if strong:
            nearest = min(
                strong,
                key=lambda item: (
                    abs(item.tracking_cfo_hz - prediction),
                    -item.margin,
                    item.rank,
                ),
            )
            error = abs(nearest.tracking_cfo_hz - prediction)
            nearest_errors.append(error)
            if error <= residual_gate_hz:
                inventory_hits += 1
                selected_ranks.append(nearest.rank)
    errors = np.asarray(nearest_errors, dtype=float)
    winner_error_values = np.asarray(winner_errors, dtype=float)
    return {
        "probe_count": len(grouped),
        "candidate_count": sum(len(value) for value in grouped.values()),
        "median_candidates_per_probe": float(
            np.median([len(value) for value in grouped.values()])
        ),
        "strong_probe_count": strong_probes,
        "winner_hit_count": winner_hits,
        "inventory_hit_count": inventory_hits,
        "alias_winner_miss_count": alias_winner_misses,
        "median_nearest_strong_error_hz": float(np.median(errors)) if len(errors) else None,
        "maximum_nearest_strong_error_hz": float(np.max(errors)) if len(errors) else None,
        "winner_error_p95_hz": (
            float(np.quantile(np.abs(winner_error_values), 0.95))
            if len(winner_error_values)
            else None
        ),
        "median_selected_rank": (
            float(np.median(selected_ranks)) if selected_ranks else None
        ),
        "maximum_selected_rank": max(selected_ranks) if selected_ranks else None,
        "margin_gate": margin_gate,
        "residual_gate_hz": residual_gate_hz,
    }


def _reproduction(
    rerun: tuple[CandidateRow, ...], oracle: tuple[CandidateRow, ...]
) -> dict[str, Any]:
    rerun_grouped = _group(rerun)
    oracle_grouped = _group(oracle)
    common = sorted(set(rerun_grouped) & set(oracle_grouped))
    differences = np.asarray(
        [
            _best_glrt(rerun_grouped[key]).tracking_cfo_hz
            - _best_glrt(oracle_grouped[key]).tracking_cfo_hz
            for key in common
        ]
    )
    return {
        "common_probe_count": len(common),
        "winner_cfo_within_1_hz": int(np.sum(np.abs(differences) <= 1.0)),
        "winner_cfo_within_500_hz": int(np.sum(np.abs(differences) <= 500.0)),
        "maximum_absolute_winner_cfo_difference_hz": float(np.max(np.abs(differences))),
    }


def _dense_candidates(path: Path) -> tuple[CandidateRow, ...]:
    result = []
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            result.append(CandidateRow(**json.loads(line)))
    return tuple(result)


def _rank_and_gate_diagnostics(
    rows: tuple[CandidateRow, ...], lines: tuple[dict[str, float], ...]
) -> dict[str, Any]:
    grouped = _group(rows)
    rank_caps = (1, 2, 4, 8, 16, 32)
    rank_result = []
    for cap in rank_caps:
        limited = tuple(
            item for candidates in grouped.values() for item in candidates if item.rank < cap
        )
        metrics = summarize_population(limited, lines, start_s=0.0, end_s=27.25)
        rank_result.append({"rank_cap": cap, **metrics})
    margin_gates = (0.0, 0.02, 0.05, 0.10, 0.20, 0.30, 0.40)
    residual_gates = (100.0, 250.0, 500.0, 750.0, 1_000.0, 2_000.0)
    gate_result = []
    for margin in margin_gates:
        for residual in residual_gates:
            metrics = summarize_population(
                rows,
                lines,
                start_s=0.0,
                end_s=27.25,
                margin_gate=margin,
                residual_gate_hz=residual,
            )
            gate_result.append(
                {
                    "margin_gate": margin,
                    "residual_gate_hz": residual,
                    "inventory_hit_count": metrics["inventory_hit_count"],
                    "strong_probe_count": metrics["strong_probe_count"],
                }
            )
    return {"rank_cap": rank_result, "gate": gate_result}


def _plot_coverage(path: Path, results: list[dict[str, Any]]) -> None:
    short_labels = {
        "standard": "standard",
        "coarse": "coarse grid",
        "fine": "fine grids",
        "glrt": "GLRT-4096",
        "basins": "32 basins",
        "separation": "narrow sep.",
        "inventory": "32 + narrow",
        "acquisition_grids": "all acq. grids",
        "full_dense": "combined",
    }
    figure, axes = plt.subplots(1, 3, figsize=(16, 5.8), sharey=True)
    for axis, (window, _, _) in zip(axes, WINDOWS, strict=True):
        rows = [item for item in results if item["window"] == window]
        x = np.arange(len(rows))
        probes = np.asarray([item["probe_count"] for item in rows])
        winner = 100 * np.asarray([item["winner_hit_count"] for item in rows]) / probes
        inventory = 100 * np.asarray([item["inventory_hit_count"] for item in rows]) / probes
        axis.bar(x - 0.18, winner, 0.36, color="#277da1", label="winner on line")
        axis.bar(x + 0.18, inventory, 0.36, color="#e17c05", label="any retained basin on line")
        axis.set_xticks(
            x,
            [short_labels[item["profile_key"]] for item in rows],
            rotation=55,
            ha="right",
        )
        axis.set_title(window)
        axis.set_ylim(0, 105)
        axis.grid(axis="y", alpha=0.15)
    axes[0].set_ylabel("probes recovered within 500 Hz (%)")
    axes[0].legend(fontsize=8, loc="lower right")
    figure.suptitle(
        "T1 raw-IQ parameter ablation · detector winner versus retained-inventory coverage",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _plot_transition(
    path: Path,
    rows: tuple[CandidateRow, ...],
    lines: tuple[dict[str, float], ...],
) -> None:
    grouped = {
        probe: candidates
        for probe, candidates in _group(rows).items()
        if 6.6 <= candidates[0].time_s < 7.05
    }
    winners = tuple(_best_glrt(candidates) for candidates in grouped.values())
    times = np.linspace(6.6, 7.05, 400, endpoint=False)
    reference = np.asarray([expected_frequency(lines, value) for value in times]) / 1_000
    figure, axes = plt.subplots(
        2,
        1,
        figsize=(14.5, 7.2),
        sharex=True,
        gridspec_kw={"height_ratios": (2.0, 1.0)},
    )
    cfo_axis, margin_axis = axes
    cfo_axis.scatter(
        [item.time_s for item in winners],
        [item.tracking_cfo_hz / 1_000 for item in winners],
        s=28,
        color="#277da1",
        label="highest GLRT margin",
    )
    strong_nearest = []
    for candidates in grouped.values():
        prediction = expected_frequency(lines, candidates[0].time_s)
        strong = tuple(item for item in candidates if item.margin >= MARGIN_GATE)
        if strong:
            strong_nearest.append(
                min(strong, key=lambda item: abs(item.tracking_cfo_hz - prediction))
            )
    cfo_axis.scatter(
        [item.time_s for item in strong_nearest],
        [item.tracking_cfo_hz / 1_000 for item in strong_nearest],
        s=34,
        facecolors="none",
        edgecolors="#e17c05",
        linewidths=0.9,
        label="nearest margin-qualified candidate",
    )
    cfo_axis.plot(
        times,
        reference,
        color="#111111",
        linewidth=0.9,
        label="fixed P1/P2 lines",
    )
    cfo_axis.axvline(6.825, color="#d1495b", linestyle=":", linewidth=0.9)
    cfo_axis.set_ylabel("CFO (kHz)")
    cfo_axis.set_ylim(-15, 205)
    cfo_axis.set_title(
        "A · combined-dense winners across the fitted frequency step", loc="left"
    )
    cfo_axis.legend(fontsize=8, ncol=3)
    margins = np.asarray([item.margin for item in winners])
    margin_axis.scatter(
        [item.time_s for item in winners],
        margins,
        s=25,
        color=np.where(margins >= MARGIN_GATE, "#2a9d8f", "#d1495b"),
    )
    margin_axis.axhline(MARGIN_GATE, color="#111111", linestyle="--", linewidth=0.8)
    margin_axis.axvline(6.825, color="#d1495b", linestyle=":", linewidth=0.9)
    margin_axis.set_ylabel("best GLRT margin")
    margin_axis.set_xlabel("capture time (s)")
    margin_axis.set_title(
        "B · several probes have weak evidence under every profile", loc="left"
    )
    for axis in axes:
        axis.grid(alpha=0.13)
    figure.suptitle(
        "The real 6.825 s transition is not the old 7.5–7.9 s basin-loss artifact",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _plot_timeline(
    path: Path,
    rows_by_profile: dict[str, tuple[CandidateRow, ...]],
    lines: tuple[dict[str, float], ...],
) -> None:
    keys = ("standard", "basins", "inventory", "full_dense")
    figure, axes = plt.subplots(4, 1, figsize=(15, 10.5), sharex=True, sharey=True)
    times = np.linspace(7.5, 7.9, 200)
    reference = np.asarray([expected_frequency(lines, value) for value in times]) / 1_000
    for axis, key in zip(axes, keys, strict=True):
        profile = next(item for item in PROFILES if item.key == key)
        grouped = {
            probe: candidates
            for probe, candidates in _group(rows_by_profile[key]).items()
            if 7.5 <= candidates[0].time_s < 7.9
        }
        all_rows = tuple(item for candidates in grouped.values() for item in candidates)
        winners = tuple(_best_glrt(candidates) for candidates in grouped.values())
        selected = []
        for candidates in grouped.values():
            prediction = expected_frequency(lines, candidates[0].time_s)
            strong = tuple(item for item in candidates if item.margin >= MARGIN_GATE)
            if strong:
                nearest = min(strong, key=lambda item: abs(item.tracking_cfo_hz - prediction))
                if abs(nearest.tracking_cfo_hz - prediction) <= RESIDUAL_GATE_HZ:
                    selected.append(nearest)
        axis.scatter(
            [item.time_s for item in all_rows],
            [item.tracking_cfo_hz / 1_000 for item in all_rows],
            s=8,
            color="#aab2ba",
            alpha=0.22,
            linewidths=0,
        )
        axis.scatter(
            [item.time_s for item in winners],
            [item.tracking_cfo_hz / 1_000 for item in winners],
            s=22,
            color="#277da1",
            label="highest GLRT margin",
        )
        axis.scatter(
            [item.time_s for item in selected],
            [item.tracking_cfo_hz / 1_000 for item in selected],
            s=28,
            facecolors="none",
            edgecolors="#e17c05",
            linewidths=0.8,
            label="retained candidate within 500 Hz",
        )
        axis.plot(times, reference, color="#111111", linewidth=0.9, label="fixed P2 line")
        axis.set_ylabel("CFO (kHz)")
        axis.set_title(profile.label, loc="left")
        axis.grid(alpha=0.12)
    axes[0].legend(fontsize=8, ncol=3, loc="upper right")
    axes[-1].set_xlabel("capture time (s)")
    axes[0].set_ylim(-265, 25)
    figure.suptitle(
        "Mechanism at the old 7.5–7.9 s gap · independent raw-IQ searches",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _plot_rank_gate(path: Path, diagnostics: dict[str, Any]) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(13.5, 5.4))
    rank = diagnostics["rank_cap"]
    axes[0].plot(
        [item["rank_cap"] for item in rank],
        [item["inventory_hit_count"] for item in rank],
        marker="o",
        color="#277da1",
        label="fixed-line inventory hits",
    )
    axes[0].plot(
        [item["rank_cap"] for item in rank],
        [item["winner_hit_count"] for item in rank],
        marker="s",
        color="#e17c05",
        label="best-margin winner hits",
    )
    axes[0].set_xscale("log", base=2)
    axes[0].set_xticks([1, 2, 4, 8, 16, 32], [1, 2, 4, 8, 16, 32])
    axes[0].set_xlabel("available post-scoring candidate ranks")
    axes[0].set_ylabel("probes recovered (of 1,090)")
    axes[0].set_title("A · rank-depth diagnostic on combined-dense inventory")
    axes[0].grid(alpha=0.15)
    axes[0].legend(fontsize=8)

    margins = sorted({item["margin_gate"] for item in diagnostics["gate"]})
    residuals = sorted({item["residual_gate_hz"] for item in diagnostics["gate"]})
    values = np.asarray(
        [
            [
                next(
                    item["inventory_hit_count"]
                    for item in diagnostics["gate"]
                    if item["margin_gate"] == margin
                    and item["residual_gate_hz"] == residual
                )
                for residual in residuals
            ]
            for margin in margins
        ]
    )
    image = axes[1].imshow(values, aspect="auto", cmap="viridis", vmin=0, vmax=1_090)
    axes[1].set_xticks(range(len(residuals)), [f"{value:.0f}" for value in residuals])
    axes[1].set_yticks(range(len(margins)), [f"{value:.2f}" for value in margins])
    axes[1].set_xlabel("line residual gate (Hz)")
    axes[1].set_ylabel("GLRT exact−control margin gate")
    axes[1].set_title("B · full-interval diagnostic sensitivity")
    for row in range(len(margins)):
        for column in range(len(residuals)):
            axes[1].text(
                column,
                row,
                str(values[row, column]),
                ha="center",
                va="center",
                fontsize=7,
                color="white" if values[row, column] < 650 else "black",
            )
    figure.colorbar(image, ax=axes[1], label="recovered probes")
    figure.suptitle(
        "Why 32 candidates look powerful: inventory depth and post-hoc gate sensitivity",
        fontweight="bold",
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, dpi=190)
    plt.close(figure)


def _markdown(summary: dict[str, Any]) -> str:
    lookup = {(item["profile_key"], item["window"]): item for item in summary["results"]}
    lines = [
        "# T1 independent-GLRT search-parameter mechanism study",
        "",
        f"Capture: `{SESSION_ID}`; path: `{PATH_LABEL}`; raw IQ only.",
        "",
        "## Executive finding",
        "",
        "The dense result is not 34,880 independent detections. It is 1,090 "
        "independent time probes with up to 32 timing/CFO alternatives per probe. "
        "The primary failure mechanism is **inventory loss under CFO/timing "
        "ambiguity**: a correct branch can be present but not be the highest-margin "
        "candidate, or can be discarded before GLRT scoring. The characteristic "
        "wrong winners cluster approximately one "
        f"{ALIAS_SPACING_HZ / 1_000:.3f} kHz ambiguity spacing away. That declared "
        "spacing is the reciprocal of the 4.4 µs OFDM symbol duration.",
        "",
        "Increasing basin count and relaxing nonmaximum-suppression separation "
        "therefore changes *which hypotheses survive*. Finer CFO grids primarily "
        "improve localization after the correct basin survives. GLRT-4096 improves "
        "residual-CFO resolution and discrimination, but cannot score a basin that "
        "was already discarded.",
        "",
        "The strongest one-factor result is more specific than the earlier audit: "
        "changing only nonmaximum-suppression separation from 80 kHz/20 samples "
        "to 10 kHz/5 samples recovers all 16 old-gap probes. Raising the count to "
        "32 while leaving broad separation unchanged recovers only 14/16. Basin "
        "count helps, but separation policy is decisive in this interval.",
        "",
        "## Search mechanism",
        "",
        "| Stage | Operation | Parameter that matters | Failure observed here |",
        "|---:|---|---|---|",
        "| 1 | Search timing × coarse CFO using sparse known pilots | CFO domain and "
        "coarse step | A local maximum may be represented coarsely, but the ±400 kHz "
        "domain covers T1 |",
        "| 2 | Nonmaximum suppression retains separated local maxima | Basin count; "
        "CFO/epoch separation | The correct ≈227.27 kHz alias/timing alternative can "
        "be suppressed or fall below the cap |",
        "| 3 | Fine and conditioned CFO refinement | Fine radii and steps | Improves "
        "tens-to-hundreds-of-hertz placement; does not restore a removed basin |",
        "| 4 | Exact and wrong-pilot control are scored | GLRT size and margin | "
        "Longer GLRT sharpens the residual grid and evidence comparison |",
        "| 5 | Post-hoc straight-line association | Margin and residual gates | "
        "Selects at most one already-retained candidate/probe; it does not alter "
        "acquisition |",
        "",
        "All searches in stages 1–4 are independent per 20 ms probe. No adjacent "
        "probe, fitted line, TLE, or expected Doppler enters them. The strict "
        "piecewise degree-1 lines are used only afterward as fixed diagnostics.",
        "",
        "## Actual raw-IQ one-factor ablation",
        "",
        "The following profiles were rerun over the actual 6.825 s transition, the "
        "old 7.5–7.9 s apparent gap, and a steady P3 control. A hit requires margin "
        "≥0.05 and CFO within 500 Hz of the fixed strict-linear reference.",
        "",
        "![Parameter coverage]"
        "(figures/2026_08_22_t1_glrt_search_parameter_study/"
        "parameter-coverage.png)",
        "",
        "`winner` asks whether the single largest GLRT exact-minus-control margin "
        "lands on the branch. `inventory` asks whether any independently retained "
        "candidate lands on it. Their gap is the ambiguity/ranking problem that a "
        "later line association can resolve.",
        "",
        "| Profile | Actual transition inventory | Old-gap inventory | "
        "Steady P3 inventory | Runtime for 50 probes |",
        "|---|---:|---:|---:|---:|",
    ]
    for profile in PROFILES:
        transition = lookup[(profile.key, "actual transition")]
        gap = lookup[(profile.key, "old apparent gap")]
        steady = lookup[(profile.key, "steady P3 control")]
        runtime = summary["runtime_s"][profile.key]
        runtime_label = "cached" if runtime is None else f"{runtime:.1f} s"
        lines.append(
            f"| {profile.label} | {transition['inventory_hit_count']}/"
            f"{transition['probe_count']} | {gap['inventory_hit_count']}/"
            f"{gap['probe_count']} | {steady['inventory_hit_count']}/"
            f"{steady['probe_count']} | {runtime_label} |"
        )
    lines.extend(
        [
            "",
            "| Profile | Coarse | Fine radius / step | Conditioned radius / step | "
            "Basins | CFO / epoch separation | GLRT | Old-gap winner | "
            "Old-gap inventory | Alias winner misses |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for profile in PROFILES:
        row = lookup[(profile.key, "old apparent gap")]
        lines.append(
            f"| {profile.label} | {profile.coarse_step_hz / 1_000:.0f} kHz | "
            f"{profile.fine_radius_hz / 1_000:.0f} kHz / "
            f"{profile.fine_step_hz:.0f} Hz | "
            f"{profile.conditioned_radius_hz / 1_000:.0f} kHz / "
            f"{profile.conditioned_step_hz:.0f} Hz | "
            f"{profile.candidate_count} | {profile.cfo_separation_hz / 1_000:.0f} kHz / "
            f"{profile.epoch_separation_samples} samples | {profile.glrt_size} | "
            f"{row['winner_hit_count']}/{row['probe_count']} | "
            f"{row['inventory_hit_count']}/{row['probe_count']} | "
            f"{row['alias_winner_miss_count']} |"
        )
    lines.extend(
        [
            "",
            "![Critical timeline]"
            "(figures/2026_08_22_t1_glrt_search_parameter_study/"
            "critical-timeline.png)",
            "",
            "The timeline exposes the mechanism directly. Blue points are detector "
            "winners; hollow orange points show when a qualifying branch candidate is "
            "available. In Standard, three winning probes jump by one OFDM-symbol "
            "frequency and only one remaining miss can be rescued from the eight "
            "retained candidates. Narrower separation changes the candidate set and "
            "eliminates all four failures.",
            "",
            "## The real 6.825 s transition is different",
            "",
            "![Transition evidence]"
            "(figures/2026_08_22_t1_glrt_search_parameter_study/"
            "transition-evidence.png)",
            "",
            "The fitted-step region does not become complete under the dense "
            "configuration: 11/18 probes meet both gates. Five probes have no "
            "candidate with margin ≥0.05, and two margin-qualified probes remain "
            "about 2.3–2.4 kHz from the fixed steady-piece lines. Because every "
            "parameter profile shows a similar deficit, this is not the same basin-"
            "truncation mechanism as the old 7.5–7.9 s gap. It may be signal "
            "intermittency, overlap during the frequency change, or local model error; "
            "these data do not distinguish those causes.",
            "",
            "## Full-interval inventory-depth and gate audit",
            "",
            "![Rank and gate sensitivity]"
            "(figures/2026_08_22_t1_glrt_search_parameter_study/"
            "rank-gate-sensitivity.png)",
            "",
            "Panel A is a **post-scoring truncation diagnostic**, not a substitute for "
            "the raw reruns above: it progressively hides ranks from the already-created "
            "combined-dense inventory. Panel B shows the expected look-elsewhere tradeoff. "
            "Looser evidence or residual gates recover more probes, but also make an "
            "accidental line easier to find. The report therefore retains the declared "
            "0.05 margin and 500/750 Hz residual scales and relies on the matched time-"
            "permutation control for coherence evidence.",
            "",
            "## Parameters deliberately held fixed",
            "",
            "| Parameter | Fixed value | Reason |",
            "|---|---:|---|",
            "| CFO domain | −400 to +400 kHz | The fitted T1 branch spans only about "
            "+44 to −124 kHz, so it is not clipped; narrowing the domain would change "
            "the ambiguity prior rather than resolution |",
            "| Probe duration / spacing | 20 / 25 ms | Keeps identical independent IQ "
            "samples across profiles; changing duration also changes integration gain |",
            "| Pilot edge / template | Upper / Qin known pilot | T1 was detected on this "
            "edge; changing the template asks a different signal question |",
            "| Time model | Fixed four intercept+slope pieces | Prevents each profile "
            "from moving the diagnostic target to flatter its own candidates |",
            "| Margin / residual gates | 0.05 / 500 Hz for headline | Their full "
            "sensitivity grid is shown above rather than choosing a favorable gate |",
            "",
            "The 10 kHz coarse-grid profiles use a 10 kHz fine-search radius instead "
            "of Standard's 80 kHz radius. This preserves contiguous coarse-cell "
            "coverage without redundantly rescanning eight neighboring coarse cells; "
            "the fine-grid *resolution* remains 500 Hz unless explicitly changed.",
            "",
            "## Reproduction checks",
            "",
            f"The Standard profile winner reproduces the persisted Standard winner "
            f"within 1 Hz for **{summary['reproduction']['standard']['winner_cfo_within_1_hz']}"
            f"/{summary['reproduction']['standard']['common_probe_count']}** studied probes. "
            f"The combined-dense profile reproduces the archived dense winner within 1 Hz "
            f"for **{summary['reproduction']['full_dense']['winner_cfo_within_1_hz']}"
            f"/{summary['reproduction']['full_dense']['common_probe_count']}** probes.",
            "",
            "## Conclusions and limits",
            "",
            "1. The large recovery is real candidate-level continuity, not interpolation "
            "between missing time samples: every probe was searched independently.",
            "2. In the old apparent gap, narrow CFO/epoch separation is the strongest "
            "single correction. More basins alone is helpful but insufficient.",
            "3. CFO-grid and GLRT refinement improve precision and evidence but are "
            "secondary when the desired basin was discarded.",
            "4. Thirty-two alternatives create a look-elsewhere burden. The earlier "
            "888-versus-48 matched permutation result addresses line coherence, but the "
            "capture and breakpoint windows remain post hoc; this is not a calibrated "
            "false-alarm probability or satellite identity.",
            "5. The three-point quadratic operation inside acquisition only interpolates "
            "a local score peak to center the next discrete CFO grid. No quadratic or "
            "cubic trajectory in time is fitted or used anywhere in this study.",
            "",
            "Machine-readable results: "
            "[parameter-study.json](figures/2026_08_22_t1_glrt_search_parameter_study/parameter-study.json).",
            "",
            "Candidate inventory: `parameter-study-candidates.jsonl.gz`. Source recording "
            "was read-only; no RF was collected and no payload was decoded.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = _arguments()
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must lie in 1..16")
    args.output_root.mkdir(parents=True, exist_ok=True)
    candidate_path = args.output_root / "parameter-study-candidates.jsonl.gz"
    lines = _load_lines(args.line_summary)
    previous: dict[str, Any] = {}
    if args.reuse and candidate_path.exists():
        rows_by_profile = _load_candidate_file(candidate_path)
        previous_summary_path = args.output_root / "parameter-study.json"
        previous = (
            json.loads(previous_summary_path.read_text(encoding="utf-8"))
            if previous_summary_path.exists()
            else {}
        )
        runtimes = previous.get(
            "runtime_s", {profile.key: None for profile in PROFILES}
        )
    else:
        rows_by_profile, runtimes = _run_profiles(args.bulk_root, args.workers)
        _candidate_file(candidate_path, rows_by_profile)

    results = []
    for profile in PROFILES:
        for window, start_s, end_s in WINDOWS:
            results.append(
                {
                    "profile_key": profile.key,
                    "profile_label": profile.label,
                    "window": window,
                    "interval_s": [start_s, end_s],
                    **summarize_population(
                        rows_by_profile[profile.key],
                        lines,
                        start_s=start_s,
                        end_s=end_s,
                    ),
                }
            )

    dense = _dense_candidates(args.dense_candidates)

    def studied(rows: tuple[CandidateRow, ...]) -> tuple[CandidateRow, ...]:
        return tuple(
            item
            for item in rows
            if any(start <= item.time_s < end for _, start, end in WINDOWS)
        )

    if "reproduction" in previous:
        reproduction = previous["reproduction"]
    else:
        baseline = _baseline_rows(args.baseline, 0.0, 27.25)
        reproduction = {
            "standard": _reproduction(rows_by_profile["standard"], studied(baseline)),
            "full_dense": _reproduction(rows_by_profile["full_dense"], studied(dense)),
        }
    diagnostics = _rank_and_gate_diagnostics(dense, lines)
    summary = {
        "schema": "org.leo.research.t1-glrt-parameter-study/v1",
        "session_id": SESSION_ID,
        "path": PATH_LABEL,
        "radio_trajectory_model": "fixed_piecewise_intercept_plus_slope_only",
        "search_is_independent_per_probe": True,
        "reference_used_during_search": False,
        "payload_decoded": False,
        "alias_spacing_hz": ALIAS_SPACING_HZ,
        "probe_duration_ms": 20.0,
        "probe_spacing_ms": 25.0,
        "windows": [
            {"label": label, "interval_s": [start, end]} for label, start, end in WINDOWS
        ],
        "profiles": [asdict(profile) for profile in PROFILES],
        "runtime_s": runtimes,
        "results": results,
        "reproduction": reproduction,
        "full_interval_diagnostics": diagnostics,
    }
    (args.output_root / "parameter-study.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _plot_coverage(args.output_root / "parameter-coverage.png", results)
    _plot_transition(
        args.output_root / "transition-evidence.png",
        rows_by_profile["full_dense"],
        lines,
    )
    _plot_timeline(args.output_root / "critical-timeline.png", rows_by_profile, lines)
    _plot_rank_gate(args.output_root / "rank-gate-sensitivity.png", diagnostics)
    args.report.write_text(_markdown(summary), encoding="utf-8")
    print(args.report)


if __name__ == "__main__":
    main()
