#!/usr/bin/env python3
"""Compare exact-transform and hardware-aligned GLRT search profiles on T1 IQ.

The study is deliberately bounded to 50 immutable 20 ms probes in the three
diagnostic windows established by the earlier T1 parameter report.  Every
probe remains independent; the piecewise-linear frequency reference is used
only after detection to summarize the returned candidate inventory.
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal
from unittest.mock import patch

import numpy as np

import leo.analysis.starlink.acquisition as acquisition
import leo.analysis.starlink.pilot_methods as pilot_methods
from leo.analysis.starlink.acquisition import (
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.states import StarlinkEdge
from leo.storage import PinnedLocalRoot, RecordingStore

try:
    from tools.report_t1_glrt_search_parameter_study import (
        DEFAULT_LINES,
        PATH_LABEL,
        SESSION_ID,
        WINDOWS,
        _best_glrt,
        _group,
        _load_lines,
        _read_requests,
        summarize_population,
    )
    from tools.rerun_dense_independent_glrt import CandidateRow, _detect_one
except ModuleNotFoundError:  # direct ``python tools/...`` execution
    from report_t1_glrt_search_parameter_study import (  # type: ignore[no-redef]
        DEFAULT_LINES,
        PATH_LABEL,
        SESSION_ID,
        WINDOWS,
        _best_glrt,
        _group,
        _load_lines,
        _read_requests,
        summarize_population,
    )
    from rerun_dense_independent_glrt import (  # type: ignore[no-redef]
        CandidateRow,
        _detect_one,
    )

SAMPLE_RATE_HZ = 2_500_000
STANDARD_ALIGNED_STEP_HZ = SAMPLE_RATE_HZ / 4_096
STANDARD_ALIGNED_RADIUS_HZ = 131 * STANDARD_ALIGNED_STEP_HZ
STANDARD_FINER_STEP_HZ = SAMPLE_RATE_HZ / 8_192
STANDARD_FINER_RADIUS_HZ = 262 * STANDARD_FINER_STEP_HZ
RESEARCH_ALIGNED_STEP_HZ = SAMPLE_RATE_HZ / 16_384
RESEARCH_ALIGNED_RADIUS_HZ = 66 * RESEARCH_ALIGNED_STEP_HZ
RESEARCH_FINER_STEP_HZ = SAMPLE_RATE_HZ / 32_768
RESEARCH_FINER_RADIUS_HZ = 132 * RESEARCH_FINER_STEP_HZ

DEFAULT_OUTPUT = Path("reports/figures/2026_08_22_t1_glrt_hardware_aligned_parameter_study")
DEFAULT_REPORT = Path("reports/2026_08_22_t1_glrt_hardware_aligned_parameter_study.md")


@dataclass(frozen=True, slots=True)
class SearchProfile:
    key: str
    lane: Literal["standard", "research"]
    label: str
    kernel_mode: Literal["direct", "exact"] = "exact"
    coarse_step_hz: float = 80_000.0
    fine_radius_hz: float = 80_000.0
    fine_step_hz: float = 500.0
    conditioned_radius_hz: float = 2_000.0
    conditioned_step_hz: float = 100.0
    candidate_count: int = 10
    cfo_separation_hz: float = 10_000.0
    epoch_separation_samples: int = 5
    glrt_size: int = 512


_STANDARD_DIRECT = SearchProfile(
    "standard_direct", "standard", "Standard current parameters, direct oracle", "direct"
)
_STANDARD_CURRENT = SearchProfile(
    "standard_current", "standard", "Standard current parameters, exact dispatch"
)
_STANDARD_ALIGNED = SearchProfile(
    "standard_aligned",
    "standard",
    "Standard radix-2 aligned",
    fine_radius_hz=STANDARD_ALIGNED_RADIUS_HZ,
    fine_step_hz=STANDARD_ALIGNED_STEP_HZ,
)
_STANDARD_FINER = SearchProfile(
    "standard_finer",
    "standard",
    "Standard finer radix-2",
    fine_radius_hz=STANDARD_FINER_RADIUS_HZ,
    fine_step_hz=STANDARD_FINER_STEP_HZ,
)
_RESEARCH_ARGUMENTS = {
    "coarse_step_hz": 10_000.0,
    "conditioned_radius_hz": 1_000.0,
    "conditioned_step_hz": 25.0,
    "candidate_count": 32,
    "glrt_size": 4_096,
}
_RESEARCH_DIRECT = SearchProfile(
    "research_direct",
    "research",
    "Research current parameters, direct oracle",
    "direct",
    fine_radius_hz=10_000.0,
    fine_step_hz=100.0,
    **_RESEARCH_ARGUMENTS,
)
_RESEARCH_CURRENT = SearchProfile(
    "research_current",
    "research",
    "Research current parameters, exact dispatch",
    fine_radius_hz=10_000.0,
    fine_step_hz=100.0,
    **_RESEARCH_ARGUMENTS,
)
_RESEARCH_ALIGNED = SearchProfile(
    "research_aligned",
    "research",
    "Research radix-2 aligned",
    fine_radius_hz=RESEARCH_ALIGNED_RADIUS_HZ,
    fine_step_hz=RESEARCH_ALIGNED_STEP_HZ,
    **_RESEARCH_ARGUMENTS,
)
_RESEARCH_FINER = SearchProfile(
    "research_finer",
    "research",
    "Research finer radix-2",
    fine_radius_hz=RESEARCH_FINER_RADIUS_HZ,
    fine_step_hz=RESEARCH_FINER_STEP_HZ,
    **_RESEARCH_ARGUMENTS,
)

PROFILES = (
    _STANDARD_DIRECT,
    _STANDARD_CURRENT,
    _STANDARD_ALIGNED,
    _STANDARD_FINER,
    _RESEARCH_DIRECT,
    _RESEARCH_CURRENT,
    _RESEARCH_ALIGNED,
    _RESEARCH_FINER,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--line-summary", type=Path, default=DEFAULT_LINES)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--reuse", action="store_true")
    return parser.parse_args()


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


@contextmanager
def _selected_kernels(mode: Literal["direct", "exact"]) -> Iterator[None]:
    if mode == "exact":
        yield
        return
    with (
        patch.object(
            acquisition,
            "_normalized_frame_scores",
            acquisition._normalized_frame_scores_direct,
        ),
        patch.object(pilot_methods, "_glrt_pair", pilot_methods._glrt_pair_direct),
    ):
        yield


def _detect_profile(
    profile: SearchProfile,
    requests: tuple[tuple[int, np.ndarray], ...],
    *,
    sample_rate_hz: int,
    calibration: ReceiverFrequencyCalibration,
    workers: int,
) -> tuple[CandidateRow, ...]:
    config = _profile_config(profile, requests[0][1].size)
    detect = partial(
        _detect_one,
        sample_rate_hz=sample_rate_hz,
        calibration=calibration,
        config=config,
        edge=StarlinkEdge.UPPER,
        candidate_count=profile.candidate_count,
        glrt_size=profile.glrt_size,
    )
    with (
        _selected_kernels(profile.kernel_mode),
        ThreadPoolExecutor(max_workers=workers) as executor,
    ):
        detected = executor.map(detect, requests)
        rows = tuple(item for candidates in detected for item in candidates)
    return tuple(sorted(rows, key=lambda item: (item.sample_start, item.rank)))


def _row_digest(rows: tuple[CandidateRow, ...]) -> str:
    return canonical_digest([asdict(row) for row in rows])


def _run_profiles(
    bulk_root: Path,
    workers: int,
    repeats: int,
) -> tuple[dict[str, tuple[CandidateRow, ...]], dict[str, dict[str, Any]]]:
    pinned = PinnedLocalRoot(bulk_root)
    store: RecordingStore | None = None
    try:
        store = RecordingStore.open_pinned(pinned)
        bundle = store.inspect(SESSION_ID)
        store.verify(bundle)
        reader = store.reader(bundle, "stream-0", verify=True)
        requests = _read_requests(reader)
        calibration = ReceiverFrequencyCalibration(
            "t1-hardware-aligned-study-baseband",
            0.0,
            canonical_digest(
                {
                    "session_id": SESSION_ID,
                    "path": PATH_LABEL,
                    "purpose": "glrt-hardware-aligned-parameter-study",
                }
            ).removeprefix("sha256:"),
        )
        rows_by_profile: dict[str, tuple[CandidateRow, ...]] = {}
        timings: dict[str, dict[str, Any]] = {}
        for profile in PROFILES:
            _detect_profile(
                profile,
                requests[:1],
                sample_rate_hz=reader.sample_rate_hz,
                calibration=calibration,
                workers=1,
            )
            wall_repetitions = []
            cpu_repetitions = []
            expected_digest: str | None = None
            selected_rows: tuple[CandidateRow, ...] = ()
            for _ in range(repeats):
                cpu_started = time.process_time()
                wall_started = time.perf_counter()
                rows = _detect_profile(
                    profile,
                    requests,
                    sample_rate_hz=reader.sample_rate_hz,
                    calibration=calibration,
                    workers=workers,
                )
                wall_repetitions.append(time.perf_counter() - wall_started)
                cpu_repetitions.append(time.process_time() - cpu_started)
                digest = _row_digest(rows)
                if expected_digest is not None and digest != expected_digest:
                    raise RuntimeError(f"{profile.key} did not reproduce across timing repetitions")
                expected_digest = digest
                selected_rows = rows
            rows_by_profile[profile.key] = selected_rows
            timings[profile.key] = {
                "wall_s_repetitions": wall_repetitions,
                "process_cpu_s_repetitions": cpu_repetitions,
                "median_wall_s": float(np.median(wall_repetitions)),
                "median_process_cpu_s": float(np.median(cpu_repetitions)),
                "probe_count": len(_group(selected_rows)),
                "candidate_count": len(selected_rows),
                "result_digest": expected_digest,
            }
            print(
                f"{profile.key}: probes={len(_group(selected_rows))} "
                f"candidates={len(selected_rows)} "
                f"wall={timings[profile.key]['median_wall_s']:.3f}s "
                f"cpu={timings[profile.key]['median_process_cpu_s']:.3f}s",
                flush=True,
            )
        return rows_by_profile, timings
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
            document = json.loads(line)
            key = document.pop("profile")
            result[key].append(CandidateRow(**document))
    return {key: tuple(rows) for key, rows in result.items()}


def _scientific_delta(
    reference: tuple[CandidateRow, ...], candidate: tuple[CandidateRow, ...]
) -> dict[str, Any]:
    reference_grouped = _group(reference)
    candidate_grouped = _group(candidate)
    common_probes = sorted(reference_grouped.keys() & candidate_grouped.keys())
    matched: list[tuple[CandidateRow, CandidateRow]] = []
    for sample_start in common_probes:
        epochs = {row.local_epoch_sample for row in reference_grouped[sample_start]} & {
            row.local_epoch_sample for row in candidate_grouped[sample_start]
        }
        for epoch in epochs:
            reference_at_epoch = sorted(
                (row for row in reference_grouped[sample_start] if row.local_epoch_sample == epoch),
                key=lambda row: (row.acquired_cfo_hz, row.rank),
            )
            candidate_at_epoch = sorted(
                (row for row in candidate_grouped[sample_start] if row.local_epoch_sample == epoch),
                key=lambda row: (row.acquired_cfo_hz, row.rank),
            )
            if len(reference_at_epoch) == len(candidate_at_epoch):
                matched.extend(zip(reference_at_epoch, candidate_at_epoch, strict=True))
                continue
            possible = sorted(
                (
                    (
                        abs(candidate_row.acquired_cfo_hz - reference_row.acquired_cfo_hz),
                        reference_row.rank,
                        candidate_row.rank,
                        reference_row,
                        candidate_row,
                    )
                    for reference_row in reference_at_epoch
                    for candidate_row in candidate_at_epoch
                ),
                key=lambda item: item[:3],
            )
            used_reference_ranks: set[int] = set()
            used_candidate_ranks: set[int] = set()
            for _, reference_rank, candidate_rank, reference_row, candidate_row in possible:
                if reference_rank in used_reference_ranks or candidate_rank in used_candidate_ranks:
                    continue
                used_reference_ranks.add(reference_rank)
                used_candidate_ranks.add(candidate_rank)
                matched.append((reference_row, candidate_row))

    def maximum(field: str) -> float | None:
        differences = [
            abs(float(getattr(candidate_row, field)) - float(getattr(reference_row, field)))
            for reference_row, candidate_row in matched
        ]
        return max(differences) if differences else None

    winner_differences = [
        _best_glrt(candidate_grouped[key]).tracking_cfo_hz
        - _best_glrt(reference_grouped[key]).tracking_cfo_hz
        for key in common_probes
    ]
    winner_epoch_changes = sum(
        _best_glrt(candidate_grouped[key]).local_epoch_sample
        != _best_glrt(reference_grouped[key]).local_epoch_sample
        for key in common_probes
    )
    reference_ranked = {(row.sample_start, row.rank): row for row in reference}
    candidate_ranked = {(row.sample_start, row.rank): row for row in candidate}
    common_rank_slots = reference_ranked.keys() & candidate_ranked.keys()
    rank_epoch_changes = sum(
        reference_ranked[key].local_epoch_sample != candidate_ranked[key].local_epoch_sample
        for key in common_rank_slots
    )
    return {
        "reference_row_count": len(reference),
        "candidate_row_count": len(candidate),
        "matched_basin_count": len(matched),
        "unmatched_reference_basin_count": len(reference) - len(matched),
        "unmatched_candidate_basin_count": len(candidate) - len(matched),
        "rank_epoch_change_count": rank_epoch_changes,
        "common_probe_count": len(common_probes),
        "winner_epoch_change_count": winner_epoch_changes,
        "maximum_absolute_acquired_cfo_delta_hz": maximum("acquired_cfo_hz"),
        "maximum_absolute_tracking_cfo_delta_hz": maximum("tracking_cfo_hz"),
        "maximum_absolute_margin_delta": maximum("margin"),
        "median_absolute_winner_cfo_delta_hz": (
            float(np.median(np.abs(winner_differences))) if winner_differences else None
        ),
        "maximum_absolute_winner_cfo_delta_hz": (
            float(np.max(np.abs(winner_differences))) if winner_differences else None
        ),
    }


def _nominal_fine_bins(profile: SearchProfile) -> int:
    return math.floor(2 * profile.fine_radius_hz / profile.fine_step_hz + 1e-12) + 1


def _transform_size(profile: SearchProfile) -> int | None:
    size = round(SAMPLE_RATE_HZ / profile.fine_step_hz)
    exact = math.isclose(SAMPLE_RATE_HZ / profile.fine_step_hz, size, abs_tol=1e-12)
    return size if exact else None


def _format_delta(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}g}"


def _markdown(summary: dict[str, Any]) -> str:
    profiles = {profile.key: profile for profile in PROFILES}
    timings = summary["timings"]
    results = summary["results"]
    deltas = summary["scientific_deltas"]

    def speedup(direct: str, exact: str) -> float:
        return timings[direct]["median_wall_s"] / timings[exact]["median_wall_s"]

    lines = [
        "# T1 GLRT hardware-aligned search parameter study",
        "",
        "Date: 2026-08-22",
        "",
        "Status: qualification report; exact kernels approved for deployment, "
        "search parameters unchanged",
        "",
        "## Decision",
        "",
        "Deploy the mathematically equivalent FFT GLRT64 and fine-CFO transform dispatch. "
        "Keep the current Standard and Research search parameters for now. The radix-2 "
        "profiles are useful research variants, but they change the sampled CFO lattice "
        "and therefore cannot be treated as a transparent implementation replacement.",
        "",
        "This leaves one public GLRT64 method in each lane. Direct and FFT calculations "
        "are implementation backends of that method, not additional scientific GLRT flavors.",
        "",
        "## Bounded evidence",
        "",
        f"The benchmark reread 50 immutable 20 ms probes from `{SESSION_ID}` `{PATH_LABEL}` "
        f"using {summary['workers']} worker threads. Each timing is the median of "
        f"{summary['repeats']} warmed repetitions. The source recording was read-only; no RF "
        "was collected. The three fixed windows are the transition, old-gap, and steady-P3 "
        "windows from the preceding T1 study.",
        "",
        "The fixed piecewise-linear frequency reference is applied only after each independent "
        "probe search. A hit means a margin-qualified candidate lies within 500 Hz of that "
        "diagnostic reference; it is not a calibrated false-alarm probability or identity claim.",
        "",
        "## Equivalent kernel replacement",
        "",
        "| Lane | Direct oracle wall | Exact dispatch wall | End-to-end speed-up | "
        "Max winner CFO delta | Max margin delta | Winner epoch changes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for lane in ("standard", "research"):
        direct = f"{lane}_direct"
        exact = f"{lane}_current"
        delta = deltas[direct]
        lines.append(
            f"| {lane.title()} | {timings[direct]['median_wall_s']:.3f} s | "
            f"{timings[exact]['median_wall_s']:.3f} s | {speedup(direct, exact):.2f}× | "
            f"{_format_delta(delta['maximum_absolute_winner_cfo_delta_hz'])} Hz | "
            f"{_format_delta(delta['maximum_absolute_margin_delta'])} | "
            f"{delta['winner_epoch_change_count']}/{delta['common_probe_count']} |"
        )
    lines.extend(
        [
            "",
            "The direct oracle remains in code for unsupported geometry and regression checks. "
            "The dispatcher uses an FFT only when the CFO/symbol grid is exactly representable "
            "and the fixed cost model predicts a benefit.",
            "",
            "## Parameter geometry",
            "",
            "Only the fine-CFO step and its nearly equal radius change in the aligned variants. "
            "Coarse search, conditioned refinement, basin retention/separation, GLRT length, "
            "sample rate, and probe schedule remain lane-current.",
            "",
            "| Profile | Fine radius | Fine step | Nominal bins | Fine DFT N | Radix-2 | GLRT N |",
            "|---|---:|---:|---:|---:|:---:|---:|",
        ]
    )
    for key in (
        "standard_current",
        "standard_aligned",
        "standard_finer",
        "research_current",
        "research_aligned",
        "research_finer",
    ):
        profile = profiles[key]
        transform = _transform_size(profile)
        power_two = transform is not None and transform > 0 and transform & (transform - 1) == 0
        lines.append(
            f"| {profile.label} | {profile.fine_radius_hz:,.3f} Hz | "
            f"{profile.fine_step_hz:,.6f} Hz | {_nominal_fine_bins(profile)} | "
            f"{transform:,} | {'yes' if power_two else 'no'} | {profile.glrt_size:,} |"
        )
    lines.extend(
        [
            "",
            "## Runtime and T1 result changes",
            "",
            "| Profile | Wall | CPU | Wall vs lane current | Winner hits | Inventory hits | "
            "Strong probes |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for key in (
        "standard_current",
        "standard_aligned",
        "standard_finer",
        "research_current",
        "research_aligned",
        "research_finer",
    ):
        profile = profiles[key]
        baseline = timings[f"{profile.lane}_current"]["median_wall_s"]
        runtime = timings[key]
        result = results[key]
        lines.append(
            f"| {profile.label} | {runtime['median_wall_s']:.3f} s | "
            f"{runtime['median_process_cpu_s']:.3f} s | "
            f"{100 * (runtime['median_wall_s'] / baseline - 1):+.1f}% | "
            f"{result['winner_hit_count']}/{result['probe_count']} | "
            f"{result['inventory_hit_count']}/{result['probe_count']} | "
            f"{result['strong_probe_count']}/{result['probe_count']} |"
        )
    lines.extend(
        [
            "",
            "## Scientific deltas from current lane parameters",
            "",
            "Candidate rows below are matched by probe, refined epoch, and nearest acquired CFO, "
            "rather than by rank. This keeps ordinary rank reordering from appearing as a large "
            "CFO change.",
            "",
            "| Variant | Matched basins | Rank-slot epoch changes | Winner epoch changes | "
            "Median winner CFO delta | Max winner CFO delta | Max basin CFO delta |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for key in ("standard_aligned", "standard_finer", "research_aligned", "research_finer"):
        delta = deltas[key]
        lines.append(
            f"| {profiles[key].label} | "
            f"{delta['matched_basin_count']}/{delta['reference_row_count']} | "
            f"{delta['rank_epoch_change_count']} | "
            f"{delta['winner_epoch_change_count']}/{delta['common_probe_count']} | "
            f"{_format_delta(delta['median_absolute_winner_cfo_delta_hz'])} Hz | "
            f"{_format_delta(delta['maximum_absolute_winner_cfo_delta_hz'])} Hz | "
            f"{_format_delta(delta['maximum_absolute_acquired_cfo_delta_hz'])} Hz |"
        )
    lines.extend(
        [
            "",
            "## Hardware interpretation",
            "",
            "- GLRT-512 and GLRT-4096 are already radix-2. The implementation now evaluates "
            "their identical uniform DFT grids with FFTs.",
            "",
            "- The current 500 Hz and 100 Hz fine grids map exactly to N=5,000 and N=25,000 "
            "transforms. They are not powers of two, but PocketFFT still accelerates them; "
            "power-of-two geometry is an optional additional tuning dimension, not a prerequisite.",
            "",
            "- N=4,096 is the smallest useful Standard radix-2 fine transform because the "
            "selected pilot samples span more than 2,048 sample positions. N=16,384 is the "
            "nearest practical Research choice to the current 100 Hz resolution.",
            "",
            "- Conditioned refinement remains direct. Its small bin count does not repay the "
            "larger whole-frame transform. The 2.5 MS/s sample rate remains ideal because one "
            "4.4 us OFDM symbol is exactly 11 samples.",
            "",
            "## Recommendation",
            "",
            "1. Release the exact dispatch under `standard-v2-production-2` and the updated "
            "science implementation digest.",
            "2. Do not silently replace current Standard or Research parameters. Preserve the "
            "radix-2 and finer-radix-2 settings as named Research configurations until they pass "
            "full-corpus, threshold, and trajectory-level qualification.",
            "3. Keep one public GLRT64 result contract. The direct oracle, exact FFT backend, and "
            "future hardware kernels should remain implementation choices selected by exact "
            "geometry and measured cost.",
            "",
            "Machine-readable summary: "
            "[hardware-aligned-study.json](figures/2026_08_22_t1_glrt_hardware_aligned_parameter_study/hardware-aligned-study.json).",
            "",
            "Candidate inventory: `hardware-aligned-candidates.jsonl.gz`.",
            "",
        ]
    )
    return "\n".join(lines)


def _summaries(
    rows_by_profile: dict[str, tuple[CandidateRow, ...]],
    lines: tuple[dict[str, float], ...],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    results = {}
    windows = []
    for profile in PROFILES:
        results[profile.key] = summarize_population(
            rows_by_profile[profile.key], lines, start_s=0.0, end_s=27.25
        )
        for label, start_s, end_s in WINDOWS:
            windows.append(
                {
                    "profile_key": profile.key,
                    "window": label,
                    "interval_s": [start_s, end_s],
                    **summarize_population(
                        rows_by_profile[profile.key],
                        lines,
                        start_s=start_s,
                        end_s=end_s,
                    ),
                }
            )
    return results, windows


def main() -> None:
    args = _arguments()
    if not 1 <= args.workers <= 16:
        raise ValueError("workers must lie in 1..16")
    if not 1 <= args.repeats <= 10:
        raise ValueError("repeats must lie in 1..10")
    args.output_root.mkdir(parents=True, exist_ok=True)
    candidate_path = args.output_root / "hardware-aligned-candidates.jsonl.gz"
    summary_path = args.output_root / "hardware-aligned-study.json"
    line_reference = _load_lines(args.line_summary)
    if args.reuse:
        rows_by_profile = _load_candidate_file(candidate_path)
        previous = json.loads(summary_path.read_text(encoding="utf-8"))
        timings = previous["timings"]
    else:
        rows_by_profile, timings = _run_profiles(args.bulk_root, args.workers, args.repeats)
        _candidate_file(candidate_path, rows_by_profile)

    results, window_results = _summaries(rows_by_profile, line_reference)
    scientific_deltas = {
        "standard_direct": _scientific_delta(
            rows_by_profile["standard_current"], rows_by_profile["standard_direct"]
        ),
        "standard_aligned": _scientific_delta(
            rows_by_profile["standard_current"], rows_by_profile["standard_aligned"]
        ),
        "standard_finer": _scientific_delta(
            rows_by_profile["standard_current"], rows_by_profile["standard_finer"]
        ),
        "research_direct": _scientific_delta(
            rows_by_profile["research_current"], rows_by_profile["research_direct"]
        ),
        "research_aligned": _scientific_delta(
            rows_by_profile["research_current"], rows_by_profile["research_aligned"]
        ),
        "research_finer": _scientific_delta(
            rows_by_profile["research_current"], rows_by_profile["research_finer"]
        ),
    }
    summary = {
        "schema": "org.leo.research.t1-glrt-hardware-aligned-parameter-study/v1",
        "session_id": SESSION_ID,
        "path": PATH_LABEL,
        "search_is_independent_per_probe": True,
        "reference_used_during_search": False,
        "source_recording_mutated": False,
        "probe_duration_ms": 20.0,
        "probe_spacing_ms": 25.0,
        "workers": args.workers,
        "repeats": args.repeats,
        "profiles": [asdict(profile) for profile in PROFILES],
        "timings": timings,
        "results": results,
        "window_results": window_results,
        "scientific_deltas": scientific_deltas,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.write_text(_markdown(summary), encoding="utf-8")
    print(args.report)


if __name__ == "__main__":
    main()
