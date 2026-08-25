#!/usr/bin/env python3
"""Bounded V3/V4 performance receipt for the frozen 2026-08-25 dwell.

The tool runs current V3 and candidate-only V4 on identical verified 75 ms IQ
rows.  Deterministic scientific evidence is written separately from runtime,
RSS, and host metadata so performance noise cannot change the scientific
receipt.  A small, deterministic subset also compares the production native
folded-anchor grid with its NumPy fallback.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import math
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

CANARY_MODULE_NAME = "leo_v4_frozen_canary_for_benchmark"
SCIENTIFIC_SCHEMA = "org.leo.research.pnt-kalman-v3-v4-performance-scientific/v1"
PERFORMANCE_SCHEMA = "org.leo.research.pnt-kalman-v3-v4-performance-runtime/v1"
ISOLATED_WORKER_SCHEMA = "org.leo.research.pnt-kalman-v3-v4-isolated-worker/v1"
SCIENTIFIC_FILENAME = "scientific-receipt.json"
PERFORMANCE_FILENAME = "performance-receipt.json"
ISOLATED_WORKER_FILENAMES = {
    "v3": "isolated-v3-worker-receipt.json",
    "v4": "isolated-v4-worker-receipt.json",
}
SEEDED_PATH_P95_RATIO_LIMIT = 1.0
FULL_WALL_RATIO_LIMIT = 1.25
PEAK_RSS_RATIO_LIMIT = 1.25
DEFAULT_PARITY_ROW_COUNT = 3
DEFAULT_PARITY_SAMPLE_COUNT = 12_000
MAXIMUM_PARITY_ROW_COUNT = 5
MAXIMUM_PARITY_SAMPLE_COUNT = 50_000
PARITY_CFO_OFFSETS_HZ = (-250.0, 0.0, 250.0)
PARITY_RTOL = 1e-12
PARITY_ATOL = 1e-12


def _load_canary_module() -> Any:
    existing = sys.modules.get(CANARY_MODULE_NAME)
    if existing is not None:
        return existing
    path = Path(__file__).with_name("replay_150802_pnt_kalman_v4_canary.py")
    spec = importlib.util.spec_from_file_location(CANARY_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen V4 canary support: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CANARY = _load_canary_module()


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=CANARY.DEFAULT_INPUT)
    parser.add_argument("--capture-root", type=Path, default=CANARY.DEFAULT_CAPTURE_ROOT)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--maximum-rows",
        type=int,
        help="bounded smoke/subset; omitted schedules all 537 frozen rows",
    )
    parser.add_argument("--parity-row-count", type=int, default=DEFAULT_PARITY_ROW_COUNT)
    parser.add_argument("--parity-sample-count", type=int, default=DEFAULT_PARITY_SAMPLE_COUNT)
    parser.add_argument(
        "--isolated-worker",
        choices=("v3", "v4"),
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


@dataclass(frozen=True, slots=True)
class BenchmarkBindings:
    v3_api_name: str
    v3_source_sha256: str
    v3_config_digest: str
    v3_config: dict[str, Any]
    v4_api_name: str
    v4_source_sha256: str
    v4_config_digest: str
    v4_config: dict[str, Any]
    source_inventory: dict[str, str]
    runtime_inventory: dict[str, Any]
    analyze_v3: Callable[[np.ndarray, float, Any], Any]
    analyze_v4: Callable[[np.ndarray, float, Any], Mapping[str, Any]]
    acquisition_module: Any


@dataclass(frozen=True, slots=True)
class IsolatedWorkerBinding:
    analyzer: str
    api_name: str
    source_sha256: str
    config_digest: str
    config: dict[str, Any]
    source_inventory: dict[str, str]
    runtime_inventory: dict[str, Any]
    analyze: Callable[[np.ndarray, float, Any], Any]
    summarize: Callable[[Any], Mapping[str, Any]]


def load_bindings() -> BenchmarkBindings:
    import leo.analysis.starlink.acquisition as acquisition_module
    from leo.analysis.qam.pilot_pnt_kalman import (
        PilotPntKalmanConfigV3,
        analyze_contiguous_pilot_pnt_kalman_v3,
    )
    from leo.analysis.qam.pilot_pnt_kalman_v4 import (
        PilotPntKalmanConfigV4,
        analyze_contiguous_pilot_pnt_kalman_v4,
    )
    from leo.analysis.starlink.seeded_acquisition import KnownPilotModeSeed

    v3_config = PilotPntKalmanConfigV3()
    v3_config_document = CANARY._plain(v3_config)
    v4 = CANARY.load_v4_binding()
    v4_config = PilotPntKalmanConfigV4()
    if CANARY._plain(v4_config) != v4.config:
        raise RuntimeError("benchmark and canary V4 default configurations differ")
    v3_path = Path(
        str(__import__(analyze_contiguous_pilot_pnt_kalman_v3.__module__, fromlist=["x"]).__file__)
    )

    def analyze_v3(samples: np.ndarray, sample_rate_hz: float, row: Any) -> Any:
        return analyze_contiguous_pilot_pnt_kalman_v3(
            samples,
            sample_rate_hz,
            epoch_sample=int(row.source["epoch_sample"]),
            initial_absolute_cfo_hz=float(row.source["seed_cfo_hz"]),
            edge=str(row.source["edge"]),
            maximum_residual_cfo_hz=2_000.0,
            expected_symbol_roll=0,
            config=v3_config,
        )

    def analyze_v4(
        samples: np.ndarray,
        sample_rate_hz: float,
        row: Any,
    ) -> Mapping[str, Any]:
        rate = row.source.get("standard_v1_local_rate_hz_s")
        seed = KnownPilotModeSeed(
            nominal_epoch_sample=int(row.source["epoch_sample"]),
            nominal_absolute_cfo_hz=float(row.source["seed_cfo_hz"]),
            nominal_doppler_rate_hz_s=0.0 if rate is None else float(rate),
            branch_id=str(row.source["source_branch_id"]),
            provenance_sha256=row.row_input_digest.removeprefix("sha256:"),
        )
        result = analyze_contiguous_pilot_pnt_kalman_v4(
            samples,
            sample_rate_hz,
            seed=seed,
            additional_seeds=(),
            edge=str(row.source["edge"]),
            maximum_residual_cfo_hz=2_000.0,
            expected_symbol_roll=0,
            config=v4_config,
        )
        return _v4_result_summary(result, v4_config)

    return BenchmarkBindings(
        v3_api_name="analyze_contiguous_pilot_pnt_kalman_v3",
        v3_source_sha256=CANARY._file_digest(v3_path),
        v3_config_digest=CANARY._value_digest(v3_config_document),
        v3_config=v3_config_document,
        v4_api_name=v4.api_name,
        v4_source_sha256=v4.source_sha256,
        v4_config_digest=v4.config_digest,
        v4_config=v4.config,
        source_inventory=v4.source_inventory,
        runtime_inventory=v4.runtime_inventory,
        analyze_v3=analyze_v3,
        analyze_v4=analyze_v4,
        acquisition_module=acquisition_module,
    )


def load_isolated_worker_binding(analyzer: str) -> IsolatedWorkerBinding:
    """Load only the analyzer family required by one fresh worker process."""

    if analyzer == "v3":
        import leo.analysis.starlink.acquisition as acquisition_module
        from leo.analysis.qam.pilot_pnt_kalman import (
            PilotPntKalmanConfigV3,
            analyze_contiguous_pilot_pnt_kalman_v3,
        )
        from leo.analysis.starlink.templates import qin_edge_pilot_frame

        v3_config = PilotPntKalmanConfigV3()
        config_document = CANARY._plain(v3_config)
        source_path = Path(
            str(
                __import__(
                    analyze_contiguous_pilot_pnt_kalman_v3.__module__,
                    fromlist=["x"],
                ).__file__
            )
        )

        def analyze_v3(samples: np.ndarray, sample_rate_hz: float, row: Any) -> Any:
            return analyze_contiguous_pilot_pnt_kalman_v3(
                samples,
                sample_rate_hz,
                epoch_sample=int(row.source["epoch_sample"]),
                initial_absolute_cfo_hz=float(row.source["seed_cfo_hz"]),
                edge=str(row.source["edge"]),
                maximum_residual_cfo_hz=2_000.0,
                expected_symbol_roll=0,
                config=v3_config,
            )

        inventory = CANARY._source_inventory(
            (
                analyze_contiguous_pilot_pnt_kalman_v3,
                acquisition_module._folded_anchor_score_grid,
                qin_edge_pilot_frame,
            )
        )
        native_module = acquisition_module._native_acquisition
        if native_module is not None:
            native_path = Path(str(native_module.__file__)).resolve()
            try:
                native_name = str(native_path.relative_to(CANARY.REPOSITORY_ROOT))
            except ValueError:
                native_name = native_path.name
            inventory[native_name] = CANARY._file_digest(native_path)
            inventory = dict(sorted(inventory.items()))
        return IsolatedWorkerBinding(
            analyzer="v3",
            api_name="analyze_contiguous_pilot_pnt_kalman_v3",
            source_sha256=CANARY._file_digest(source_path),
            config_digest=CANARY._value_digest(config_document),
            config=config_document,
            source_inventory=inventory,
            runtime_inventory={
                "folded_anchor_score_grid_backend": (
                    acquisition_module._folded_anchor_score_grid_backend()
                ),
                "native_acquisition_loaded": native_module is not None,
            },
            analyze=analyze_v3,
            summarize=_v3_summary,
        )
    if analyzer == "v4":
        from leo.analysis.qam.pilot_pnt_kalman_v4 import (
            PilotPntKalmanConfigV4,
            analyze_contiguous_pilot_pnt_kalman_v4,
        )
        from leo.analysis.starlink.seeded_acquisition import KnownPilotModeSeed

        canary_binding = CANARY.load_v4_binding()
        v4_config = PilotPntKalmanConfigV4()
        config_document = CANARY._plain(v4_config)
        if config_document != canary_binding.config:
            raise RuntimeError("isolated worker and canary V4 default configurations differ")

        def analyze_v4(samples: np.ndarray, sample_rate_hz: float, row: Any) -> Any:
            rate = row.source.get("standard_v1_local_rate_hz_s")
            seed = KnownPilotModeSeed(
                nominal_epoch_sample=int(row.source["epoch_sample"]),
                nominal_absolute_cfo_hz=float(row.source["seed_cfo_hz"]),
                nominal_doppler_rate_hz_s=0.0 if rate is None else float(rate),
                branch_id=str(row.source["source_branch_id"]),
                provenance_sha256=row.row_input_digest.removeprefix("sha256:"),
            )
            return analyze_contiguous_pilot_pnt_kalman_v4(
                samples,
                sample_rate_hz,
                seed=seed,
                additional_seeds=(),
                edge=str(row.source["edge"]),
                maximum_residual_cfo_hz=2_000.0,
                expected_symbol_roll=0,
                config=v4_config,
            )

        return IsolatedWorkerBinding(
            analyzer="v4",
            api_name=canary_binding.api_name,
            source_sha256=canary_binding.source_sha256,
            config_digest=canary_binding.config_digest,
            config=canary_binding.config,
            source_inventory=canary_binding.source_inventory,
            runtime_inventory=canary_binding.runtime_inventory,
            analyze=analyze_v4,
            summarize=lambda result: _v4_result_summary(result, v4_config),
        )
    raise ValueError("isolated worker analyzer must be v3 or v4")


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _enum_value(value: Any) -> Any:
    return CANARY._plain(value)


def _v3_summary(result: Any) -> dict[str, Any]:
    plain = CANARY._plain(result)
    frames = _get(result, "frames", ())
    alignment = _get(result, "initial_alignment")
    return {
        "status": _enum_value(_get(result, "status")),
        "frame_count": len(frames),
        "supported_frame_count": int(_get(result, "supported_frame_count", 0)),
        "phase_update_count": int(_get(result, "phase_update_count", 0)),
        "frequency_update_count": int(_get(result, "frequency_update_count", 0)),
        "timing_update_count": int(_get(result, "timing_update_count", 0)),
        "phase_lock_qualified": bool(_get(result, "phase_lock_qualified", False)),
        "phase_lock_reason": str(_get(result, "phase_lock_reason", "")),
        "reason": str(_get(result, "reason", "")),
        "initial_alignment": None if alignment is None else CANARY._plain(alignment),
        "evidence_digest": CANARY._value_digest(plain),
    }


def _v4_result_summary(result: Any, config: Any) -> dict[str, Any]:
    from leo.analysis.qam.pilot_pnt_kalman import PilotPntKalmanConfigV3

    acquisition = result.acquisition
    modes = tuple(acquisition.retained_modes)
    accepted = tuple(acquisition.accepted_modes)

    def mode_id(mode: Any) -> str:
        return CANARY._value_digest(
            {
                "rank": int(mode.rank),
                "origin": _enum_value(mode.proposal_origin),
                "epoch_sample": int(mode.epoch_sample),
                "absolute_cfo_hz": float(mode.absolute_cfo_hz),
                "source_seed_index": int(mode.source_seed_index),
                "source_branch_id": str(mode.source_branch_id),
                "proposal_epoch_sample": int(mode.proposal_epoch_sample),
                "proposal_absolute_cfo_hz": float(mode.proposal_absolute_cfo_hz),
                "trajectory_path_sha256": str(mode.trajectory_path_sha256),
            }
        )

    accepted_ids = {mode_id(mode) for mode in accepted}
    tracks = {mode_id(row.mode): row for row in result.mode_results}
    local_modes = tuple(
        mode for mode in modes if _enum_value(mode.proposal_origin) != "global_fallback"
    )
    global_modes = tuple(
        mode for mode in modes if _enum_value(mode.proposal_origin) == "global_fallback"
    )
    if acquisition.evaluated_grid_point_count != (
        len(local_modes)
        + acquisition.separation_suppressed_count
        + acquisition.candidate_limit_truncated_count
    ):
        raise RuntimeError("V4 local proposal accounting is incomplete")
    if acquisition.global_peak_count != (
        len(global_modes)
        + acquisition.global_separation_suppressed_count
        + acquisition.global_candidate_limit_truncated_count
    ):
        raise RuntimeError("V4 global peak accounting is incomplete")
    if acquisition.evaluated_seed_count != 1 + len(acquisition.additional_seeds):
        raise RuntimeError("V4 seed accounting is incomplete")
    if acquisition.additional_seeds:
        raise RuntimeError("frozen V4 benchmark requires exactly one provenance-bound seed")
    block_starts = tuple(int(value) for value in acquisition.block_starts)
    block_count = len(block_starts)
    global_block_score_count = int(acquisition.global_evaluated_block_score_count)
    if block_count == 0:
        if global_block_score_count:
            raise RuntimeError("V4 reported global refinement work without blocks")
        global_refinement_coordinate_pair_count = 0
    else:
        if global_block_score_count % block_count:
            raise RuntimeError("V4 global refinement work is not an exact-pair block inventory")
        global_refinement_coordinate_pair_count = global_block_score_count // block_count
    proposal_symbols = tuple(
        int(value) for value in config.acquisition_config.global_proposal_symbols
    )
    proposal_block_index = int(acquisition.global_proposal_block_index)
    proposal_start = acquisition.global_proposal_block_start_sample
    proposal_stop = acquisition.global_proposal_block_stop_sample
    proposal_sample_count = int(acquisition.global_proposal_sample_count)
    proposal_symbol_count = int(acquisition.global_proposal_symbol_count)
    proposal_frame_offset_count = int(acquisition.global_proposal_frame_offset_count)
    if proposal_block_index != int(config.acquisition_config.global_proposal_block_index):
        raise RuntimeError("V4 global proposal block does not match its bound configuration")
    if acquisition.global_fallback_attempted:
        if (
            not block_starts
            or proposal_block_index >= block_count
            or proposal_start != block_starts[proposal_block_index]
            or proposal_stop is None
            or proposal_stop <= proposal_start
            or proposal_stop > int(acquisition.sample_count)
            or proposal_sample_count != proposal_stop - proposal_start
            or proposal_symbol_count != len(proposal_symbols)
        ):
            raise RuntimeError("V4 global proposal block or symbol accounting is incomplete")
        expected_frame_offset_count = 0
        while round(expected_frame_offset_count * acquisition.frame_period_samples) < (
            proposal_sample_count
        ):
            expected_frame_offset_count += 1
        if proposal_frame_offset_count != expected_frame_offset_count:
            raise RuntimeError("V4 global proposal frame-offset accounting is incomplete")
    elif any(
        value is not None
        for value in (
            proposal_start,
            proposal_stop,
        )
    ) or any(
        (
            proposal_sample_count,
            proposal_symbol_count,
            proposal_frame_offset_count,
            global_refinement_coordinate_pair_count,
        )
    ):
        raise RuntimeError("V4 reported global proposal work without fallback")
    if global_refinement_coordinate_pair_count < len(global_modes):
        raise RuntimeError("V4 global exact-pair refinement does not cover retained proposals")

    components = []
    for mode in modes:
        identifier = mode_id(mode)
        track = tracks.get(identifier)
        components.append(
            {
                "candidate_id": identifier,
                "rank": int(mode.rank),
                "origin": _enum_value(mode.proposal_origin),
                "decision": _enum_value(mode.decision),
                "epoch_sample": int(mode.epoch_sample),
                "absolute_cfo_hz": float(mode.absolute_cfo_hz),
                "doppler_rate_hz_s": float(mode.doppler_rate_hz_s),
                "canonical_cfo_hz": float(mode.canonical_cfo_hz),
                "cfo_alias_lift": int(mode.cfo_alias_lift),
                "source_seed_index": int(mode.source_seed_index),
                "source_branch_id": str(mode.source_branch_id),
                "source_provenance_sha256": str(mode.source_provenance_sha256),
                "source_nominal_epoch_sample": int(mode.source_nominal_epoch_sample),
                "source_nominal_absolute_cfo_hz": float(mode.source_nominal_absolute_cfo_hz),
                "proposal_epoch_sample": int(mode.proposal_epoch_sample),
                "proposal_absolute_cfo_hz": float(mode.proposal_absolute_cfo_hz),
                "trajectory_block_epoch_samples": [
                    int(value) for value in mode.trajectory_block_epoch_samples
                ],
                "trajectory_block_epoch_residual_samples": [
                    int(value) for value in mode.trajectory_block_epoch_residual_samples
                ],
                "trajectory_block_absolute_cfo_hz": [
                    float(value) for value in mode.trajectory_block_absolute_cfo_hz
                ],
                "trajectory_block_cfo_residual_hz": [
                    float(value) for value in mode.trajectory_block_cfo_residual_hz
                ],
                "trajectory_epoch_span_samples": int(mode.trajectory_epoch_span_samples),
                "trajectory_max_adjacent_epoch_step_samples": int(
                    mode.trajectory_max_adjacent_epoch_step_samples
                ),
                "trajectory_epoch_dispersion_samples": float(
                    mode.trajectory_epoch_dispersion_samples
                ),
                "trajectory_epoch_fit_rms_samples": float(mode.trajectory_epoch_fit_rms_samples),
                "trajectory_timing_rate_samples_s": float(mode.trajectory_timing_rate_samples_s),
                "trajectory_cfo_span_hz": float(mode.trajectory_cfo_span_hz),
                "trajectory_cfo_dispersion_hz": float(mode.trajectory_cfo_dispersion_hz),
                "trajectory_cfo_fit_rms_hz": float(mode.trajectory_cfo_fit_rms_hz),
                "trajectory_cfo_rate_residual_hz_s": float(mode.trajectory_cfo_rate_residual_hz_s),
                "trajectory_path_sha256": str(mode.trajectory_path_sha256),
                "trajectory_admissible": bool(mode.trajectory_admissible),
                "blocks": CANARY._plain(mode.blocks),
                "whole_window_verify_score": (
                    None
                    if mode.whole_window_verify_score is None
                    else float(mode.whole_window_verify_score)
                ),
                "whole_window_control_scores": list(mode.whole_window_control_scores),
                "whole_window_diagnostic_control_scores": list(
                    mode.whole_window_diagnostic_control_scores
                ),
                "whole_window_exact_minus_control_margin": (
                    None
                    if mode.whole_window_exact_minus_control_margin is None
                    else float(mode.whole_window_exact_minus_control_margin)
                ),
                "whole_window_frame_support": int(mode.whole_window_frame_support),
                "whole_window_consistent_with_blocks": bool(
                    mode.whole_window_consistent_with_blocks
                ),
                "accepted": identifier in accepted_ids,
                "tracking_status": (None if track is None else _enum_value(track.numerical_status)),
                "phase_lock_qualified": (
                    None if track is None else bool(track.phase_lock_qualified)
                ),
            }
        )

    return {
        "numerical_status": _enum_value(result.numerical_status),
        "acquisition_status": _enum_value(acquisition.status),
        "proposal_count": int(
            acquisition.evaluated_grid_point_count + acquisition.global_peak_count
        ),
        "serialized_proposal_count": len(modes),
        "local_serialized_proposal_count": len(local_modes),
        "global_serialized_proposal_count": len(global_modes),
        "local_evaluated_grid_point_count": int(acquisition.evaluated_grid_point_count),
        "local_evaluated_block_score_count": int(acquisition.evaluated_block_score_count),
        "local_trajectory_path_evaluated_count": int(acquisition.trajectory_path_evaluated_count),
        "local_trajectory_path_limit_truncated_count": int(
            acquisition.trajectory_path_limit_truncated_count
        ),
        "global_fallback_attempted": bool(acquisition.global_fallback_attempted),
        "global_proposal_block_index": proposal_block_index,
        "global_proposal_block_start_sample": proposal_start,
        "global_proposal_block_stop_sample": proposal_stop,
        "global_proposal_sample_count": proposal_sample_count,
        "global_proposal_symbols": list(proposal_symbols),
        "global_proposal_symbol_count": proposal_symbol_count,
        "global_proposal_frame_offset_count": proposal_frame_offset_count,
        "global_evaluated_grid_point_count": int(acquisition.global_evaluated_grid_point_count),
        "global_peak_count": int(acquisition.global_peak_count),
        "global_refinement_coordinate_pair_count": (global_refinement_coordinate_pair_count),
        "global_evaluated_block_score_count": global_block_score_count,
        "global_trajectory_path_evaluated_count": int(
            acquisition.global_trajectory_path_evaluated_count
        ),
        "global_trajectory_path_limit_truncated_count": int(
            acquisition.global_trajectory_path_limit_truncated_count
        ),
        "additional_seed_count": len(acquisition.additional_seeds),
        "evaluated_seed_count": int(acquisition.evaluated_seed_count),
        "whole_window_rescore_candidate_count": int(
            acquisition.whole_window_rescore_candidate_count
        ),
        "whole_window_rescore_template_score_count": int(
            acquisition.whole_window_rescore_template_score_count
        ),
        "retained_mode_count": len(modes),
        "accepted_mode_count": len(accepted),
        "accepted_tracked_mode_count": int(result.complete_mode_count),
        "accepted_phase_lock_count": int(result.phase_lock_qualified_mode_count),
        "component_inventory": components,
        "acquisition_config_digest": str(acquisition.config_digest),
        "exact_template_identity": CANARY._plain(acquisition.exact_template_identity),
        "conditional_control_template_identities": CANARY._plain(
            acquisition.conditional_control_template_identities
        ),
        "diagnostic_control_template_identities": CANARY._plain(
            acquisition.diagnostic_control_template_identities
        ),
        "presence_disposition": _enum_value(acquisition.presence_disposition),
        "code_specificity_disposition": _enum_value(acquisition.code_specificity_disposition),
        "cfo_alias_resolution_disposition": _enum_value(
            acquisition.cfo_alias_resolution_disposition
        ),
        "uniqueness_disposition": _enum_value(acquisition.uniqueness_disposition),
        "scientific_qualification_claimed": False,
        "phase_thresholds_unchanged": (
            CANARY._plain(config.tracker_config) == CANARY._plain(PilotPntKalmanConfigV3())
        ),
        "evidence_digest": CANARY._value_digest(CANARY._plain(result)),
    }


def representative_rows(rows: Sequence[Any], maximum_count: int) -> tuple[Any, ...]:
    if maximum_count < 1:
        raise ValueError("parity row count must be positive")
    if not rows:
        return ()
    count = min(maximum_count, len(rows))
    if count == 1:
        return (rows[0],)
    indexes = tuple(round(index * (len(rows) - 1) / (count - 1)) for index in range(count))
    return tuple(rows[index] for index in indexes)


def _sample_digest(values: np.ndarray) -> str:
    payload = np.ascontiguousarray(values, dtype="<c16").tobytes()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def native_numpy_parity(
    samples: np.ndarray,
    sample_rate_hz: float,
    row: Any,
    acquisition_module: Any,
    sample_count: int,
    clock_ns: Callable[[], int],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from leo.analysis.starlink.acquisition import DEFAULT_ACQUIRE_SYMBOLS
    from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame

    native_module = acquisition_module._native_acquisition
    backend = acquisition_module._folded_anchor_score_grid_backend()
    selected = np.asarray(samples[:sample_count], dtype=np.complex128)
    epoch_count = min(math.ceil(sample_rate_hz / FRAME_RATE_HZ), selected.size)
    center_cfo_hz = float(row.source["seed_cfo_hz"])
    cfo_grid = tuple(center_cfo_hz + offset for offset in PARITY_CFO_OFFSETS_HZ)
    template = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, str(row.source["edge"])),
        dtype=np.complex128,
    )
    if native_module is None:
        return (
            {
                "row_key": row.row_key,
                "status": "not_estimable_native_unavailable",
                "sample_count": selected.size,
                "sample_sha256": _sample_digest(selected),
            },
            {"row_key": row.row_key, "native_elapsed_ns": None, "numpy_elapsed_ns": None},
        )

    native_started = clock_ns()
    native = acquisition_module._folded_anchor_score_grid(
        selected,
        template,
        sample_rate_hz,
        cfo_grid,
        DEFAULT_ACQUIRE_SYMBOLS,
        epoch_count,
    )
    native_elapsed_ns = clock_ns() - native_started
    try:
        acquisition_module._native_acquisition = None
        numpy_started = clock_ns()
        numpy_fallback = acquisition_module._folded_anchor_score_grid(
            selected,
            template,
            sample_rate_hz,
            cfo_grid,
            DEFAULT_ACQUIRE_SYMBOLS,
            epoch_count,
        )
        numpy_elapsed_ns = clock_ns() - numpy_started
    finally:
        acquisition_module._native_acquisition = native_module

    native_values = np.asarray(native, dtype=np.float64)
    numpy_values = np.asarray(numpy_fallback, dtype=np.float64)
    shape_match = native_values.shape == numpy_values.shape
    delta = (
        np.abs(native_values - numpy_values) if shape_match else np.asarray([math.inf], dtype=float)
    )
    maximum_absolute_delta = float(np.max(delta, initial=0.0))
    allclose = bool(
        shape_match
        and np.allclose(
            native_values,
            numpy_values,
            rtol=PARITY_RTOL,
            atol=PARITY_ATOL,
        )
    )
    argmax_mismatches = (
        sum(
            int(np.argmax(left)) != int(np.argmax(right))
            for left, right in zip(native_values, numpy_values, strict=True)
        )
        if shape_match
        else max(len(native_values), len(numpy_values))
    )
    return (
        {
            "row_key": row.row_key,
            "status": "pass" if allclose and argmax_mismatches == 0 else "fail",
            "sample_count": selected.size,
            "sample_sha256": _sample_digest(selected),
            "edge": str(row.source["edge"]),
            "cfo_grid_hz": list(cfo_grid),
            "epoch_count": epoch_count,
            "score_shape": list(native_values.shape),
            "native_backend": backend,
            "rtol": PARITY_RTOL,
            "atol": PARITY_ATOL,
            "maximum_absolute_score_delta": maximum_absolute_delta,
            "argmax_mismatch_count": argmax_mismatches,
            "allclose": allclose,
        },
        {
            "row_key": row.row_key,
            "native_elapsed_ns": native_elapsed_ns,
            "numpy_elapsed_ns": numpy_elapsed_ns,
        },
    )


def _distribution(values: Sequence[int]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "minimum_ns": None,
            "median_ns": None,
            "p95_ns": None,
            "maximum_ns": None,
        }
    measured = np.asarray(values, dtype=np.int64)
    return {
        "count": len(values),
        "minimum_ns": int(np.min(measured)),
        "median_ns": float(np.median(measured)),
        "p95_ns": float(np.percentile(measured, 95)),
        "maximum_ns": int(np.max(measured)),
        "total_ns": int(np.sum(measured)),
    }


def _peak_rss_bytes() -> int:
    raw = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return raw if sys.platform == "darwin" else raw * 1024


def _hardware() -> dict[str, Any]:
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "logical_cpu_count": os.cpu_count(),
        "cpu_affinity": affinity,
        "thread_environment": {
            name: os.environ.get(name)
            for name in (
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS",
            )
        },
    }


def _receipt(value: Any) -> dict[str, Any]:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return CANARY._plain(dataclasses.asdict(value))
    return CANARY._plain(value)


def _chunk_inventory(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for row in rows:
        for receipt in row["verified_iq_chunks"]:
            relative = str(receipt["relative_path"])
            previous = inventory.setdefault(relative, dict(receipt))
            if previous != receipt:
                raise ValueError(f"conflicting verified chunk receipts: {relative}")
    return dict(sorted(inventory.items()))


def run_isolated_worker(
    *,
    frozen: Any,
    reader: Any,
    binding: IsolatedWorkerBinding,
    maximum_rows: int | None,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
    peak_rss_bytes: Callable[[], int] = _peak_rss_bytes,
) -> dict[str, Any]:
    """Run exactly one analyzer family and return its source-bound runtime receipt."""

    if maximum_rows is not None and maximum_rows < 1:
        raise ValueError("maximum rows must be positive")
    rows = frozen.rows if maximum_rows is None else frozen.rows[:maximum_rows]
    if not rows:
        raise ValueError("isolated worker schedules no rows")

    initial_peak_rss = peak_rss_bytes()
    worker_started = clock_ns()
    receipt_rows = []
    for position, row in enumerate(rows):
        read_started = clock_ns()
        samples, iq_receipts = reader.read_complex(
            str(row.source["stream"]),
            int(row.source["receiver"]),
            int(row.source["source_probe_sample_start"]),
            CANARY.WINDOW_SAMPLE_COUNT,
        )
        read_elapsed_ns = clock_ns() - read_started
        analyzer_started = clock_ns()
        raw_result = binding.analyze(samples, reader.sample_rate_hz, row)
        analyzer_elapsed_ns = clock_ns() - analyzer_started
        summary = dict(binding.summarize(raw_result))
        if binding.analyzer == "v4":
            seeded_path: bool | None = not bool(summary["global_fallback_attempted"])
            outcome_status = str(summary["numerical_status"])
        else:
            seeded_path = None
            outcome_status = str(summary["status"])
        receipt_rows.append(
            {
                "row_index": int(row.index),
                "row_key": row.row_key,
                "row_input_digest": row.row_input_digest,
                "stream": str(row.source["stream"]),
                "receiver": int(row.source["receiver"]),
                "source_probe_sample_start": int(row.source["source_probe_sample_start"]),
                "verified_iq_chunks": [_receipt(receipt) for receipt in iq_receipts],
                "iq_read_elapsed_ns": read_elapsed_ns,
                "analyzer_elapsed_ns": analyzer_elapsed_ns,
                "seeded_path": seeded_path,
                "outcome_status": outcome_status,
                "outcome_evidence_digest": str(summary["evidence_digest"]),
            }
        )
        print(
            f"isolated {binding.analyzer} row {position + 1}/{len(rows)} {row.row_key}",
            flush=True,
        )
    full_replay_wall_elapsed_ns = clock_ns() - worker_started
    final_peak_rss = peak_rss_bytes()
    row_identities = [
        {
            "row_index": int(row.index),
            "row_key": row.row_key,
            "row_input_digest": row.row_input_digest,
        }
        for row in rows
    ]
    receipt = {
        "schema": ISOLATED_WORKER_SCHEMA,
        "analyzer": binding.analyzer,
        "session_id": CANARY.SESSION_ID,
        "run_id": CANARY.RUN_ID,
        "frozen_input_sha256": frozen.digest,
        "recording_manifest_sha256": reader.manifest_digest,
        "harness_source_sha256": CANARY._file_digest(Path(__file__).resolve()),
        "binding": {
            "api": binding.api_name,
            "source_sha256": binding.source_sha256,
            "config_digest": binding.config_digest,
            "config": binding.config,
            "source_inventory": binding.source_inventory,
            "runtime_inventory": binding.runtime_inventory,
        },
        "coverage": {
            "population_row_count": len(frozen.rows),
            "scheduled_row_count": len(rows),
            "full_population": len(rows) == len(frozen.rows),
            "rows": row_identities,
            "row_identity_digest": CANARY._value_digest(row_identities),
        },
        "measurement_scope": {
            "isolated_analyzer_process": True,
            "clock": "time.perf_counter_ns",
            "full_wall_includes": (
                "verified IQ reads, analyzer execution, and row outcome summarization; "
                "excludes process startup and receipt serialization"
            ),
            "timing_is_nondeterministic": True,
        },
        "rows": receipt_rows,
        "verified_consumed_chunks": _chunk_inventory(receipt_rows),
        "distributions": {
            "analyzer": _distribution([int(row["analyzer_elapsed_ns"]) for row in receipt_rows]),
            "iq_read": _distribution([int(row["iq_read_elapsed_ns"]) for row in receipt_rows]),
        },
        "full_replay_wall_elapsed_ns": full_replay_wall_elapsed_ns,
        "peak_rss": {
            "unit": "bytes",
            "at_entry": initial_peak_rss,
            "maximum_observed": max(initial_peak_rss, final_peak_rss),
            "source": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        },
    }
    receipt["worker_receipt_digest"] = CANARY._value_digest(receipt)
    return receipt


def _not_estimable_exit_gates(reason: str) -> dict[str, Any]:
    return {
        "status": "not_estimable",
        "reason": reason,
        "thresholds": {
            "seeded_path_v4_p95_over_v3_maximum": SEEDED_PATH_P95_RATIO_LIMIT,
            "full_wall_v4_over_v3_maximum": FULL_WALL_RATIO_LIMIT,
            "peak_rss_v4_over_v3_maximum": PEAK_RSS_RATIO_LIMIT,
            "native_numpy_parity_required": True,
        },
        "checks": {
            "seeded_path_p95": None,
            "full_wall": None,
            "peak_rss": None,
            "native_numpy_parity": None,
        },
    }


def _validate_isolated_worker_pair(
    scientific: Mapping[str, Any],
    receipts: Mapping[str, Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if set(receipts) != {"v3", "v4"}:
        raise ValueError("isolated worker receipts must contain exactly v3 and v4")
    v3 = receipts["v3"]
    v4 = receipts["v4"]
    expected_rows = [
        {
            "row_index": int(row["row_index"]),
            "row_key": str(row["row_key"]),
            "row_input_digest": str(row["row_input_digest"]),
        }
        for row in scientific["rows"]
    ]
    scientific_rows = list(scientific["rows"])
    expected_population_count = int(scientific["coverage"]["population_row_count"])
    expected_full_population = scientific["coverage"]["full_population"] is True
    for analyzer, receipt in (("v3", v3), ("v4", v4)):
        if receipt.get("schema") != ISOLATED_WORKER_SCHEMA:
            raise ValueError(f"isolated {analyzer} worker schema mismatch")
        if receipt.get("analyzer") != analyzer:
            raise ValueError(f"isolated {analyzer} worker analyzer mismatch")
        for field in ("session_id", "run_id", "harness_source_sha256"):
            if receipt.get(field) != scientific[field]:
                raise ValueError(f"isolated {analyzer} worker {field} mismatch")
        if receipt.get("frozen_input_sha256") != scientific["frozen_input_sha256"]:
            raise ValueError(f"isolated {analyzer} worker frozen input mismatch")
        if receipt.get("recording_manifest_sha256") != scientific["recording_manifest_sha256"]:
            raise ValueError(f"isolated {analyzer} worker recording manifest mismatch")
        coverage = receipt.get("coverage", {})
        if (
            coverage.get("population_row_count") != expected_population_count
            or coverage.get("scheduled_row_count") != len(expected_rows)
            or coverage.get("full_population") is not expected_full_population
            or coverage.get("rows") != expected_rows
            or coverage.get("row_identity_digest") != CANARY._value_digest(expected_rows)
        ):
            raise ValueError(f"isolated {analyzer} worker row population mismatch")
        if receipt.get("measurement_scope", {}).get("isolated_analyzer_process") is not True:
            raise ValueError(f"isolated {analyzer} worker process scope mismatch")
        expected_binding = scientific["bindings"][analyzer]
        binding = receipt.get("binding", {})
        for field in ("api", "source_sha256", "config_digest"):
            if binding.get(field) != expected_binding[field]:
                raise ValueError(f"isolated {analyzer} worker {field} mismatch")
        rows = receipt.get("rows")
        if not isinstance(rows, list) or len(rows) != len(expected_rows):
            raise ValueError(f"isolated {analyzer} worker timing rows are incomplete")
        observed_rows = [
            {
                "row_index": int(row["row_index"]),
                "row_key": str(row["row_key"]),
                "row_input_digest": str(row["row_input_digest"]),
            }
            for row in rows
        ]
        if observed_rows != expected_rows:
            raise ValueError(f"isolated {analyzer} worker timing row identity mismatch")
        for row, scientific_row in zip(rows, scientific_rows, strict=True):
            expected_outcome_digest = str(scientific_row[analyzer]["evidence_digest"])
            if row.get("outcome_evidence_digest") != expected_outcome_digest:
                raise ValueError(f"isolated {analyzer} worker outcome evidence digest mismatch")
        if analyzer == "v4" and not all(isinstance(row.get("seeded_path"), bool) for row in rows):
            raise ValueError("isolated v4 worker seeded-path decisions are incomplete")
        recorded_digest = receipt.get("worker_receipt_digest")
        digest_document = dict(receipt)
        digest_document.pop("worker_receipt_digest", None)
        if recorded_digest != CANARY._value_digest(digest_document):
            raise ValueError(f"isolated {analyzer} worker receipt digest mismatch")
    return v3, v4


def _positive_metric(value: Any, label: str) -> float:
    measured = float(value)
    if not math.isfinite(measured) or measured <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return measured


def evaluate_performance_exit_gates(
    scientific: Mapping[str, Any],
    isolated_worker_receipts: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Evaluate only source-matched, full-population, isolated-process evidence."""

    if isolated_worker_receipts is None:
        if scientific["coverage"]["full_population"] is not True:
            return _not_estimable_exit_gates(
                "complete frozen-population receipts are required; bounded subsets cannot qualify"
            )
        return _not_estimable_exit_gates("isolated V3 and V4 worker receipts are required")
    v3, v4 = _validate_isolated_worker_pair(scientific, isolated_worker_receipts)
    if scientific["coverage"]["full_population"] is not True:
        return _not_estimable_exit_gates(
            "complete frozen-population receipts are required; bounded subsets cannot qualify"
        )
    v3_by_key = {str(row["row_key"]): row for row in v3["rows"]}
    seeded_v4_rows = [row for row in v4["rows"] if row.get("seeded_path") is True]
    if not seeded_v4_rows:
        return _not_estimable_exit_gates("the full-population V4 worker reported no seeded rows")
    seeded_v3_times = [
        int(v3_by_key[str(row["row_key"])]["analyzer_elapsed_ns"]) for row in seeded_v4_rows
    ]
    seeded_v4_times = [int(row["analyzer_elapsed_ns"]) for row in seeded_v4_rows]
    v3_p95_ns = _positive_metric(_distribution(seeded_v3_times)["p95_ns"], "V3 seeded p95")
    v4_p95_ns = _positive_metric(_distribution(seeded_v4_times)["p95_ns"], "V4 seeded p95")
    v3_wall_ns = _positive_metric(v3["full_replay_wall_elapsed_ns"], "V3 full wall")
    v4_wall_ns = _positive_metric(v4["full_replay_wall_elapsed_ns"], "V4 full wall")
    v3_peak_rss = _positive_metric(v3["peak_rss"]["maximum_observed"], "V3 peak RSS")
    v4_peak_rss = _positive_metric(v4["peak_rss"]["maximum_observed"], "V4 peak RSS")
    seeded_p95_ratio = v4_p95_ns / v3_p95_ns
    full_wall_ratio = v4_wall_ns / v3_wall_ns
    peak_rss_ratio = v4_peak_rss / v3_peak_rss
    parity_pass = scientific["native_numpy_parity"]["all_rows_passed"] is True
    checks = {
        "seeded_path_p95": seeded_p95_ratio <= SEEDED_PATH_P95_RATIO_LIMIT,
        "full_wall": full_wall_ratio <= FULL_WALL_RATIO_LIMIT,
        "peak_rss": peak_rss_ratio <= PEAK_RSS_RATIO_LIMIT,
        "native_numpy_parity": parity_pass,
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "thresholds": {
            "seeded_path_v4_p95_over_v3_maximum": SEEDED_PATH_P95_RATIO_LIMIT,
            "full_wall_v4_over_v3_maximum": FULL_WALL_RATIO_LIMIT,
            "peak_rss_v4_over_v3_maximum": PEAK_RSS_RATIO_LIMIT,
            "native_numpy_parity_required": True,
        },
        "observations": {
            "seeded_path_row_count": len(seeded_v4_rows),
            "seeded_path_v3_p95_ns": v3_p95_ns,
            "seeded_path_v4_p95_ns": v4_p95_ns,
            "seeded_path_v4_p95_over_v3": seeded_p95_ratio,
            "v3_full_wall_elapsed_ns": v3_wall_ns,
            "v4_full_wall_elapsed_ns": v4_wall_ns,
            "full_wall_v4_over_v3": full_wall_ratio,
            "v3_peak_rss_bytes": v3_peak_rss,
            "v4_peak_rss_bytes": v4_peak_rss,
            "peak_rss_v4_over_v3": peak_rss_ratio,
            "native_numpy_parity": parity_pass,
        },
        "checks": checks,
        "measurement_source": "fresh isolated V3-only and V4-only worker processes",
    }


