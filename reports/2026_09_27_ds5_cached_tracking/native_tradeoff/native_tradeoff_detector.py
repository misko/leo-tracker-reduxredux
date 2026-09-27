"""Causal native TG11 tracking without a rank-epoch cache gate.

Cold, expired, forced, and failed-guided visits use the unchanged TG11 screen
and all-eleven-probe blind detector.  A cache hit evaluates exactly the two
probe indices selected by the last accepted blind pair.  The guided native
scores are fresh full-aperture evidence, but their input timing is a point
hypothesis, so guided observations never train timing or CFO slopes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
import sys
from typing import Any, Protocol


HERE = Path(__file__).resolve().parent
TG11 = HERE.parent / "tg11"
if str(TG11) not in sys.path:
    sys.path.insert(0, str(TG11))

from decision import CacheKey, circular_samples  # noqa: E402


FRAME_RATE_HZ = 750
PROBE_COUNT = 11
PROBE_MS = 20
PROBE_STRIDE_MS = 10
MARGIN_GATE = 0.025
CFO_GATE_HZ = 8_000.0
TIMING_INNOVATION_SECONDS = 4e-6


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


class NativeObservation(Protocol):
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: float
    acquired_cfo_hz: float
    tracking_cfo_hz: float
    margin: float
    fractional_complete: bool
    supported: bool
    fitted: bool
    candidate_index: int
    exact_score: float
    control_score: float
    support_frames: int
    valid_bounds: bool
    status: int


class NativeEngine(Protocol):
    def screen(self, raw: Any, *, receiver: int) -> Any: ...

    def blind(
        self, raw: Any, *, receiver: int, screen: Any
    ) -> tuple[NativeObservation, ...]: ...

    def guided(
        self,
        raw: Any,
        *,
        receiver: int,
        probe_index: int,
        predicted_local_epoch_sample: float,
        scoring_cfo_hz: float,
        expected_physical_cfo_hz: float,
    ) -> NativeObservation | None: ...


@dataclass(frozen=True, slots=True)
class NativeEvidence:
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: float
    dwell_epoch_sample: float
    source_epoch_counter: int
    source_epoch_fraction: float
    acquired_cfo_hz: float
    tracking_cfo_hz: float
    margin: float
    exact_score: float
    control_score: float
    support_frames: int
    fractional_complete: bool
    supported: bool
    fitted: bool
    valid_bounds: bool
    status: int
    candidate_index: int

    @property
    def positive(self) -> bool:
        return (
            self.status == 0
            and self.supported
            and self.valid_bounds
            and self.support_frames >= 2
            and self.fractional_complete
            and self.margin >= MARGIN_GATE
        )


@dataclass(frozen=True, slots=True)
class NativePair:
    receiver: int
    first: NativeEvidence
    second: NativeEvidence


@dataclass(frozen=True, slots=True)
class FittedAnchor:
    probe_index: int
    source_epoch_counter: int
    source_epoch_fraction: float


@dataclass(frozen=True, slots=True)
class NativeTrackState:
    anchors: tuple[FittedAnchor, FittedAnchor]
    timing_rate_samples_per_s: float
    cfo_rate_hz_per_s: float
    scoring_cfo_hz: float
    physical_cfo_hz: float
    cfo_measurement_counter: int
    cfo_measurement_fraction: float
    blind_physical_cfo_hz: float
    blind_cfo_counter: int
    blind_cfo_fraction: float
    last_seen_counter: int
    last_visit_index: int
    guided_accepts_since_discovery: int


@dataclass(frozen=True, slots=True)
class NativePrediction:
    probe_index: int
    local_epoch_sample: float
    scoring_cfo_hz: float
    physical_cfo_hz: float


@dataclass(frozen=True, slots=True)
class NativeTradeoffDecision:
    active: bool
    route: str
    reason: str
    pair: NativePair | None
    screened_probe_count: int
    guided_probe_count: int
    blind_probe_count: int
    proposal_count: int
    scoring_count: int
    state_established: bool


@dataclass(frozen=True, slots=True)
class NativeTradeoffSnapshot:
    states: tuple[tuple[CacheKey, NativeTrackState], ...]
    last_inputs: tuple[tuple[CacheKey, tuple[int, int]], ...]


class NativeTradeoffDetector:
    """One-receiver causal controller bound to a stateless native engine."""

    def __init__(
        self,
        engine: NativeEngine,
        *,
        expiry_seconds: float = 2.0,
        guided_accept_limit: int = 31,
        maximum_clock_error_ppm: float = 50.0,
        maximum_cfo_rate_hz_per_s: float = 5_000.0,
        timing_innovation_seconds: float = TIMING_INNOVATION_SECONDS,
        cfo_innovation_hz: float = CFO_GATE_HZ,
    ) -> None:
        values = (
            expiry_seconds,
            maximum_clock_error_ppm,
            maximum_cfo_rate_hz_per_s,
            timing_innovation_seconds,
            cfo_innovation_hz,
        )
        if (
            engine is None
            or not all(_finite(value) and value >= 0 for value in values)
            or expiry_seconds <= 0
            or type(guided_accept_limit) is not int
            or guided_accept_limit < 1
        ):
            raise ValueError("invalid native tradeoff detector policy")
        self.engine = engine
        self.expiry_seconds = float(expiry_seconds)
        self.guided_accept_limit = guided_accept_limit
        self.maximum_clock_error_ppm = float(maximum_clock_error_ppm)
        self.maximum_cfo_rate_hz_per_s = float(maximum_cfo_rate_hz_per_s)
        self.timing_innovation_seconds = float(timing_innovation_seconds)
        self.cfo_innovation_hz = float(cfo_innovation_hz)
        self.states: dict[CacheKey, NativeTrackState] = {}
        self.last_inputs: dict[CacheKey, tuple[int, int]] = {}

    def clear(self) -> None:
        self.states.clear()
        self.last_inputs.clear()

    def snapshot(self) -> NativeTradeoffSnapshot:
        return NativeTradeoffSnapshot(
            tuple(self.states.items()), tuple(self.last_inputs.items())
        )

    def restore(self, snapshot: NativeTradeoffSnapshot) -> None:
        if not isinstance(snapshot, NativeTradeoffSnapshot):
            raise ValueError("invalid native tradeoff snapshot")
        self.states = dict(snapshot.states)
        self.last_inputs = dict(snapshot.last_inputs)

    @staticmethod
    def _probe_start(rate_hz: int, probe_index: int) -> int:
        return probe_index * rate_hz * PROBE_STRIDE_MS // 1_000

    def _register(self, key: CacheKey, start_counter: int, visit_index: int) -> None:
        if type(start_counter) is not int or type(visit_index) is not int or visit_index < 0:
            raise ValueError("invalid native tradeoff visit coordinate")
        previous = self.last_inputs.get(key)
        if previous is not None and (
            start_counter <= previous[0] or visit_index <= previous[1]
        ):
            raise ValueError("native tradeoff visits must advance causally within a key")
        self.last_inputs[key] = start_counter, visit_index

    def _validate_screen(self, key: CacheKey, screen: Any) -> int:
        windows = tuple(getattr(screen, "windows", ()))
        if len(windows) != PROBE_COUNT:
            raise ValueError("native blind screen must contain all eleven probes")
        for index, window in enumerate(windows):
            if (
                getattr(window, "probe_index", None) != index
                or getattr(window, "probe_start_sample", None)
                != self._probe_start(key.rate_hz, index)
            ):
                raise ValueError("native blind screen has invalid probe geometry")
        receiver = getattr(screen, "receiver", key.receiver)
        if receiver != key.receiver:
            raise ValueError("native blind screen receiver disagrees with key")
        return len(windows)

    def _map(
        self,
        key: CacheKey,
        start_counter: int,
        observation: NativeObservation,
    ) -> NativeEvidence:
        if (
            getattr(observation, "receiver", None) != key.receiver
            or type(getattr(observation, "probe_index", None)) is not int
            or not 0 <= observation.probe_index < PROBE_COUNT
        ):
            raise ValueError("native observation identity disagrees with key")
        expected_start = self._probe_start(key.rate_hz, observation.probe_index)
        if getattr(observation, "probe_start_sample", None) != expected_start:
            raise ValueError("native observation has invalid probe geometry")
        numeric = (
            observation.local_epoch_sample,
            observation.acquired_cfo_hz,
            observation.tracking_cfo_hz,
            observation.margin,
            getattr(observation, "exact_score", 0.0),
            getattr(observation, "control_score", 0.0),
        )
        if not all(_finite(value) for value in numeric):
            raise ValueError("native observation contains non-finite evidence")
        status = getattr(observation, "status", 0)
        support_frames = getattr(observation, "support_frames", 0)
        candidate_index = getattr(observation, "candidate_index", 0)
        if (
            type(status) is not int
            or type(support_frames) is not int
            or support_frames < 0
            or type(candidate_index) is not int
            or candidate_index < 0
        ):
            raise ValueError("native observation has invalid discrete evidence")
        local = float(observation.local_epoch_sample)
        period = key.rate_hz / FRAME_RATE_HZ
        if not 0 <= local < period:
            raise ValueError("native observation epoch is not normalized")
        dwell = expected_start + local
        reported_dwell = getattr(observation, "dwell_epoch_sample", dwell)
        if not _finite(reported_dwell) or abs(float(reported_dwell) - dwell) > 1e-9:
            raise ValueError("native observation dwell coordinate is inconsistent")
        whole = math.floor(local)
        fraction = local - whole
        return NativeEvidence(
            receiver=key.receiver,
            probe_index=observation.probe_index,
            probe_start_sample=expected_start,
            local_epoch_sample=local,
            dwell_epoch_sample=dwell,
            source_epoch_counter=start_counter + expected_start + whole,
            source_epoch_fraction=fraction,
            acquired_cfo_hz=float(observation.acquired_cfo_hz),
            tracking_cfo_hz=float(observation.tracking_cfo_hz),
            margin=float(observation.margin),
            exact_score=float(getattr(observation, "exact_score", 0.0)),
            control_score=float(getattr(observation, "control_score", 0.0)),
            support_frames=support_frames,
            fractional_complete=bool(observation.fractional_complete),
            supported=bool(observation.supported),
            fitted=bool(observation.fitted),
            valid_bounds=bool(getattr(observation, "valid_bounds", True)),
            status=status,
            candidate_index=candidate_index,
        )

    @staticmethod
    def _pair(
        observations: tuple[NativeEvidence, ...], rate_hz: int
    ) -> NativePair | None:
        by_probe: dict[int, list[NativeEvidence]] = {}
        for observation in observations:
            if observation.positive:
                by_probe.setdefault(observation.probe_index, []).append(observation)
        history: list[NativeEvidence] = []
        separation = rate_hz * PROBE_MS // 1_000
        for probe_index in sorted(by_probe):
            current = sorted(
                by_probe[probe_index],
                key=lambda item: (
                    -item.margin,
                    item.candidate_index,
                    item.local_epoch_sample,
                ),
            )
            for observation in current:
                compatible = tuple(
                    prior
                    for prior in history
                    if observation.probe_start_sample - prior.probe_start_sample
                    >= separation
                    and abs(observation.tracking_cfo_hz - prior.tracking_cfo_hz)
                    <= CFO_GATE_HZ
                )
                if compatible:
                    first = min(
                        compatible,
                        key=lambda item: (
                            item.probe_index,
                            -item.margin,
                            item.candidate_index,
                            item.local_epoch_sample,
                        ),
                    )
                    return NativePair(observation.receiver, first, observation)
            history.extend(current)
        return None

    @staticmethod
    def _anchor(observation: NativeEvidence) -> FittedAnchor:
        return FittedAnchor(
            observation.probe_index,
            observation.source_epoch_counter,
            observation.source_epoch_fraction,
        )

    def _establish(
        self,
        key: CacheKey,
        start_counter: int,
        visit_index: int,
        pair: NativePair,
    ) -> bool:
        if not all(item.fitted for item in (pair.first, pair.second)):
            self.states.pop(key, None)
            return False
        anchors = self._anchor(pair.first), self._anchor(pair.second)
        previous = self.states.get(key)
        timing_rate = 0.0
        cfo_rate = 0.0
        if previous is not None:
            old_anchor = previous.anchors[1]
            new_anchor = anchors[1]
            timing_dt = (
                new_anchor.source_epoch_counter
                - old_anchor.source_epoch_counter
                + new_anchor.source_epoch_fraction
                - old_anchor.source_epoch_fraction
            ) / key.rate_hz
            if 0 < timing_dt <= 5.0:
                integer_phase = (
                    (new_anchor.source_epoch_counter - old_anchor.source_epoch_counter)
                    * FRAME_RATE_HZ
                    % key.rate_hz
                ) / FRAME_RATE_HZ
                fractional_phase = (
                    new_anchor.source_epoch_fraction - old_anchor.source_epoch_fraction
                )
                measured_timing_rate = circular_samples(
                    integer_phase + fractional_phase, key.rate_hz
                ) / timing_dt
                timing_bound = self.maximum_clock_error_ppm * 1e-6 * key.rate_hz
                if abs(measured_timing_rate) <= timing_bound:
                    timing_rate = measured_timing_rate

            cfo_dt = (
                pair.second.source_epoch_counter
                - previous.blind_cfo_counter
                + pair.second.source_epoch_fraction
                - previous.blind_cfo_fraction
            ) / key.rate_hz
            if 0 < cfo_dt <= 5.0:
                measured_cfo_rate = (
                    pair.second.tracking_cfo_hz
                    - previous.blind_physical_cfo_hz
                ) / cfo_dt
                if abs(measured_cfo_rate) <= self.maximum_cfo_rate_hz_per_s:
                    cfo_rate = measured_cfo_rate

        self.states[key] = NativeTrackState(
            anchors=anchors,
            timing_rate_samples_per_s=timing_rate,
            cfo_rate_hz_per_s=cfo_rate,
            scoring_cfo_hz=pair.second.acquired_cfo_hz,
            physical_cfo_hz=pair.second.tracking_cfo_hz,
            cfo_measurement_counter=pair.second.source_epoch_counter,
            cfo_measurement_fraction=pair.second.source_epoch_fraction,
            blind_physical_cfo_hz=pair.second.tracking_cfo_hz,
            blind_cfo_counter=pair.second.source_epoch_counter,
            blind_cfo_fraction=pair.second.source_epoch_fraction,
            last_seen_counter=start_counter,
            last_visit_index=visit_index,
            guided_accepts_since_discovery=0,
        )
        return True

    def _prediction(
        self,
        key: CacheKey,
        state: NativeTrackState,
        anchor: FittedAnchor,
        start_counter: int,
    ) -> NativePrediction:
        probe_start = self._probe_start(key.rate_hz, anchor.probe_index)
        period = key.rate_hz / FRAME_RATE_HZ
        base_epoch = (
            (
                (anchor.source_epoch_counter - start_counter - probe_start)
                * FRAME_RATE_HZ
                % key.rate_hz
            )
            / FRAME_RATE_HZ
            + anchor.source_epoch_fraction
        ) % period
        base_whole = math.floor(base_epoch)
        base_fraction = base_epoch - base_whole
        elapsed_anchor = (
            start_counter
            + probe_start
            + base_whole
            - anchor.source_epoch_counter
            + base_fraction
            - anchor.source_epoch_fraction
        ) / key.rate_hz
        local = (
            base_epoch + state.timing_rate_samples_per_s * elapsed_anchor
        ) % period
        local_whole = math.floor(local)
        local_fraction = local - local_whole
        measurement_elapsed = (
            start_counter
            + probe_start
            + local_whole
            - state.cfo_measurement_counter
            + local_fraction
            - state.cfo_measurement_fraction
        ) / key.rate_hz
        delta = state.cfo_rate_hz_per_s * measurement_elapsed
        return NativePrediction(
            probe_index=anchor.probe_index,
            local_epoch_sample=local,
            scoring_cfo_hz=state.scoring_cfo_hz + delta,
            physical_cfo_hz=state.physical_cfo_hz + delta,
        )

    def _blind(
        self,
        raw: Any,
        key: CacheKey,
        start_counter: int,
        visit_index: int,
        reason: str,
        guided_attempts: int,
    ) -> NativeTradeoffDecision:
        screen = self.engine.screen(raw, receiver=key.receiver)
        screened = self._validate_screen(key, screen)
        observations = tuple(
            self._map(key, start_counter, item)
            for item in self.engine.blind(raw, receiver=key.receiver, screen=screen)
        )
        pair = self._pair(observations, key.rate_hz)
        route = f"blind_{reason}"
        scoring_count = guided_attempts + PROBE_COUNT
        if pair is None:
            self.states.pop(key, None)
            return NativeTradeoffDecision(
                False,
                route,
                "all-eleven-probe native blind route found no compatible pair",
                None,
                screened,
                guided_attempts,
                PROBE_COUNT,
                len(observations),
                scoring_count,
                False,
            )
        established = self._establish(key, start_counter, visit_index, pair)
        return NativeTradeoffDecision(
            True,
            route,
            "all-eleven-probe native blind route found a compatible pair",
            pair,
            screened,
            guided_attempts,
            PROBE_COUNT,
            len(observations),
            scoring_count,
            established,
        )

    def _guided_acceptable(
        self,
        key: CacheKey,
        prediction: NativePrediction,
        observation: NativeEvidence,
    ) -> bool:
        timing_error = abs(
            circular_samples(
                observation.local_epoch_sample - prediction.local_epoch_sample,
                key.rate_hz,
            )
        ) / key.rate_hz
        return (
            observation.positive
            and timing_error <= self.timing_innovation_seconds
            and abs(observation.tracking_cfo_hz - prediction.physical_cfo_hz)
            <= self.cfo_innovation_hz
        )

    def process(
        self,
        raw: Any,
        key: CacheKey,
        *,
        start_counter: int,
        visit_index: int,
        force_discovery: bool = False,
    ) -> NativeTradeoffDecision:
        """Measure one receiver visit and advance its causal state exactly once."""

        if type(force_discovery) is not bool:
            raise ValueError("force_discovery must be bool")
        self._register(key, start_counter, visit_index)
        state = self.states.get(key)
        reason = None
        if force_discovery:
            reason = "forced"
        elif state is None:
            reason = "cold"
        elif (start_counter - state.last_seen_counter) / key.rate_hz > self.expiry_seconds:
            reason = "expired"
        elif state.guided_accepts_since_discovery >= self.guided_accept_limit:
            reason = "periodic"
        if reason is not None:
            return self._blind(raw, key, start_counter, visit_index, reason, 0)

        guided: list[NativeEvidence] = []
        for order, anchor in enumerate(state.anchors):
            prediction = self._prediction(key, state, anchor, start_counter)
            if abs(prediction.scoring_cfo_hz) > 400_000:
                return self._blind(
                    raw, key, start_counter, visit_index, "guided_failure", order
                )
            native = self.engine.guided(
                raw,
                receiver=key.receiver,
                probe_index=prediction.probe_index,
                predicted_local_epoch_sample=prediction.local_epoch_sample,
                scoring_cfo_hz=prediction.scoring_cfo_hz,
                expected_physical_cfo_hz=prediction.physical_cfo_hz,
            )
            attempts = order + 1
            if native is None:
                return self._blind(
                    raw, key, start_counter, visit_index, "guided_failure", attempts
                )
            observation = self._map(key, start_counter, native)
            if not self._guided_acceptable(key, prediction, observation):
                return self._blind(
                    raw, key, start_counter, visit_index, "guided_failure", attempts
                )
            guided.append(observation)

        pair = self._pair(tuple(guided), key.rate_hz)
        if pair is None:
            return self._blind(
                raw, key, start_counter, visit_index, "guided_failure", len(guided)
            )

        # The guided timing is the tested point hypothesis.  Preserve blind-fit
        # anchors and both fitted slopes.  Physical CFO is a fresh measurement,
        # so its value and actual observation timestamp may advance.
        self.states[key] = replace(
            state,
            scoring_cfo_hz=pair.second.acquired_cfo_hz,
            physical_cfo_hz=pair.second.tracking_cfo_hz,
            cfo_measurement_counter=pair.second.source_epoch_counter,
            cfo_measurement_fraction=pair.second.source_epoch_fraction,
            last_seen_counter=start_counter,
            last_visit_index=visit_index,
            guided_accepts_since_discovery=state.guided_accepts_since_discovery + 1,
        )
        return NativeTradeoffDecision(
            True,
            "guided",
            "two fresh native full-aperture point confirmations formed a pair",
            pair,
            0,
            len(guided),
            0,
            0,
            len(guided),
            True,
        )


__all__ = [
    "CacheKey",
    "FittedAnchor",
    "NativeEvidence",
    "NativePair",
    "NativePrediction",
    "NativeTrackState",
    "NativeTradeoffDecision",
    "NativeTradeoffDetector",
    "NativeTradeoffSnapshot",
]
