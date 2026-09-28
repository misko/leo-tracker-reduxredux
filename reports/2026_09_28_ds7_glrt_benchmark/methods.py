"""Bounded detector methods for the DS7 saved-IQ GLRT benchmark."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from threading import RLock
from types import ModuleType

import numpy as np

import leo.scanner.detector as detector_module
from leo.analysis.starlink import ReceiverFrequencyCalibration, SymbolwiseAcquisitionConfig
from leo.analysis.starlink.acquisition import acquire_symbolwise as optimized_acquire
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score as optimized_score
from leo.scanner.detector import DwellGlrt64Analysis
from leo.scanner.models import ScannerConfiguration

HERE = Path(__file__).resolve().parent
REFERENCE_ROOT = HERE.parent / "2026_09_27_server_scan_speed"
ORIGINAL_ACQUISITION = REFERENCE_ROOT / "acquisition_peak" / "original" / "acquisition.py"
ORIGINAL_PILOT_METHODS = REFERENCE_ROOT / "pilot_methods_baseline.py"

ORIGINAL_ACQUISITION_SHA256 = (
    "b4891b7ceb7f60a8d23c7e8127b836159a48aa5a2e2f0245e25ac26bd96d3742"
)
ORIGINAL_PILOT_METHODS_SHA256 = (
    "d6a599d7eb9cb4d6de5f7e6781cb6ea3ce65de422723d94ebfec9ea0a1fa4193"
)

_LOCAL_CFO_RADIUS_HZ = 20_000.0
_MAX_PRIOR_AGE_S = 3.0
_CONFIRMATION_CFO_GATE_HZ = 8_000.0
_DETECTOR_PATCH_LOCK = RLock()

Acquire = Callable[..., object]
Score = Callable[..., object]


@dataclass(frozen=True, slots=True)
class MethodRun:
    analysis: DwellGlrt64Analysis
    diagnostics: dict[str, object]


@dataclass(frozen=True, slots=True)
class _CallContext:
    session_id: str
    visit_index: int
    sample_start_counter: int
    rate_hz: int
    target_index: int


@dataclass(frozen=True, slots=True)
class _Prior:
    visit_index: int
    sample_start_counter: int
    tracking_cfo_hz: float


class BenchmarkMethod:
    """One complete, serial detector method used by the benchmark runner."""

    name: str

    def reset(self) -> None:
        """Discard all causal state."""

    def analyze(
        self,
        iq_complex: np.ndarray,
        configuration: ScannerConfiguration,
        edge: object,
        context: Mapping[str, object],
    ) -> MethodRun:
        raise NotImplementedError


class _BlindMethod(BenchmarkMethod):
    def __init__(
        self,
        name: str,
        acquire: Acquire,
        score: Score,
        *,
        candidate_budget: int | None = None,
        approximate: bool = False,
    ) -> None:
        self.name = name
        self._acquire = acquire
        self._score = score
        self._candidate_budget = candidate_budget
        self._approximate = approximate

    def reset(self) -> None:
        return None

    def analyze(
        self,
        iq_complex: np.ndarray,
        configuration: ScannerConfiguration,
        edge: object,
        context: Mapping[str, object],
    ) -> MethodRun:
        call_context = _validate_call(iq_complex, configuration, context)
        effective = configuration
        if self._candidate_budget is not None:
            effective = configuration.model_copy(
                update={"maximum_acquisition_candidates": self._candidate_budget}
            )
        analysis = _run_detector(iq_complex, effective, edge, self._acquire, self._score)
        return MethodRun(
            analysis,
            _diagnostics(
                self.name,
                analysis,
                call_context,
                route="full_blind",
                approximate=self._approximate,
                acquisition_candidate_budget=effective.maximum_acquisition_candidates,
                detector_calls=1,
            ),
        )


class _LocalFallbackMethod(BenchmarkMethod):
    name = "local_fallback"

    def __init__(self, acquire: Acquire, score: Score) -> None:
        self._acquire = acquire
        self._score = score
        self._session_id: str | None = None
        self._priors: dict[tuple[int, int, int], _Prior] = {}

    def reset(self) -> None:
        self._session_id = None
        self._priors.clear()

    def analyze(
        self,
        iq_complex: np.ndarray,
        configuration: ScannerConfiguration,
        edge: object,
        context: Mapping[str, object],
    ) -> MethodRun:
        call_context = _validate_call(iq_complex, configuration, context)
        session_reset = self._session_id is not None and self._session_id != call_context.session_id
        if self._session_id != call_context.session_id:
            self._priors.clear()
            self._session_id = call_context.session_id

        eligible = self._eligible_priors(call_context, configuration)
        if not eligible:
            analysis = _run_detector(
                iq_complex,
                configuration,
                edge,
                self._acquire,
                self._score,
            )
            fresh = _confirmed_tracking_cfo_by_receiver(analysis, configuration)
            self._store_fresh(call_context, fresh)
            return MethodRun(
                analysis,
                _diagnostics(
                    self.name,
                    analysis,
                    call_context,
                    route="full_blind_no_prior",
                    approximate=True,
                    acquisition_candidate_budget=configuration.maximum_acquisition_candidates,
                    detector_calls=1,
                    session_reset=session_reset,
                    local_seed_receiver_ids=[],
                    fresh_confirmed_receiver_ids=sorted(fresh),
                    fallback_reason="no_eligible_prior",
                ),
            )

        local_calls = 0
        blind_receiver_calls = 0

        def local_acquire(
            samples: np.ndarray,
            sample_rate_hz: float,
            calibration: ReceiverFrequencyCalibration,
            *,
            edge: object,
            config: SymbolwiseAcquisitionConfig,
        ) -> object:
            nonlocal local_calls, blind_receiver_calls
            receiver_id = int(calibration.receiver_id)
            prior = eligible.get(receiver_id)
            if prior is None:
                blind_receiver_calls += 1
                return self._acquire(
                    samples,
                    sample_rate_hz,
                    calibration,
                    edge=edge,
                    config=config,
                )
            local_calls += 1
            center = min(
                config.residual_cfo_max_hz,
                max(config.residual_cfo_min_hz, prior.tracking_cfo_hz),
            )
            local_config = replace(
                config,
                residual_cfo_min_hz=max(
                    config.residual_cfo_min_hz,
                    center - _LOCAL_CFO_RADIUS_HZ,
                ),
                residual_cfo_max_hz=min(
                    config.residual_cfo_max_hz,
                    center + _LOCAL_CFO_RADIUS_HZ,
                ),
            )
            return self._acquire(
                samples,
                sample_rate_hz,
                calibration,
                edge=edge,
                config=local_config,
            )

        local_analysis = _run_detector(
            iq_complex,
            configuration,
            edge,
            local_acquire,
            self._score,
        )
        local_fresh = _confirmed_tracking_cfo_by_receiver(local_analysis, configuration)
        seeded_receivers = set(eligible)
        missing = sorted(seeded_receivers - set(local_fresh))
        if not missing:
            self._store_fresh(call_context, local_fresh)
            return MethodRun(
                local_analysis,
                _diagnostics(
                    self.name,
                    local_analysis,
                    call_context,
                    route="local_cfo",
                    approximate=True,
                    acquisition_candidate_budget=configuration.maximum_acquisition_candidates,
                    detector_calls=1,
                    session_reset=session_reset,
                    local_seed_receiver_ids=sorted(seeded_receivers),
                    fresh_confirmed_receiver_ids=sorted(local_fresh),
                    local_acquisition_calls=local_calls,
                    blind_receiver_acquisition_calls=blind_receiver_calls,
                    fallback_reason=None,
                ),
            )

        blind_analysis = _run_detector(
            iq_complex,
            configuration,
            edge,
            self._acquire,
            self._score,
        )
        blind_fresh = _confirmed_tracking_cfo_by_receiver(blind_analysis, configuration)
        self._store_fresh(call_context, blind_fresh)
        return MethodRun(
            blind_analysis,
            _diagnostics(
                self.name,
                blind_analysis,
                call_context,
                route="local_then_full_blind",
                approximate=True,
                acquisition_candidate_budget=configuration.maximum_acquisition_candidates,
                detector_calls=2,
                session_reset=session_reset,
                local_seed_receiver_ids=sorted(seeded_receivers),
                fresh_confirmed_receiver_ids=sorted(blind_fresh),
                local_acquisition_calls=local_calls,
                blind_receiver_acquisition_calls=blind_receiver_calls,
                fallback_reason="seeded_receiver_missing_fresh_pair",
                missing_local_pair_receiver_ids=missing,
            ),
        )

    def _eligible_priors(
        self,
        context: _CallContext,
        configuration: ScannerConfiguration,
    ) -> dict[int, _Prior]:
        result: dict[int, _Prior] = {}
        maximum_age = round(_MAX_PRIOR_AGE_S * context.rate_hz)
        for receiver_id in configuration.receiver_ids:
            prior = self._priors.get((context.target_index, context.rate_hz, receiver_id))
            if prior is None:
                continue
            age = context.sample_start_counter - prior.sample_start_counter
            if (
                context.visit_index > prior.visit_index
                and 0 < age <= maximum_age
            ):
                result[receiver_id] = prior
        return result

    def _store_fresh(self, context: _CallContext, fresh: Mapping[int, float]) -> None:
        for receiver_id, tracking_cfo_hz in fresh.items():
            self._priors[(context.target_index, context.rate_hz, receiver_id)] = _Prior(
                visit_index=context.visit_index,
                sample_start_counter=context.sample_start_counter,
                tracking_cfo_hz=float(tracking_cfo_hz),
            )


def make_method(name: str) -> BenchmarkMethod:
    """Create one isolated benchmark method by its frozen experiment name."""

    if name == "original":
        acquisition, pilot = _original_modules()
        return _BlindMethod(
            name,
            acquisition.acquire_symbolwise,
            pilot.conditioned_glrt64_score,
        )
    if name == "optimized":
        return _BlindMethod(name, optimized_acquire, optimized_score)
    if name == "candidates2":
        return _BlindMethod(
            name,
            optimized_acquire,
            optimized_score,
            candidate_budget=2,
            approximate=True,
        )
    if name == "local_fallback":
        return _LocalFallbackMethod(optimized_acquire, optimized_score)
    raise ValueError(
        "method must be one of: original, optimized, local_fallback, candidates2"
    )


@contextmanager
def _patched_detector(acquire: Acquire, score: Score) -> Iterator[None]:
    with _DETECTOR_PATCH_LOCK:
        previous_acquire = detector_module.acquire_symbolwise
        previous_score = detector_module.conditioned_glrt64_score
        detector_module.acquire_symbolwise = acquire
        detector_module.conditioned_glrt64_score = score
        try:
            yield
        finally:
            detector_module.acquire_symbolwise = previous_acquire
            detector_module.conditioned_glrt64_score = previous_score


def _run_detector(
    iq_complex: np.ndarray,
    configuration: ScannerConfiguration,
    edge: object,
    acquire: Acquire,
    score: Score,
) -> DwellGlrt64Analysis:
    with _patched_detector(acquire, score):
        return detector_module.analyze_glrt64_dwell(iq_complex, configuration, edge=edge)


def _confirmed_tracking_cfo_by_receiver(
    analysis: DwellGlrt64Analysis,
    configuration: ScannerConfiguration,
) -> dict[int, float]:
    history: dict[int, list[tuple[int, float]]] = {
        receiver_id: [] for receiver_id in configuration.receiver_ids
    }
    confirmed: dict[int, float] = {}
    for response in analysis.probes:
        hits = tuple(candidate for candidate in response.candidates if candidate.passed_margin_gate)
        receiver_history = history.setdefault(response.receiver_id, [])
        for hit in hits:
            if any(
                response.probe_start_ms - prior_start_ms >= configuration.probe_ms
                and abs(hit.tracking_cfo_hz - prior_cfo_hz) <= _CONFIRMATION_CFO_GATE_HZ
                for prior_start_ms, prior_cfo_hz in receiver_history
            ):
                confirmed[response.receiver_id] = float(hit.tracking_cfo_hz)
        receiver_history.extend(
            (response.probe_start_ms, float(hit.tracking_cfo_hz)) for hit in hits
        )
    return confirmed


def _validate_call(
    iq_complex: np.ndarray,
    configuration: ScannerConfiguration,
    context: Mapping[str, object],
) -> _CallContext:
    values = np.asarray(iq_complex)
    expected = (configuration.dwell_samples, len(configuration.receiver_ids))
    if values.ndim != 2 or values.shape != expected or not np.iscomplexobj(values):
        raise ValueError(f"iq_complex must be a complex scanner dwell with shape {expected}")
    required = (
        "session_id",
        "visit_index",
        "sample_start_counter",
        "rate_hz",
        "target_index",
    )
    missing = tuple(key for key in required if key not in context)
    if missing:
        raise ValueError(f"method context is missing: {', '.join(missing)}")
    session_id = context["session_id"]
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("context session_id must be a nonempty string")
    integers: dict[str, int] = {}
    for key in required[1:]:
        value = context[key]
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 0:
            raise ValueError(f"context {key} must be a nonnegative integer")
        integers[key] = int(value)
    if integers["rate_hz"] != configuration.sample_rate_hz:
        raise ValueError("context rate_hz differs from scanner configuration")
    return _CallContext(session_id=session_id, **integers)


def _diagnostics(
    method: str,
    analysis: DwellGlrt64Analysis,
    context: _CallContext,
    **values: object,
) -> dict[str, object]:
    return {
        "method": method,
        "session_id": context.session_id,
        "visit_index": context.visit_index,
        "sample_start_counter": context.sample_start_counter,
        "rate_hz": context.rate_hz,
        "target_index": context.target_index,
        "probe_response_count": len(analysis.probes),
        "candidate_response_count": sum(len(probe.candidates) for probe in analysis.probes),
        "decision_confirmed": analysis.first is not None,
        **values,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_module(path: Path, name: str, expected_sha256: str) -> ModuleType:
    actual = _sha256(path)
    if actual != expected_sha256:
        raise RuntimeError(f"frozen method source changed: {path} ({actual})")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen method source: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _original_modules() -> tuple[ModuleType, ModuleType]:
    acquisition = _load_module(
        ORIGINAL_ACQUISITION,
        "_ds7_original_acquisition",
        ORIGINAL_ACQUISITION_SHA256,
    )
    pilot = _load_module(
        ORIGINAL_PILOT_METHODS,
        "_ds7_original_pilot_methods",
        ORIGINAL_PILOT_METHODS_SHA256,
    )
    return acquisition, pilot


__all__ = ["BenchmarkMethod", "MethodRun", "make_method"]