def run_isolated_worker_subprocesses(
    *,
    input_path: Path,
    capture_root: Path,
    maximum_rows: int | None,
) -> dict[str, dict[str, Any]]:
    """Execute V3 and V4 in separate fresh interpreters and load their receipts."""

    receipts: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="leo-pnt-v3-v4-workers-") as temporary_name:
        temporary_root = Path(temporary_name)
        for analyzer in ("v3", "v4"):
            output_root = temporary_root / analyzer
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--input",
                str(input_path),
                "--capture-root",
                str(capture_root),
                "--output-root",
                str(output_root),
                "--isolated-worker",
                analyzer,
            ]
            if maximum_rows is not None:
                command.extend(("--maximum-rows", str(maximum_rows)))
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"isolated {analyzer} worker failed with exit {completed.returncode}: "
                    f"{completed.stderr.strip() or completed.stdout.strip()}"
                )
            receipt_path = output_root / ISOLATED_WORKER_FILENAMES[analyzer]
            receipts[analyzer] = CANARY._json_object(receipt_path)
    return receipts


def run_benchmark(
    *,
    frozen: Any,
    reader: Any,
    bindings: BenchmarkBindings,
    maximum_rows: int | None,
    parity_row_count: int,
    parity_sample_count: int,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
    peak_rss_bytes: Callable[[], int] = _peak_rss_bytes,
    parity_function: Callable[..., tuple[dict[str, Any], dict[str, Any]]] = native_numpy_parity,
    isolated_worker_receipts: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if maximum_rows is not None and maximum_rows < 1:
        raise ValueError("maximum rows must be positive")
    if not 1 <= parity_row_count <= MAXIMUM_PARITY_ROW_COUNT:
        raise ValueError(f"parity row count must lie in 1..{MAXIMUM_PARITY_ROW_COUNT}")
    if not 1 <= parity_sample_count <= MAXIMUM_PARITY_SAMPLE_COUNT:
        raise ValueError(f"parity sample count must lie in 1..{MAXIMUM_PARITY_SAMPLE_COUNT}")
    rows = frozen.rows if maximum_rows is None else frozen.rows[:maximum_rows]
    if not rows:
        raise ValueError("benchmark schedules no rows")
    parity_rows = representative_rows(rows, parity_row_count)
    parity_row_keys = {row.row_key for row in parity_rows}

    initial_peak_rss = peak_rss_bytes()
    operation_started = clock_ns()
    replay_started = clock_ns()
    scientific_rows = []
    timing_rows = []
    samples_by_key: dict[str, np.ndarray] = {}
    for position, row in enumerate(rows):
        row_started = clock_ns()
        read_started = clock_ns()
        samples, receipts = reader.read_complex(
            str(row.source["stream"]),
            int(row.source["receiver"]),
            int(row.source["source_probe_sample_start"]),
            CANARY.WINDOW_SAMPLE_COUNT,
        )
        read_elapsed = clock_ns() - read_started
        if position % 2 == 0:
            v3_started = clock_ns()
            v3_result = bindings.analyze_v3(samples, reader.sample_rate_hz, row)
            v3_elapsed = clock_ns() - v3_started
            v4_started = clock_ns()
            v4_raw = bindings.analyze_v4(samples, reader.sample_rate_hz, row)
            v4_elapsed = clock_ns() - v4_started
            execution_order = "v3_then_v4"
        else:
            v4_started = clock_ns()
            v4_raw = bindings.analyze_v4(samples, reader.sample_rate_hz, row)
            v4_elapsed = clock_ns() - v4_started
            v3_started = clock_ns()
            v3_result = bindings.analyze_v3(samples, reader.sample_rate_hz, row)
            v3_elapsed = clock_ns() - v3_started
            execution_order = "v4_then_v3"
        v3_summary = _v3_summary(v3_result)
        v4_summary = dict(v4_raw)
        receipt_rows = [_receipt(receipt) for receipt in receipts]
        scientific_rows.append(
            {
                "row_index": int(row.index),
                "row_key": row.row_key,
                "row_input_digest": row.row_input_digest,
                "stream": str(row.source["stream"]),
                "receiver": int(row.source["receiver"]),
                "edge": str(row.source["edge"]),
                "source_probe_sample_start": int(row.source["source_probe_sample_start"]),
                "verified_iq_chunks": receipt_rows,
                "v3": v3_summary,
                "v4": v4_summary,
                "comparison": {
                    "same_numerical_status": (
                        v3_summary["status"] == v4_summary["numerical_status"]
                    ),
                    "v3_phase_lock_qualified": v3_summary["phase_lock_qualified"],
                    "v4_phase_lock_qualified": v4_summary["accepted_phase_lock_count"] > 0,
                    "selection_recovery_is_scientific_qualification": False,
                },
            }
        )
        timing_rows.append(
            {
                "row_index": int(row.index),
                "row_key": row.row_key,
                "execution_order": execution_order,
                "iq_read_elapsed_ns": read_elapsed,
                "v3_elapsed_ns": v3_elapsed,
                "v4_elapsed_ns": v4_elapsed,
                "row_wall_elapsed_ns": clock_ns() - row_started,
            }
        )
        if row.row_key in parity_row_keys:
            samples_by_key[row.row_key] = np.asarray(
                samples[:parity_sample_count], dtype=np.complex128
            ).copy()
        print(f"row {position + 1}/{len(rows)} benchmarked {row.row_key}", flush=True)
    replay_elapsed = clock_ns() - replay_started
    replay_peak_rss = peak_rss_bytes()

    parity_scientific = []
    parity_timing = []
    for row in parity_rows:
        parity_row, timing_row = parity_function(
            samples_by_key[row.row_key],
            reader.sample_rate_hz,
            row,
            bindings.acquisition_module,
            parity_sample_count,
            clock_ns,
        )
        parity_scientific.append(parity_row)
        parity_timing.append(timing_row)
    aggregates = {
        "v3_complete_row_count": sum(row["v3"]["status"] == "complete" for row in scientific_rows),
        "v3_phase_lock_row_count": sum(
            row["v3"]["phase_lock_qualified"] for row in scientific_rows
        ),
        "v4_complete_row_count": sum(
            row["v4"]["numerical_status"] == "complete" for row in scientific_rows
        ),
        "v4_selected_row_count": sum(
            row["v4"]["accepted_mode_count"] > 0 for row in scientific_rows
        ),
        "v4_tracked_row_count": sum(
            row["v4"]["accepted_tracked_mode_count"] > 0 for row in scientific_rows
        ),
        "v4_phase_lock_row_count": sum(
            row["v4"]["accepted_phase_lock_count"] > 0 for row in scientific_rows
        ),
        "v4_proposal_count": sum(row["v4"]["proposal_count"] for row in scientific_rows),
        "v4_global_fallback_row_count": sum(
            row["v4"]["global_fallback_attempted"] for row in scientific_rows
        ),
        "v4_global_grid_point_count": sum(
            row["v4"]["global_evaluated_grid_point_count"] for row in scientific_rows
        ),
        "v4_global_proposal_sample_count": sum(
            row["v4"]["global_proposal_sample_count"] for row in scientific_rows
        ),
        "v4_global_proposal_symbol_count": sum(
            row["v4"]["global_proposal_symbol_count"] for row in scientific_rows
        ),
        "v4_global_proposal_frame_offset_count": sum(
            row["v4"]["global_proposal_frame_offset_count"] for row in scientific_rows
        ),
        "v4_global_refinement_coordinate_pair_count": sum(
            row["v4"]["global_refinement_coordinate_pair_count"] for row in scientific_rows
        ),
        "v4_local_evaluated_block_score_count": sum(
            row["v4"]["local_evaluated_block_score_count"] for row in scientific_rows
        ),
        "v4_local_trajectory_path_evaluated_count": sum(
            row["v4"]["local_trajectory_path_evaluated_count"] for row in scientific_rows
        ),
        "v4_local_trajectory_path_limit_truncated_count": sum(
            row["v4"]["local_trajectory_path_limit_truncated_count"] for row in scientific_rows
        ),
        "v4_global_evaluated_block_score_count": sum(
            row["v4"]["global_evaluated_block_score_count"] for row in scientific_rows
        ),
        "v4_global_trajectory_path_evaluated_count": sum(
            row["v4"]["global_trajectory_path_evaluated_count"] for row in scientific_rows
        ),
        "v4_global_trajectory_path_limit_truncated_count": sum(
            row["v4"]["global_trajectory_path_limit_truncated_count"] for row in scientific_rows
        ),
        "v4_whole_window_rescore_candidate_count": sum(
            row["v4"]["whole_window_rescore_candidate_count"] for row in scientific_rows
        ),
        "v4_whole_window_rescore_template_score_count": sum(
            row["v4"]["whole_window_rescore_template_score_count"] for row in scientific_rows
        ),
    }
    parity_pass = bool(parity_scientific) and all(
        row["status"] == "pass" for row in parity_scientific
    )
    scientific = {
        "schema": SCIENTIFIC_SCHEMA,
        "execution_status": "complete" if parity_pass else "parity_not_qualified",
        "session_id": CANARY.SESSION_ID,
        "run_id": CANARY.RUN_ID,
        "frozen_input_sha256": frozen.digest,
        "recording_manifest_sha256": reader.manifest_digest,
        "harness_source_sha256": CANARY._file_digest(Path(__file__).resolve()),
        "bindings": {
            "v3": {
                "api": bindings.v3_api_name,
                "source_sha256": bindings.v3_source_sha256,
                "config_digest": bindings.v3_config_digest,
                "config": bindings.v3_config,
            },
            "v4": {
                "api": bindings.v4_api_name,
                "source_sha256": bindings.v4_source_sha256,
                "config_digest": bindings.v4_config_digest,
                "config": bindings.v4_config,
            },
            "source_inventory": bindings.source_inventory,
            "runtime_inventory": bindings.runtime_inventory,
        },
        "coverage": {
            "population_row_count": len(frozen.rows),
            "scheduled_row_count": len(rows),
            "full_population": len(rows) == len(frozen.rows),
            "row_selection": "frozen artifact order, first maximum_rows when bounded",
            "row_keys": [row.row_key for row in rows],
        },
        "bounded_inventory": {
            "window_sample_count": CANARY.WINDOW_SAMPLE_COUNT,
            "window_complex128_bytes": CANARY.WINDOW_SAMPLE_COUNT
            * np.dtype(np.complex128).itemsize,
            "reader_maximum_cached_chunks": int(getattr(reader, "_maximum_cached_chunks", 0)),
            "parity_row_limit": parity_row_count,
            "parity_sample_limit": parity_sample_count,
            "parity_cfo_bin_count": len(PARITY_CFO_OFFSETS_HZ),
            "retained_parity_iq_bytes": len(parity_rows)
            * parity_sample_count
            * np.dtype(np.complex128).itemsize,
            "actual": aggregates,
        },
        "rows": scientific_rows,
        "verified_consumed_chunks": _chunk_inventory(scientific_rows),
        "native_numpy_parity": {
            "selection_method": "evenly spaced scheduled-row indexes including endpoints",
            "declared_rtol": PARITY_RTOL,
            "declared_atol": PARITY_ATOL,
            "all_rows_passed": parity_pass,
            "rows": parity_scientific,
        },
        "scope": {
            "candidate_only_v4": True,
            "standard_pipeline_modified": False,
            "new_rf_collected": False,
            "qnap_written": False,
            "timing_fields_in_scientific_receipt": False,
        },
    }
    scientific["receipt_digest"] = CANARY._value_digest(scientific)
    final_peak_rss = peak_rss_bytes()
    operation_elapsed = clock_ns() - operation_started

    v3_times = [int(row["v3_elapsed_ns"]) for row in timing_rows]
    v4_times = [int(row["v4_elapsed_ns"]) for row in timing_rows]
    exit_gates = evaluate_performance_exit_gates(scientific, isolated_worker_receipts)
    performance = {
        "schema": PERFORMANCE_SCHEMA,
        "scientific_receipt_digest": scientific["receipt_digest"],
        "measurement_scope": {
            "clock": "time.perf_counter_ns",
            "single_process": True,
            "single_process_measurements_are_gate_inputs": False,
            "exit_gates_use_fresh_isolated_workers": True,
            "alternating_row_order": "even rows V3->V4; odd rows V4->V3",
            "full_wall_includes": (
                "verified IQ reads, V3, V4, parity, and deterministic scientific "
                "receipt assembly; excludes runtime receipt serialization and file writes"
            ),
            "timing_is_nondeterministic": True,
        },
        "hardware": _hardware(),
        "per_row": timing_rows,
        "distributions": {
            "v3": _distribution(v3_times),
            "v4": _distribution(v4_times),
            "iq_read": _distribution([int(row["iq_read_elapsed_ns"]) for row in timing_rows]),
            "row_wall": _distribution([int(row["row_wall_elapsed_ns"]) for row in timing_rows]),
        },
        "native_numpy_parity": parity_timing,
        "replay_wall_elapsed_ns": replay_elapsed,
        "full_operation_wall_elapsed_ns": operation_elapsed,
        "peak_rss": {
            "unit": "bytes",
            "before": initial_peak_rss,
            "after_replay": replay_peak_rss,
            "after_parity": final_peak_rss,
            "maximum_observed": max(initial_peak_rss, replay_peak_rss, final_peak_rss),
            "incremental_over_entry": max(0, final_peak_rss - initial_peak_rss),
            "source": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        },
        "isolated_worker_receipts": (
            None
            if isolated_worker_receipts is None
            else {
                analyzer: CANARY._plain(receipt)
                for analyzer, receipt in sorted(isolated_worker_receipts.items())
            }
        ),
        "exit_gates": exit_gates,
    }
    return scientific, performance


def write_receipts(
    output_root: Path,
    scientific: Mapping[str, Any],
    performance: Mapping[str, Any],
    *,
    capture_root: Path | None,
) -> None:
    CANARY._validate_output_root(output_root, capture_root)
    CANARY._atomic_json(output_root / SCIENTIFIC_FILENAME, scientific)
    CANARY._atomic_json(output_root / PERFORMANCE_FILENAME, performance)
    isolated_receipts = performance.get("isolated_worker_receipts")
    if isinstance(isolated_receipts, Mapping):
        for analyzer, filename in ISOLATED_WORKER_FILENAMES.items():
            receipt = isolated_receipts.get(analyzer)
            if receipt is not None:
                CANARY._atomic_json(output_root / filename, receipt)


def main() -> int:
    arguments = _arguments()
    if arguments.maximum_rows is None:
        print("scheduling the complete frozen population", flush=True)
    frozen = CANARY.load_frozen_input(arguments.input)
    if arguments.isolated_worker is not None:
        worker_binding = load_isolated_worker_binding(arguments.isolated_worker)
        worker_reader = CANARY.FrozenCi16Reader(
            arguments.capture_root,
            expected_manifest_digest=CANARY.FROZEN_RECORDING_MANIFEST_SHA256,
            expected_session_id=CANARY.SESSION_ID,
            maximum_cached_chunks=2,
        )
        worker_receipt = run_isolated_worker(
            frozen=frozen,
            reader=worker_reader,
            binding=worker_binding,
            maximum_rows=arguments.maximum_rows,
        )
        CANARY._validate_output_root(arguments.output_root, arguments.capture_root)
        worker_path = arguments.output_root / ISOLATED_WORKER_FILENAMES[arguments.isolated_worker]
        CANARY._atomic_json(worker_path, worker_receipt)
        print(f"wrote {worker_path}", flush=True)
        return 0

    isolated_worker_receipts = run_isolated_worker_subprocesses(
        input_path=arguments.input,
        capture_root=arguments.capture_root,
        maximum_rows=arguments.maximum_rows,
    )
    bindings = load_bindings()
    reader = CANARY.FrozenCi16Reader(
        arguments.capture_root,
        expected_manifest_digest=CANARY.FROZEN_RECORDING_MANIFEST_SHA256,
        expected_session_id=CANARY.SESSION_ID,
        maximum_cached_chunks=2,
    )
    scientific, performance = run_benchmark(
        frozen=frozen,
        reader=reader,
        bindings=bindings,
        maximum_rows=arguments.maximum_rows,
        parity_row_count=arguments.parity_row_count,
        parity_sample_count=arguments.parity_sample_count,
        isolated_worker_receipts=isolated_worker_receipts,
    )
    write_receipts(
        arguments.output_root,
        scientific,
        performance,
        capture_root=arguments.capture_root,
    )
    print(
        f"wrote {arguments.output_root / SCIENTIFIC_FILENAME} and "
        f"{arguments.output_root / PERFORMANCE_FILENAME}",
        flush=True,
    )
    return (
        0
        if scientific["execution_status"] == "complete"
        and performance["exit_gates"]["status"] == "pass"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
