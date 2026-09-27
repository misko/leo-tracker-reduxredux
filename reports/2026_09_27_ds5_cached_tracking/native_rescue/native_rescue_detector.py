"""One bounded Python-acquisition rescue for an inactive native receiver.

The unchanged :class:`NativeTradeoffDetector` remains the primary detector and
the sole owner of causal state.  This wrapper processes both receivers, keeps
every primary positive, and may spend one probe-zero Python acquisition on one
inactive receiver.  A proposal becomes a rescue only after guarded native
measurements on probe zero and the non-overlapping probe two agree.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import sys
from typing import Any, Callable

import numpy as np


HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
REPO = HERE.parents[2]
SRC = REPO / "src"
TRADEOFF = REPORT / "native_tradeoff"

# The research tree also contains a deployment checkout with a ``leo`` package.
# Pin the current repository before importing the frozen native wrappers.
for entry in (str(SRC), str(TRADEOFF)):
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)

from leo.analysis.starlink.acquisition import (  # noqa: E402
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score  # noqa: E402
from native_tradeoff_detector import (  # noqa: E402
    CFO_GATE_HZ,
    FRAME_RATE_HZ,
    MARGIN_GATE,
    CacheKey,
    NativeEvidence,
    NativePair,
    NativeTradeoffDecision,
    NativeTradeoffDetector,
    circular_samples,
)


PROBE_ZERO = 0
CONFIRMATION_PROBE = 2
PROBE_STRIDE_MS = 10
MAXIMUM_CANDIDATES = 10
TIMING_GATE_SECONDS = 2e-6
ZERO_CALIBRATION_SHA256 = "0" * 64


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


@dataclass(frozen=True, slots=True)
class RescueEvent:
    receiver: int
    candidate_rank: int
    python_epoch_sample: int
    python_scoring_cfo_hz: float
    python_tracking_cfo_hz: float
    python_exact_score: float
    python_control_score: float
    python_margin: float
    seed: NativeEvidence | None
    confirmation: NativeEvidence | None
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class RescueVisitDecision:
    """Both per-RX decisions plus an auditable account of bounded rescue work."""

    decisions: tuple[NativeTradeoffDecision, NativeTradeoffDecision]
    primary_decisions: tuple[NativeTradeoffDecision, NativeTradeoffDecision]
    rescue_receiver: int | None
    rescue_acquisition_count: int
    rescue_candidate_count: int
    rescue_candidate_score_count: int
    rescue_seed_guided_count: int
    rescue_confirmation_guided_count: int
    rescue_events: tuple[RescueEvent, ...]

    def decision(self, receiver: int) -> NativeTradeoffDecision:
        if type(receiver) is not int or receiver not in (0, 1):
            raise ValueError("receiver must be zero or one")
        return self.decisions[receiver]

    @property
    def primary_scoring_count(self) -> int:
        return sum(item.scoring_count for item in self.primary_decisions)

    @property
    def total_scoring_count(self) -> int:
        """Primary native + Python point scores + rescue native point scores."""

        return (
            self.primary_scoring_count
            + self.rescue_candidate_score_count
            + self.rescue_seed_guided_count
            + self.rescue_confirmation_guided_count
        )


class SameRxRescueDetector:
    """Visit-level controller around one unchanged two-key native controller.

    ``primary`` and ``guarded_engine`` must refer to the same engine object so
    primary and rescue measurements share one pinned scientific build.  Rescue
    does not modify, establish, or clear primary tracking state.
    """

    def __init__(
        self,
        primary: NativeTradeoffDetector,
        guarded_engine: Any,
        *,
        acquisition: Callable[..., Any] = acquire_symbolwise,
        scorer: Callable[..., Any] = conditioned_glrt64_score,
    ) -> None:
        if (
            not isinstance(primary, NativeTradeoffDetector)
            or guarded_engine is None
            or primary.engine is not guarded_engine
            or not callable(acquisition)
            or not callable(scorer)
        ):
            raise ValueError("rescue requires one primary detector and its guarded engine")
        self.primary = primary
        self.guarded_engine = guarded_engine
        self.acquisition = acquisition
        self.scorer = scorer

    def clear(self) -> None:
        self.primary.clear()

    def snapshot(self) -> Any:
        return self.primary.snapshot()

    def restore(self, snapshot: Any) -> None:
        self.primary.restore(snapshot)

    @staticmethod
    def _validate_keys(keys: tuple[CacheKey, CacheKey]) -> tuple[CacheKey, CacheKey]:
        if not isinstance(keys, tuple) or len(keys) != 2:
            raise ValueError("rescue requires an RX0/RX1 key tuple")
        first, second = keys
        if not isinstance(first, CacheKey) or not isinstance(second, CacheKey):
            raise ValueError("rescue keys must be CacheKey values")
        if (first.receiver, second.receiver) != (0, 1):
            raise ValueError("rescue keys must be ordered RX0 then RX1")
        comparable = (
            "continuity_epoch", "channel", "edge", "rate_hz",
            "tuning_identity",
        )
        if any(getattr(first, name) != getattr(second, name) for name in comparable):
            raise ValueError("rescue receiver keys must describe the same physical visit")
        return first, second

    @staticmethod
    def _validate_raw(raw: Any, rate_hz: int) -> np.ndarray:
        values = np.asarray(raw)
        expected = (rate_hz * 120 // 1_000, 2, 2)
        if (
            values.dtype != np.dtype("int16")
            or values.shape != expected
            or not values.flags.c_contiguous
        ):
            raise ValueError("complete C-contiguous natural dual-RX CI16 dwell required")
        return values

    @staticmethod
    def _probe_start(rate_hz: int, probe_index: int) -> int:
        return probe_index * rate_hz * PROBE_STRIDE_MS // 1_000

    @classmethod
    def _transport_epoch(
        cls,
        rate_hz: int,
        epoch_sample: float,
        from_probe: int,
        to_probe: int,
    ) -> float:
        """Transport a local 750 Hz frame phase without a float source counter."""

        if not _finite(epoch_sample):
            raise ValueError("finite local epoch required")
        source_local = epoch_sample + cls._probe_start(rate_hz, from_probe)
        destination_start = cls._probe_start(rate_hz, to_probe)
        return (((source_local - destination_start) * FRAME_RATE_HZ) % rate_hz) / FRAME_RATE_HZ

    @classmethod
    def _map_native(
        cls,
        key: CacheKey,
        start_counter: int,
        observation: Any,
        *,
        expected_probe: int,
    ) -> NativeEvidence:
        receiver = getattr(observation, "receiver", None)
        probe_index = getattr(observation, "probe_index", None)
        if (
            receiver != key.receiver
            or type(probe_index) is not int
            or probe_index != expected_probe
            or not 0 <= probe_index < 11
        ):
            raise ValueError("native rescue observation identity disagrees with key")
        expected_start = cls._probe_start(key.rate_hz, probe_index)
        if getattr(observation, "probe_start_sample", None) != expected_start:
            raise ValueError("native rescue observation has invalid probe geometry")
        fields = (
            "local_epoch_sample", "acquired_cfo_hz", "tracking_cfo_hz",
            "margin", "exact_score", "control_score",
        )
        if not all(_finite(getattr(observation, name, None)) for name in fields):
            raise ValueError("native rescue observation contains non-finite evidence")
        local = float(observation.local_epoch_sample)
        period = key.rate_hz / FRAME_RATE_HZ
        if not 0 <= local < period:
            raise ValueError("native rescue observation epoch is not normalized")
        dwell = expected_start + local
        reported = getattr(observation, "dwell_epoch_sample", dwell)
        if not _finite(reported) or abs(float(reported) - dwell) > 1e-9:
            raise ValueError("native rescue dwell coordinate is inconsistent")
        status = getattr(observation, "status", None)
        support = getattr(observation, "support_frames", None)
        candidate_index = getattr(observation, "candidate_index", None)
        flags = tuple(
            getattr(observation, name, None)
            for name in ("fractional_complete", "supported", "fitted", "valid_bounds")
        )
        if (
            type(status) is not int
            or type(support) is not int
            or not 0 <= support <= 16
            or type(candidate_index) is not int
            or candidate_index < 0
            or any(type(value) is not bool for value in flags)
        ):
            raise ValueError("native rescue observation has invalid discrete evidence")
        whole = math.floor(local)
        return NativeEvidence(
            receiver=key.receiver,
            probe_index=probe_index,
            probe_start_sample=expected_start,
            local_epoch_sample=local,
            dwell_epoch_sample=dwell,
            source_epoch_counter=start_counter + expected_start + whole,
            source_epoch_fraction=local - whole,
            acquired_cfo_hz=float(observation.acquired_cfo_hz),
            tracking_cfo_hz=float(observation.tracking_cfo_hz),
            margin=float(observation.margin),
            exact_score=float(observation.exact_score),
            control_score=float(observation.control_score),
            support_frames=support,
            fractional_complete=bool(getattr(observation, "fractional_complete", False)),
            supported=bool(getattr(observation, "supported", False)),
            fitted=bool(getattr(observation, "fitted", False)),
            valid_bounds=bool(getattr(observation, "valid_bounds", False)),
            status=status,
            candidate_index=candidate_index,
        )

    @staticmethod
    def _identity(first: NativeEvidence, second: NativeEvidence, rate_hz: int) -> bool:
        timing_error = abs(
            circular_samples(second.local_epoch_sample - first.local_epoch_sample, rate_hz)
        ) / rate_hz
        return (
            first.receiver == second.receiver
            and first.probe_index == PROBE_ZERO
            and second.probe_index == CONFIRMATION_PROBE
            and second.probe_start_sample - first.probe_start_sample
            == rate_hz * 20 // 1_000
            and first.positive
            and second.positive
            and timing_error <= TIMING_GATE_SECONDS
            and abs(second.tracking_cfo_hz - first.tracking_cfo_hz) <= CFO_GATE_HZ
        )

    @staticmethod
    def _python_score_fields(score: Any) -> tuple[float, float, float, float]:
        control = getattr(score, "control_score", None)
        values = (
            getattr(score, "exact_score", None), control,
            getattr(score, "margin", None), getattr(score, "tracking_cfo_hz", None),
        )
        if not all(_finite(value) for value in values):
            raise ValueError("Python conditioned score contains non-finite evidence")
        return tuple(float(value) for value in values)  # type: ignore[return-value]

    def _rescue(
        self,
        raw: np.ndarray,
        key: CacheKey,
        *,
        start_counter: int,
    ) -> tuple[NativePair | None, tuple[RescueEvent, ...], int, int, int, int]:
        rate_hz = key.rate_hz
        stop = rate_hz // 50
        selected = raw[:stop, key.receiver]
        probe = np.empty(stop, dtype=np.complex128)
        probe.real = selected[:, 0]
        probe.imag = selected[:, 1]
        calibration = ReceiverFrequencyCalibration(
            receiver_id=str(key.receiver),
            center_hz=0.0,
            calibration_sha256=ZERO_CALIBRATION_SHA256,
        )
        config = SymbolwiseAcquisitionConfig(
            maximum_probe_samples=stop,
            retained_candidate_count=MAXIMUM_CANDIDATES,
            candidate_epoch_separation_samples=5,
            candidate_cfo_separation_hz=10_000.0,
        )
        acquired = self.acquisition(
            probe,
            rate_hz,
            calibration,
            edge=key.edge,
            config=config,
        )
        candidates = tuple(getattr(acquired, "candidates", ()))
        if len(candidates) > MAXIMUM_CANDIDATES:
            raise ValueError("Python acquisition exceeded the frozen candidate budget")
        if any(getattr(item, "rank", None) != index for index, item in enumerate(candidates)):
            raise ValueError("Python acquisition candidates are not in rank order")

        events: list[RescueEvent] = []
        seed_calls = 0
        confirmation_calls = 0
        score_calls = 0
        period = rate_hz / FRAME_RATE_HZ
        for candidate in candidates:
            epoch = getattr(candidate, "refined_epoch_sample", None)
            scoring_cfo = getattr(candidate, "absolute_cfo_hz", None)
            if (
                type(epoch) is not int
                or not 0 <= epoch < period
                or not _finite(scoring_cfo)
            ):
                raise ValueError("Python acquisition returned an invalid candidate")
            score = self.scorer(
                probe,
                rate_hz,
                epoch_sample=epoch,
                acquired_cfo_hz=float(scoring_cfo),
                edge=key.edge,
            )
            score_calls += 1
            exact, control, margin, physical_cfo = self._python_score_fields(score)
            base = dict(
                receiver=key.receiver,
                candidate_rank=candidate.rank,
                python_epoch_sample=epoch,
                python_scoring_cfo_hz=float(scoring_cfo),
                python_tracking_cfo_hz=physical_cfo,
                python_exact_score=exact,
                python_control_score=control,
                python_margin=margin,
            )
            if margin < MARGIN_GATE:
                events.append(RescueEvent(**base, seed=None, confirmation=None,
                                          accepted=False, reason="python_margin_failed"))
                continue

            seed_calls += 1
            native_seed = self.guarded_engine.guided(
                raw,
                receiver=key.receiver,
                probe_index=PROBE_ZERO,
                predicted_local_epoch_sample=float(epoch),
                scoring_cfo_hz=float(scoring_cfo),
                expected_physical_cfo_hz=physical_cfo,
            )
            if native_seed is None:
                events.append(RescueEvent(**base, seed=None, confirmation=None,
                                          accepted=False, reason="native_seed_unavailable"))
                continue
            seed = self._map_native(
                key, start_counter, native_seed, expected_probe=PROBE_ZERO
            )
            python_timing_error = abs(
                circular_samples(seed.local_epoch_sample - epoch, rate_hz)
            ) / rate_hz
            if (
                not seed.positive
                or python_timing_error > TIMING_GATE_SECONDS
                or seed.acquired_cfo_hz != float(scoring_cfo)
                or abs(seed.tracking_cfo_hz - physical_cfo) > CFO_GATE_HZ
            ):
                events.append(RescueEvent(**base, seed=seed, confirmation=None,
                                          accepted=False, reason="native_seed_failed"))
                continue

            confirmation_calls += 1
            confirmation_epoch = self._transport_epoch(
                rate_hz,
                float(epoch),
                PROBE_ZERO,
                CONFIRMATION_PROBE,
            )
            native_confirmation = self.guarded_engine.guided(
                raw,
                receiver=key.receiver,
                probe_index=CONFIRMATION_PROBE,
                predicted_local_epoch_sample=confirmation_epoch,
                scoring_cfo_hz=float(scoring_cfo),
                expected_physical_cfo_hz=physical_cfo,
            )
            if native_confirmation is None:
                events.append(RescueEvent(**base, seed=seed, confirmation=None,
                                          accepted=False, reason="native_confirmation_unavailable"))
                continue
            confirmation = self._map_native(
                key,
                start_counter,
                native_confirmation,
                expected_probe=CONFIRMATION_PROBE,
            )
            confirmation_timing_error = abs(
                circular_samples(
                    confirmation.local_epoch_sample - confirmation_epoch,
                    rate_hz,
                )
            ) / rate_hz
            if (
                confirmation_timing_error > TIMING_GATE_SECONDS
                or confirmation.acquired_cfo_hz != float(scoring_cfo)
                or abs(confirmation.tracking_cfo_hz - physical_cfo) > CFO_GATE_HZ
                or not self._identity(seed, confirmation, rate_hz)
            ):
                events.append(RescueEvent(**base, seed=seed, confirmation=confirmation,
                                          accepted=False, reason="native_pair_failed"))
                continue
            pair = NativePair(key.receiver, seed, confirmation)
            events.append(RescueEvent(**base, seed=seed, confirmation=confirmation,
                                      accepted=True, reason="accepted"))
            return pair, tuple(events), len(candidates), score_calls, seed_calls, confirmation_calls

        return None, tuple(events), len(candidates), score_calls, seed_calls, confirmation_calls

    def process(
        self,
        raw: Any,
        keys: tuple[CacheKey, CacheKey],
        *,
        start_counter: int,
        visit_index: int,
        force_discovery: bool = False,
    ) -> RescueVisitDecision:
        """Process one dual-RX visit and advance primary state exactly once per RX."""

        first_key, second_key = self._validate_keys(keys)
        values = self._validate_raw(raw, first_key.rate_hz)
        snapshot = self.primary.snapshot()
        try:
            primary = (
                self.primary.process(
                    values, first_key, start_counter=start_counter,
                    visit_index=visit_index, force_discovery=force_discovery,
                ),
                self.primary.process(
                    values, second_key, start_counter=start_counter,
                    visit_index=visit_index, force_discovery=force_discovery,
                ),
            )
            inactive = tuple(
                index for index, decision in enumerate(primary) if not decision.active
            )
            if not inactive:
                return RescueVisitDecision(primary, primary, None, 0, 0, 0, 0, 0, ())

            receiver = inactive[0]
            key = keys[receiver]
            pair, events, count, scored, seeded, confirmed = self._rescue(
                values, key, start_counter=start_counter
            )
            decisions = list(primary)
            if pair is not None:
                original = primary[receiver]
                decisions[receiver] = NativeTradeoffDecision(
                    active=True,
                    route="rescue_probe0_probe2",
                    reason=(
                        "Python proposal passed guarded native "
                        "probe-zero/probe-two confirmation"
                    ),
                    pair=pair,
                    screened_probe_count=original.screened_probe_count,
                    guided_probe_count=original.guided_probe_count,
                    blind_probe_count=original.blind_probe_count,
                    proposal_count=original.proposal_count,
                    scoring_count=original.scoring_count,
                    state_established=False,
                )
            return RescueVisitDecision(
                decisions=tuple(decisions),  # type: ignore[arg-type]
                primary_decisions=primary,
                rescue_receiver=receiver,
                rescue_acquisition_count=1,
                rescue_candidate_count=count,
                rescue_candidate_score_count=scored,
                rescue_seed_guided_count=seeded,
                rescue_confirmation_guided_count=confirmed,
                rescue_events=events,
            )
        except Exception:
            # A visit is one causal transaction across both receiver keys.  An
            # integrity failure must not leave only RX0 advanced before retry.
            self.primary.restore(snapshot)
            raise


__all__ = [
    "CONFIRMATION_PROBE",
    "MAXIMUM_CANDIDATES",
    "RescueEvent",
    "RescueVisitDecision",
    "SameRxRescueDetector",
    "TIMING_GATE_SECONDS",
]
