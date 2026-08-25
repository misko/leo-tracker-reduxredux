#!/usr/bin/env python3
"""Replay additive pilot Kalman variants on the frozen August-22 five dwells.

The comparison is causal and frame matched.  Each Kalman residual is its
serialized pre-update frequency innovation after twelve supported frames.  The
baseline is an equal-weight robust line fitted only to supported observations
in the preceding 20 ms.  Equal weights are deliberate: the public frame result
does not expose the raw frequency-discriminator uncertainty; its
``frequency_sigma_hz`` is the posterior state sigma and must not be recycled as
independent measurement noise.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import report_pilot_pnt_kalman as base  # noqa: E402
import report_pilot_pnt_kalman_five_dwells as five  # noqa: E402

from leo.analysis.qam import (  # noqa: E402
    PilotPntKalmanConfigV2,
    PilotPntKalmanConfigV3,
    analyze_contiguous_pilot_pnt_kalman_v2,
    analyze_contiguous_pilot_pnt_kalman_v3,
)
from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL  # noqa: E402
from leo.storage import PinnedLocalRoot, RecordingStore  # noqa: E402


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracker", choices=("v2", "v3"), required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def robust_line(time_s: np.ndarray, cfo_hz: np.ndarray) -> tuple[float, np.ndarray]:
    """Fit the frozen equal-weight Huber line used by this comparison."""

    reference = float(np.median(time_s))
    design = np.column_stack((np.ones(len(time_s)), time_s - reference))
    coefficients = np.linalg.lstsq(design, cfo_hz, rcond=None)[0]
    for _ in range(8):
        residual = cfo_hz - design @ coefficients
        scale = max(
            1.4826 * float(np.median(np.abs(residual - np.median(residual)))),
            15.0,
        )
        standardized = np.abs(residual) / scale
        weights = np.ones(len(residual))
        mask = standardized > 1.5
        weights[mask] = 1.5 / standardized[mask]
        root = np.sqrt(weights)
        updated = np.linalg.lstsq(
            design * root[:, None],
            cfo_hz * root,
            rcond=None,
        )[0]
        if np.max(np.abs(updated - coefficients)) < 1e-8:
            coefficients = updated
            break
        coefficients = updated
    return reference, coefficients


def same_mask(case_results: list[tuple[Any, Any]]) -> dict[str, Any]:
    """Compare pre-update Kalman and trailing-line errors on identical frames."""

    pairs: list[tuple[float, float, float]] = []
    for case, result in case_results:
        frames = result.frames
        supported = np.asarray([row.measurement_supported for row in frames], dtype=bool)
        times = np.asarray([row.time_s for row in frames], dtype=float)
        cfo = np.asarray([row.absolute_cfo_measurement_hz for row in frames], dtype=float)
        supported_offsets = np.flatnonzero(supported)
        line_error: dict[int, float] = {}
        for position, offset in enumerate(supported_offsets):
            prior = supported_offsets[:position]
            prior = prior[times[prior] >= times[offset] - 0.020]
            if len(prior) < 6:
                continue
            reference, coefficients = robust_line(times[prior], cfo[prior])
            predicted = float(coefficients[0] + coefficients[1] * (times[offset] - reference))
            line_error[int(offset)] = float(cfo[offset] - predicted)
        for offset in supported_offsets[12:]:
            offset = int(offset)
            if offset not in line_error:
                continue
            pairs.append(
                (
                    float(case.detection_time_s + times[offset]),
                    float(frames[offset].frequency_innovation_hz),
                    line_error[offset],
                )
            )
    blocks: dict[int, list[tuple[float, float]]] = {}
    for absolute_time_s, kalman_error, line_error in pairs:
        blocks.setdefault(math.floor(absolute_time_s), []).append((kalman_error, line_error))
    if not blocks:
        return {"status": "not_estimable", "common_frame_count": 0}
    kalman_mse = [np.mean([row[0] ** 2 for row in blocks[key]]) for key in sorted(blocks)]
    line_mse = [np.mean([row[1] ** 2 for row in blocks[key]]) for key in sorted(blocks)]
    kalman_rms = math.sqrt(float(np.mean(kalman_mse)))
    line_rms = math.sqrt(float(np.mean(line_mse)))
    return {
        "status": "estimable",
        "common_frame_count": len(pairs),
        "recording_anchored_one_second_block_count": len(blocks),
        "kalman_block_equal_rms_hz": kalman_rms,
        "trailing_20ms_block_equal_rms_hz": line_rms,
        "kalman_to_trailing_20ms_rms_ratio": kalman_rms / line_rms,
        "kalman_fractional_improvement": 1.0 - kalman_rms / line_rms,
        "mask": (
            "intersection of post-12-supported-frame one-step Kalman innovations "
            "and causal trailing-20ms predictions"
        ),
    }


@dataclasses.dataclass(frozen=True, slots=True)
class FilterCaseResult:
    case: Any
    exact: Any
    rolled: Any


def analyze_filter_case(reader: Any, case: Any, analyzer: Any) -> FilterCaseResult:
    """Run only the two filters needed by the same-mask benchmark.

    Unlike the legacy figure helper, this path does not require a measured line
    inside every selected window. A fail-closed V3 window legitimately has no
    frames and contributes no common-mask observation.
    """

    sample_count = round(base.WINDOW_S * reader.sample_rate_hz)
    raw = reader.read(case.sample_start, sample_count, receiver_ids=(case.receiver,))
    iq = base._complex_receiver(raw)
    common = {
        "epoch_sample": case.local_epoch_sample,
        "initial_absolute_cfo_hz": case.initial_cfo_hz,
        "edge": case.edge,
    }
    exact = analyzer(iq, reader.sample_rate_hz, **common)
    rolled = analyzer(
        iq,
        reader.sample_rate_hz,
        expected_symbol_roll=CONTROL_SYMBOL_ROLL,
        **common,
    )
    return FilterCaseResult(case=case, exact=exact, rolled=rolled)


def main() -> None:
    arguments = _arguments()
    started = time.perf_counter()
    if arguments.tracker == "v2":
        analyzer = analyze_contiguous_pilot_pnt_kalman_v2
        config = PilotPntKalmanConfigV2()
    else:
        analyzer = analyze_contiguous_pilot_pnt_kalman_v3
        config = PilotPntKalmanConfigV3()
    selections = {}
    manifests = {}
    for dwell in five.DWELLS:
        manifests[dwell.label] = five._validate_run_manifest(arguments.bulk_root, dwell)
        selections[dwell.label] = five._path_selection(arguments.bulk_root, dwell)
    store = RecordingStore.open_pinned(PinnedLocalRoot(arguments.bulk_root))
    rows = []
    try:
        for dwell in five.DWELLS:
            selection = selections[dwell.label]
            bundle = store.inspect(dwell.session_id)
            if bundle.manifest_sha256 != dwell.recording_manifest_digest:
                raise ValueError(f"recording manifest digest changed for {dwell.label}")
            reader = store.reader(bundle, selection.path.stream, verify=True)
            analyzed = [analyze_filter_case(reader, case, analyzer) for case in selection.cases]
            evaluated = [(result.case, result.exact) for result in analyzed]
            metric = same_mask(evaluated)
            metric.update(
                {
                    "label": dwell.label,
                    "session_id": dwell.session_id,
                    "run_id": dwell.run_id,
                    "pipeline_release_id": manifests[dwell.label]["pipeline_release_id"],
                    "recording_manifest_digest": dwell.recording_manifest_digest,
                    "run_manifest_digest": dwell.run_manifest_digest,
                    "scope_key": selection.path.scope_key,
                    "stream_id": selection.path.stream,
                    "receiver_id": selection.path.receiver,
                    "edge": selection.path.edge.value,
                    "window_count": len(evaluated),
                    "supported_frame_count": sum(
                        result.supported_frame_count for _, result in evaluated
                    ),
                    "phase_lock_count": sum(result.phase_lock_qualified for _, result in evaluated),
                    "rolled_supported_frame_count": sum(
                        result.rolled.supported_frame_count for result in analyzed
                    ),
                    "rolled_phase_lock_count": sum(
                        result.rolled.phase_lock_qualified for result in analyzed
                    ),
                }
            )
            rows.append(metric)
            print(json.dumps(metric), flush=True)
    finally:
        store.close()
    estimable = [row for row in rows if row["status"] == "estimable"]
    ratios = [float(row["kalman_to_trailing_20ms_rms_ratio"]) for row in estimable]
    aggregate = {
        "stratum": "August-22 earlier-release frozen exact-window replay",
        "tracker": arguments.tracker,
        "dwell_count": len(rows),
        "estimable_dwell_count": len(estimable),
        "equal_dwell_geometric_mean_kalman_to_20ms_ratio": math.exp(float(np.mean(np.log(ratios)))),
        "kalman_better_dwell_count": sum(value < 1.0 for value in ratios),
        "runtime_s": time.perf_counter() - started,
        "inference_unit": "dwell",
        "frame_pooling_across_dwells": False,
    }
    source_path = Path(sys.modules[analyzer.__module__].__file__).resolve()
    document = {
        "schema": "org.leo.research.aug22-pnt-kalman-versus-20ms-same-mask/v1",
        "tracker": arguments.tracker,
        "tracker_config": dataclasses.asdict(config),
        "source_selection_algorithm": (
            "unchanged report_pilot_pnt_kalman_five_dwells.py five-dwell selection"
        ),
        "line_weighting": (
            "equal weight with Huber residual reweighting; raw discriminator sigma is "
            "not exposed by PilotPntKalmanFrame"
        ),
        "tracker_source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "dwells": rows,
        "aggregate": aggregate,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(aggregate, indent=2), flush=True)


if __name__ == "__main__":
    main()
