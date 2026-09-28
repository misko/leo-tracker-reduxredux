"""Sparse and progressive complete-evidence methods for the DS7 benchmark."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from leo.analysis.starlink import ReceiverFrequencyCalibration, SymbolwiseAcquisitionConfig
from leo.analysis.starlink.acquisition import acquire_symbolwise
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
)
from leo.scanner.models import Glrt64FirstDetection, ScannerConfiguration

HERE = Path(__file__).resolve().parent
PRIOR_METHOD_ROOT = HERE.parent / "2026_09_28_ds7_glrt_benchmark"
if str(PRIOR_METHOD_ROOT) not in sys.path:
    sys.path.insert(0, str(PRIOR_METHOD_ROOT))
_prior_methods = importlib.import_module("methods")
if Path(_prior_methods.__file__).resolve() != (PRIOR_METHOD_ROOT / "methods.py").resolve():
    raise RuntimeError("methods resolved outside the frozen DS7 benchmark")
BenchmarkMethod = _prior_methods.BenchmarkMethod
MethodRun = _prior_methods.MethodRun

_ZERO_CALIBRATION_SHA256 = "0" * 64
_CFO_GATE_HZ = 8_000.0
_ALL = None
_METHODS: dict[str, tuple[tuple[int, ...] | None, int, bool]] = {
    "optimized_full": (_ALL, 8, False),
    "windows6": ((0, 2, 4, 6, 8, 10), 8, False),
    "windows4": ((0, 3, 6, 9), 8, False),
    "windows3": ((0, 5, 10), 8, False),
    "windows6_candidates2": ((0, 2, 4, 6, 8, 10), 2, False),
    "windows4_candidates2": ((0, 3, 6, 9), 2, False),
    "candidates4": (_ALL, 4, False),
    "candidates6": (_ALL, 6, False),
    "progressive4": ((0, 3, 6, 9), 8, True),
}


class SparseMethod(BenchmarkMethod):
    def __init__(
        self,
        name: str,
        initial_indices: tuple[int, ...] | None,
        candidate_budget: int,
        progressive: bool,
    ) -> None:
        self.name = name
        self._initial_indices = initial_indices
        self._candidate_budget = candidate_budget
        self._progressive = progressive

    def reset(self) -> None:
        return None

    def analyze(
        self,
        iq_complex: np.ndarray,
        configuration: ScannerConfiguration,
        edge: object,
        context: Mapping[str, object],
    ) -> MethodRun:
        values = _validate_call(iq_complex, configuration, context)
        initial = (
            tuple(range(configuration.scheduled_probe_count))
            if self._initial_indices is None
            else self._initial_indices
        )
        if not initial or min(initial) < 0 or max(initial) >= configuration.scheduled_probe_count:
            raise ValueError("sparse method probe schedule is outside the configured dwell")

        responses: dict[tuple[int, int], Glrt64ProbeResponse] = {}
        receiver_order = {
            receiver: index for index, receiver in enumerate(configuration.receiver_ids)
        }

        def evaluate(index: int, receiver: int) -> None:
            key = (index, receiver)
            if key in responses:
                raise RuntimeError("sparse method attempted duplicate receiver/probe work")
            column = receiver_order[receiver]
            responses[key] = _evaluate_probe(
                values,
                configuration,
                edge,
                index,
                column,
                receiver,
                self._candidate_budget,
            )

        for index in initial:
            for receiver in configuration.receiver_ids:
                evaluate(index, receiver)

        ordered = _ordered_responses(responses, configuration)
        analysis, confirmed = _fold_responses(ordered, configuration)
        fallback_indices: list[int] = []
        if self._progressive and len(confirmed) < len(configuration.receiver_ids):
            remaining = tuple(
                index
                for index in range(configuration.scheduled_probe_count)
                if index not in initial
            )
            for index in remaining:
                pending = tuple(
                    receiver
                    for receiver in configuration.receiver_ids
                    if receiver not in confirmed
                )
                if not pending:
                    break
                fallback_indices.append(index)
                for receiver in pending:
                    evaluate(index, receiver)
                ordered = _ordered_responses(responses, configuration)
                analysis, confirmed = _fold_responses(ordered, configuration)

        processed = {
            str(receiver): sorted(
                index for index, candidate_receiver in responses if candidate_receiver == receiver
            )
            for receiver in configuration.receiver_ids
        }
        if self._progressive:
            route = (
                "progressive_initial"
                if not fallback_indices
                else (
                    "progressive_fallback_confirmed"
                    if len(confirmed) == len(configuration.receiver_ids)
                    else "progressive_fallback_exhausted"
                )
            )
        elif len(responses) == (
            configuration.scheduled_probe_count * len(configuration.receiver_ids)
        ):
            route = "complete_schedule"
        else:
            route = "fixed_sparse"
        diagnostics: dict[str, object] = {
            "method": self.name,
            "route": route,
            "approximate": self.name != "optimized_full",
            "acquisition_candidate_budget": self._candidate_budget,
            "acquisition_calls": len(responses),
            "glrt_candidate_calls": sum(
                len(response.candidates) for response in responses.values()
            ),
            "processed_probe_indices_by_receiver": processed,
            "initial_probe_indices": list(initial),
            "fallback_probe_indices": fallback_indices,
            "confirmed_receiver_ids": sorted(confirmed),
            "probe_response_count": len(analysis.probes),
            "candidate_response_count": sum(len(probe.candidates) for probe in analysis.probes),
            "decision_confirmed": analysis.first is not None,
            **{key: context[key] for key in (
                "session_id",
                "visit_index",
                "sample_start_counter",
                "rate_hz",
                "target_index",
            )},
        }
        return MethodRun(analysis=analysis, diagnostics=diagnostics)


def make_method(name: str) -> BenchmarkMethod:
    try:
        initial, budget, progressive = _METHODS[name]
    except KeyError as error:
        raise ValueError(f"unknown sparse method {name!r}; choices={sorted(_METHODS)}") from error
    return SparseMethod(name, initial, budget, progressive)


def _evaluate_probe(
    values: np.ndarray,
    configuration: ScannerConfiguration,
    edge: object,
    probe_index: int,
    column: int,
    receiver_id: int,
    candidate_budget: int,
) -> Glrt64ProbeResponse:
    start = probe_index * configuration.probe_stride_samples
    stop = start + configuration.probe_samples
    probe = np.ascontiguousarray(values[start:stop, column], dtype=np.complex128)
    calibration = ReceiverFrequencyCalibration(
        receiver_id=str(receiver_id),
        center_hz=0.0,
        calibration_sha256=_ZERO_CALIBRATION_SHA256,
    )
    acquisition_config = SymbolwiseAcquisitionConfig(
        maximum_probe_samples=configuration.probe_samples,
        retained_candidate_count=candidate_budget,
        candidate_epoch_separation_samples=5,
        candidate_cfo_separation_hz=10_000.0,
    )
    acquired = acquire_symbolwise(
        probe,
        configuration.sample_rate_hz,
        calibration,
        edge=edge,
        config=acquisition_config,
    )
    candidates: list[Glrt64CandidateResponse] = []
    for candidate in acquired.candidates[:candidate_budget]:
        score = conditioned_glrt64_score(
            probe,
            configuration.sample_rate_hz,
            epoch_sample=candidate.refined_epoch_sample,
            acquired_cfo_hz=candidate.absolute_cfo_hz,
            edge=edge,
        )
        candidates.append(
            Glrt64CandidateResponse(
                candidate_rank=candidate.rank,
                epoch_sample=candidate.refined_epoch_sample,
                acquired_cfo_hz=candidate.absolute_cfo_hz,
                residual_cfo_hz=score.residual_cfo_hz,
                tracking_cfo_hz=score.tracking_cfo_hz,
                exact_score=score.exact_score,
                control_score=score.control_score or 0.0,
                margin=score.margin,
                passed_margin_gate=score.margin >= configuration.glrt64_margin_gate,
            )
        )
    return Glrt64ProbeResponse(
        receiver_id=receiver_id,
        probe_index=probe_index,
        probe_start_ms=probe_index * configuration.probe_stride_ms,
        candidates=tuple(candidates),
    )


def _ordered_responses(
    responses: Mapping[tuple[int, int], Glrt64ProbeResponse],
    configuration: ScannerConfiguration,
) -> tuple[Glrt64ProbeResponse, ...]:
    receiver_order = {receiver: index for index, receiver in enumerate(configuration.receiver_ids)}
    return tuple(
        response
        for _, response in sorted(
            responses.items(),
            key=lambda item: (item[0][0], receiver_order[item[0][1]]),
        )
    )


def _fold_responses(
    responses: Sequence[Glrt64ProbeResponse],
    configuration: ScannerConfiguration,
) -> tuple[DwellGlrt64Analysis, set[int]]:
    responses = tuple(responses)
    keys = tuple((response.probe_index, response.receiver_id) for response in responses)
    receiver_order = {receiver: index for index, receiver in enumerate(configuration.receiver_ids)}
    if len(keys) != len(set(keys)) or keys != tuple(
        sorted(keys, key=lambda item: (item[0], receiver_order[item[1]]))
    ):
        raise ValueError("sparse responses must be unique and chronological")

    history: dict[int, list[Glrt64FirstDetection]] = {
        receiver: [] for receiver in configuration.receiver_ids
    }
    best: float | None = None
    decision_best: float | None = None
    first: Glrt64FirstDetection | None = None
    confirmed: set[int] = set()
    cursor = 0
    for probe_index in sorted({response.probe_index for response in responses}):
        hits: list[Glrt64FirstDetection] = []
        while cursor < len(responses) and responses[cursor].probe_index == probe_index:
            response = responses[cursor]
            cursor += 1
            for candidate in response.candidates:
                best = candidate.margin if best is None else max(best, candidate.margin)
                if candidate.passed_margin_gate:
                    hits.append(
                        Glrt64FirstDetection(
                            receiver_id=response.receiver_id,
                            probe_index=response.probe_index,
                            probe_start_ms=response.probe_start_ms,
                            candidate_rank=candidate.candidate_rank,
                            epoch_sample=candidate.epoch_sample,
                            acquired_cfo_hz=candidate.acquired_cfo_hz,
                            residual_cfo_hz=candidate.residual_cfo_hz,
                            tracking_cfo_hz=candidate.tracking_cfo_hz,
                            exact_score=candidate.exact_score,
                            control_score=candidate.control_score,
                            margin=candidate.margin,
                        )
                    )
        for hit in sorted(hits, key=lambda item: (item.receiver_id, -item.margin)):
            compatible = tuple(
                prior
                for prior in history[hit.receiver_id]
                if hit.probe_start_ms - prior.probe_start_ms >= configuration.probe_ms
                and abs(hit.tracking_cfo_hz - prior.tracking_cfo_hz) <= _CFO_GATE_HZ
            )
            if compatible:
                confirmed.add(hit.receiver_id)
                if first is None:
                    first = min(
                        compatible,
                        key=lambda item: (item.probe_index, -item.margin),
                    )
                    decision_best = best
        for hit in hits:
            history[hit.receiver_id].append(hit)

    complete = len(responses) == (
        configuration.scheduled_probe_count * len(configuration.receiver_ids)
    )
    if first is not None:
        reason = (
            "two same-receiver non-overlapping 20 ms GLRT-64 probes "
            "passed the margin gate within 8 kHz CFO"
        )
    elif complete:
        reason = (
            f"all {configuration.scheduled_probe_count} overlapping "
            f"{configuration.probe_ms} ms probes completed without a confirmed "
            "same-receiver CFO-consistent pair"
        )
    else:
        reason = (
            f"sparse schedule completed {len(responses)} receiver/probe analyses "
            "without a confirmed same-receiver CFO-consistent pair"
        )
    return (
        DwellGlrt64Analysis(
            first=first,
            decision_best_margin=decision_best if first is not None else best,
            full_best_margin=best,
            reason=reason,
            probes=responses,
        ),
        confirmed,
    )


def _validate_call(
    iq_complex: np.ndarray,
    configuration: ScannerConfiguration,
    context: Mapping[str, object],
) -> np.ndarray:
    values = np.asarray(iq_complex)
    expected = (configuration.dwell_samples, len(configuration.receiver_ids))
    if values.ndim != 2 or values.shape != expected or not np.iscomplexobj(values):
        raise ValueError(f"iq_complex must be a complex scanner dwell with shape {expected}")
    required = ("session_id", "visit_index", "sample_start_counter", "rate_hz", "target_index")
    missing = tuple(key for key in required if key not in context)
    if missing:
        raise ValueError(f"method context is missing: {', '.join(missing)}")
    if context["rate_hz"] != configuration.sample_rate_hz:
        raise ValueError("context rate_hz differs from scanner configuration")
    return values


__all__ = ["SparseMethod", "make_method"]
