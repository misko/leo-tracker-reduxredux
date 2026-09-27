"""Causal TG11 routing and pair decision, independent of the native engine.

The engine measures IQ.  This module owns causal state, source-coordinate
mapping, guided-versus-blind routing, and the two-probe decision.  It never
receives a comparator result and never treats a rank screen as absence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Protocol


MARGIN_GATE = 0.025
CFO_GATE_HZ = 8_000.0
TIMING_INNOVATION_SECONDS = 4e-6
FRAME_RATE_HZ = 750
PROBE_MS = 20
PROBE_STRIDE_MS = 10
PROBE_COUNT = 11


def _finite(*values: float) -> bool:
    return all(math.isfinite(value) for value in values)


def circular_samples(delta: float, rate_hz: int) -> float:
    period = rate_hz / FRAME_RATE_HZ
    return (delta + period / 2) % period - period / 2


@dataclass(frozen=True, slots=True)
class CacheKey:
    continuity_epoch: str
    receiver: int
    channel: int
    edge: str
    rate_hz: int
    tuning_identity: str
    calibration_identity: str

    def __post_init__(self) -> None:
        if (
            not self.continuity_epoch
            or type(self.receiver) is not int
            or self.receiver < 0
            or type(self.channel) is not int
            or self.channel < 1
            or self.edge not in ("lower", "upper")
            or self.rate_hz not in (2_500_000, 5_000_000)
            or not self.tuning_identity
            or not self.calibration_identity
        ):
            raise ValueError("invalid TG11 cache key")


@dataclass(frozen=True, slots=True)
class ScreenWindow:
    probe_index: int
    probe_start_sample: int
    projected_epoch_sample: float
    score: float

    def __post_init__(self) -> None:
        if (
            type(self.probe_index) is not int
            or not 0 <= self.probe_index < PROBE_COUNT
            or type(self.probe_start_sample) is not int
            or self.probe_start_sample < 0
            or not _finite(self.projected_epoch_sample, self.score)
        ):
            raise ValueError("invalid TG11 screen window")


@dataclass(frozen=True, slots=True)
class ScreenResult:
    windows: tuple[ScreenWindow, ...]


@dataclass(frozen=True, slots=True)
class Observation:
    """Engine observation in one local 20 ms probe coordinate."""

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
    candidate_index: int = 0
    exact_score: float | None = None
    control_score: float | None = None
    support_frames: int | None = None
    valid_support: bool | None = None
    dwell_epoch_sample: float | None = None

    def __post_init__(self) -> None:
        optional = tuple(
            value
            for value in (self.exact_score, self.control_score, self.dwell_epoch_sample)
            if value is not None
        )
        if (
            type(self.receiver) is not int
            or self.receiver < 0
            or type(self.probe_index) is not int
            or not 0 <= self.probe_index < PROBE_COUNT
            or type(self.probe_start_sample) is not int
            or self.probe_start_sample < 0
            or type(self.candidate_index) is not int
            or self.candidate_index < 0
            or self.support_frames is not None
            and (type(self.support_frames) is not int or self.support_frames < 0)
            or not _finite(
                self.local_epoch_sample,
                self.acquired_cfo_hz,
                self.tracking_cfo_hz,
                self.margin,
                *optional,
            )
        ):
            raise ValueError("invalid TG11 observation")
        expected = self.probe_start_sample + self.local_epoch_sample
        if self.dwell_epoch_sample is not None and self.dwell_epoch_sample != expected:
            raise ValueError("engine dwell coordinate disagrees with local coordinate")

    @property
    def positive(self) -> bool:
        support = self.supported and self.valid_support is not False
        return support and self.fractional_complete and self.margin >= MARGIN_GATE


@dataclass(frozen=True, slots=True)
class MappedObservation:
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
    fractional_complete: bool
    supported: bool
    fitted: bool

    @property
    def positive(self) -> bool:
        return self.supported and self.fractional_complete and self.margin >= MARGIN_GATE


@dataclass(frozen=True, slots=True)
class DetectionPair:
    receiver: int
    first: MappedObservation
    second: MappedObservation


@dataclass(frozen=True, slots=True)
class DecisionResult:
    active: bool
    route: str
    reason: str
    pair: DetectionPair | None
    screen_windows: int
    guided_attempts: int
    blind_observations: int


@dataclass(frozen=True, slots=True)
class TrackState:
    fitted_source_anchor_counter: int
    fitted_source_anchor_fraction: float
    fitted_physical_cfo_hz: float
    fitted_scoring_cfo_hz: float
    timing_rate_samples_per_s: float
    cfo_rate_hz_per_s: float
    last_observation_counter: int
    last_observation_fraction: float
    last_seen_counter: int
    last_visit_index: int
    physical_cfo_hz: float
    scoring_cfo_hz: float
    guided_accepts_since_discovery: int


@dataclass(frozen=True, slots=True)
class Prediction:
    local_epoch_sample: float
    physical_cfo_hz: float
    scoring_cfo_hz: float


@dataclass(frozen=True, slots=True)
class StateSnapshot:
    states: tuple[tuple[CacheKey, TrackState], ...]
    last_inputs: tuple[tuple[CacheKey, tuple[int, int]], ...]


class Engine(Protocol):
    def screen(self, raw: Any, *, receiver: int) -> ScreenResult: ...

    def guided(
        self,
        raw: Any,
        *,
        receiver: int,
        probe_index: int,
        predicted_local_epoch_sample: float,
        scoring_cfo_hz: float,
        expected_physical_cfo_hz: float,
    ) -> Observation | None: ...

    def blind(
        self,
        raw: Any,
        *,
        receiver: int,
        screen: ScreenResult,
    ) -> tuple[Observation, ...]: ...


class TG11Decision:
    def __init__(
        self,
        *,
        expiry_seconds: float = 2.0,
        guided_accept_limit: int = 31,
        timing_innovation_seconds: float = TIMING_INNOVATION_SECONDS,
        cfo_innovation_hz: float = CFO_GATE_HZ,
        maximum_cfo_rate_hz_per_s: float = 5_000.0,
        maximum_clock_error_ppm: float = 50.0,
    ) -> None:
        values = (
            expiry_seconds,
            timing_innovation_seconds,
            cfo_innovation_hz,
            maximum_cfo_rate_hz_per_s,
            maximum_clock_error_ppm,
        )
        if (
            not all(_finite(value) and value >= 0 for value in values)
            or expiry_seconds <= 0
            or type(guided_accept_limit) is not int
            or guided_accept_limit < 1
        ):
            raise ValueError("invalid TG11 state policy")
        self.expiry_seconds = expiry_seconds
        self.guided_accept_limit = guided_accept_limit
        self.timing_innovation_seconds = timing_innovation_seconds
        self.cfo_innovation_hz = cfo_innovation_hz
        self.maximum_cfo_rate_hz_per_s = maximum_cfo_rate_hz_per_s
        self.maximum_clock_error_ppm = maximum_clock_error_ppm
        self.states: dict[CacheKey, TrackState] = {}
        self.last_inputs: dict[CacheKey, tuple[int, int]] = {}

    @staticmethod
    def _expected_probe_start(rate_hz: int, probe_index: int) -> int:
        return probe_index * rate_hz * PROBE_STRIDE_MS // 1_000

    def _validate_screen(self, key: CacheKey, screen: ScreenResult) -> None:
        expected = tuple(range(PROBE_COUNT))
        observed = tuple(window.probe_index for window in screen.windows)
        if observed != expected:
            raise ValueError("TG11 screen must contain all eleven chronological windows")
        for window in screen.windows:
            if window.probe_start_sample != self._expected_probe_start(
                key.rate_hz, window.probe_index
            ):
                raise ValueError("TG11 screen has an invalid probe start")

    def _register(self, key: CacheKey, start_counter: int, visit_index: int) -> None:
        if type(start_counter) is not int or type(visit_index) is not int or visit_index < 0:
            raise ValueError("invalid TG11 visit coordinate")
        previous = self.last_inputs.get(key)
        if previous is not None and (
            start_counter <= previous[0] or visit_index <= previous[1]
        ):
            raise ValueError("TG11 visits must advance causally within a cache key")
        self.last_inputs[key] = (start_counter, visit_index)

    def _prediction(
        self,
        state: TrackState,
        key: CacheKey,
        start_counter: int,
        probe_start_sample: int,
    ) -> Prediction:
        period = key.rate_hz / FRAME_RATE_HZ
        base_epoch = (
            (
                (state.fitted_source_anchor_counter - start_counter - probe_start_sample)
                * FRAME_RATE_HZ
                % key.rate_hz
            )
            / FRAME_RATE_HZ
            + state.fitted_source_anchor_fraction
        ) % period
        base_whole = math.floor(base_epoch)
        base_fraction = base_epoch - base_whole
        base_counter = start_counter + probe_start_sample + base_whole
        elapsed_fit = (
            base_counter
            - state.fitted_source_anchor_counter
            + base_fraction
            - state.fitted_source_anchor_fraction
        ) / key.rate_hz
        epoch = (
            base_epoch + state.timing_rate_samples_per_s * elapsed_fit
        ) % period
        predicted_whole = math.floor(epoch)
        predicted_fraction = epoch - predicted_whole
        predicted_counter = start_counter + probe_start_sample + predicted_whole
        elapsed_seen = (
            predicted_counter
            - state.last_observation_counter
            + predicted_fraction
            - state.last_observation_fraction
        ) / key.rate_hz
        cfo_delta = state.cfo_rate_hz_per_s * elapsed_seen
        return Prediction(
            epoch,
            state.physical_cfo_hz + cfo_delta,
            state.scoring_cfo_hz + cfo_delta,
        )

    def _map(
        self,
        key: CacheKey,
        start_counter: int,
        observation: Observation,
    ) -> MappedObservation:
        if observation.receiver != key.receiver:
            raise ValueError("TG11 observation receiver disagrees with cache key")
        expected_start = self._expected_probe_start(key.rate_hz, observation.probe_index)
        if observation.probe_start_sample != expected_start:
            raise ValueError("TG11 observation has an invalid probe start")
        whole_epoch = math.floor(observation.local_epoch_sample)
        fraction = observation.local_epoch_sample - whole_epoch
        return MappedObservation(
            receiver=observation.receiver,
            probe_index=observation.probe_index,
            probe_start_sample=observation.probe_start_sample,
            local_epoch_sample=observation.local_epoch_sample,
            dwell_epoch_sample=(
                observation.probe_start_sample + observation.local_epoch_sample
            ),
            source_epoch_counter=(
                start_counter + observation.probe_start_sample + whole_epoch
            ),
            source_epoch_fraction=fraction,
            acquired_cfo_hz=observation.acquired_cfo_hz,
            tracking_cfo_hz=observation.tracking_cfo_hz,
            margin=observation.margin,
            fractional_complete=observation.fractional_complete,
            supported=(
                observation.supported
                and getattr(observation, "valid_support", None) is not False
            ),
            fitted=observation.fitted,
        )

    @staticmethod
    def _pair(observations: tuple[MappedObservation, ...], rate_hz: int) -> DetectionPair | None:
        history: list[MappedObservation] = []
        by_probe: dict[int, list[tuple[int, MappedObservation]]] = {}
        for order, observation in enumerate(observations):
            if observation.positive:
                by_probe.setdefault(observation.probe_index, []).append((order, observation))
        minimum_separation = rate_hz * PROBE_MS // 1_000
        for probe_index in sorted(by_probe):
            current = sorted(
                by_probe[probe_index],
                key=lambda item: (-item[1].margin, item[0]),
            )
            for _, observation in current:
                compatible = tuple(
                    prior
                    for prior in history
                    if observation.probe_start_sample - prior.probe_start_sample
                    >= minimum_separation
                    and abs(observation.tracking_cfo_hz - prior.tracking_cfo_hz)
                    <= CFO_GATE_HZ
                )
                if compatible:
                    first = min(
                        compatible,
                        key=lambda item: (item.probe_index, -item.margin),
                    )
                    return DetectionPair(observation.receiver, first, observation)
            history.extend(item[1] for item in current)
        return None

    def _fit_blind(
        self,
        key: CacheKey,
        start_counter: int,
        visit_index: int,
        pair: DetectionPair,
    ) -> None:
        observation = pair.second
        if not observation.fitted:
            raise ValueError("blind TG11 pair must contain fitted observations")
        previous = self.states.get(key)
        timing_rate = 0.0
        cfo_rate = 0.0
        if previous is not None:
            dt = (
                observation.source_epoch_counter
                - previous.fitted_source_anchor_counter
                + observation.source_epoch_fraction
                - previous.fitted_source_anchor_fraction
            ) / key.rate_hz
            if 0 < dt <= 5.0:
                whole_delta = (
                    observation.source_epoch_counter
                    - previous.fitted_source_anchor_counter
                )
                integer_phase = (
                    whole_delta * FRAME_RATE_HZ % key.rate_hz
                ) / FRAME_RATE_HZ
                fractional_phase = (
                    observation.source_epoch_fraction
                    - previous.fitted_source_anchor_fraction
                )
                timing_rate = circular_samples(
                    integer_phase + fractional_phase, key.rate_hz
                ) / dt
                clock_bound = self.maximum_clock_error_ppm * 1e-6 * key.rate_hz
                if abs(timing_rate) > clock_bound:
                    timing_rate = previous.timing_rate_samples_per_s
                measured_cfo_rate = (
                    observation.tracking_cfo_hz - previous.fitted_physical_cfo_hz
                ) / dt
                cfo_rate = (
                    measured_cfo_rate
                    if abs(measured_cfo_rate) <= self.maximum_cfo_rate_hz_per_s
                    else previous.cfo_rate_hz_per_s
                )
        self.states[key] = TrackState(
            fitted_source_anchor_counter=observation.source_epoch_counter,
            fitted_source_anchor_fraction=observation.source_epoch_fraction,
            fitted_physical_cfo_hz=observation.tracking_cfo_hz,
            fitted_scoring_cfo_hz=observation.acquired_cfo_hz,
            timing_rate_samples_per_s=timing_rate,
            cfo_rate_hz_per_s=cfo_rate,
            last_observation_counter=observation.source_epoch_counter,
            last_observation_fraction=observation.source_epoch_fraction,
            last_seen_counter=start_counter,
            last_visit_index=visit_index,
            physical_cfo_hz=observation.tracking_cfo_hz,
            scoring_cfo_hz=observation.acquired_cfo_hz,
            guided_accepts_since_discovery=0,
        )

    def _accept_guided(
        self,
        key: CacheKey,
        start_counter: int,
        visit_index: int,
        pair: DetectionPair,
    ) -> None:
        state = self.states[key]
        observation = pair.second
        self.states[key] = replace(
            state,
            last_observation_counter=observation.source_epoch_counter,
            last_observation_fraction=observation.source_epoch_fraction,
            last_seen_counter=start_counter,
            last_visit_index=visit_index,
            physical_cfo_hz=observation.tracking_cfo_hz,
            scoring_cfo_hz=observation.acquired_cfo_hz,
            guided_accepts_since_discovery=state.guided_accepts_since_discovery + 1,
        )

    def _blind(
        self,
        engine: Engine,
        raw: Any,
        key: CacheKey,
        screen: ScreenResult,
        start_counter: int,
        visit_index: int,
        route_reason: str,
        guided_attempts: int,
    ) -> DecisionResult:
        observations = tuple(engine.blind(raw, receiver=key.receiver, screen=screen))
        mapped = tuple(self._map(key, start_counter, item) for item in observations)
        pair = self._pair(mapped, key.rate_hz)
        route = f"blind_{route_reason}"
        if pair is None:
            return DecisionResult(
                False,
                route,
                "fresh eleven-window blind route found no compatible positive pair",
                None,
                len(screen.windows),
                guided_attempts,
                len(mapped),
            )
        if not pair.first.fitted or not pair.second.fitted:
            raise ValueError("blind TG11 engine returned a non-fitted accepted pair")
        self._fit_blind(key, start_counter, visit_index, pair)
        return DecisionResult(
            True,
            route,
            "fresh eleven-window blind route found a compatible positive pair",
            pair,
            len(screen.windows),
            guided_attempts,
            len(mapped),
        )

    def process(
        self,
        engine: Engine,
        raw: Any,
        key: CacheKey,
        *,
        start_counter: int,
        visit_index: int,
    ) -> DecisionResult:
        """Measure one receiver visit and advance causal state exactly once."""

        self._register(key, start_counter, visit_index)
        screen = engine.screen(raw, receiver=key.receiver)
        self._validate_screen(key, screen)
        state = self.states.get(key)
        if state is None:
            return self._blind(
                engine, raw, key, screen, start_counter, visit_index, "cold", 0
            )
        age = (start_counter - state.last_seen_counter) / key.rate_hz
        if age > self.expiry_seconds:
            return self._blind(
                engine, raw, key, screen, start_counter, visit_index, "expired", 0
            )
        if state.guided_accepts_since_discovery >= self.guided_accept_limit:
            return self._blind(
                engine,
                raw,
                key,
                screen,
                start_counter,
                visit_index,
                "periodic_discovery",
                0,
            )

        eligible: list[tuple[ScreenWindow, Prediction]] = []
        for window in screen.windows:
            prediction = self._prediction(
                state, key, start_counter, window.probe_start_sample
            )
            timing_error = abs(
                circular_samples(
                    window.projected_epoch_sample - prediction.local_epoch_sample,
                    key.rate_hz,
                )
            ) / key.rate_hz
            if timing_error <= self.timing_innovation_seconds:
                eligible.append((window, prediction))
        minimum_separation = key.rate_hz * PROBE_MS // 1_000
        have_nonoverlap = any(
            later.probe_start_sample - earlier.probe_start_sample >= minimum_separation
            for index, (earlier, _) in enumerate(eligible)
            for later, _ in eligible[index + 1 :]
        )
        if not have_nonoverlap:
            return self._blind(
                engine,
                raw,
                key,
                screen,
                start_counter,
                visit_index,
                "screen_disagreement",
                0,
            )

        guided: list[MappedObservation] = []
        attempts = 0
        for window, prediction in eligible:
            if abs(prediction.scoring_cfo_hz) > 400_000:
                return self._blind(
                    engine,
                    raw,
                    key,
                    screen,
                    start_counter,
                    visit_index,
                    "cfo_outside_supported_band",
                    attempts,
                )
            attempts += 1
            observation = engine.guided(
                raw,
                receiver=key.receiver,
                probe_index=window.probe_index,
                predicted_local_epoch_sample=prediction.local_epoch_sample,
                scoring_cfo_hz=prediction.scoring_cfo_hz,
                expected_physical_cfo_hz=prediction.physical_cfo_hz,
            )
            if observation is None:
                return self._blind(
                    engine,
                    raw,
                    key,
                    screen,
                    start_counter,
                    visit_index,
                    "guided_failure",
                    attempts,
                )
            mapped = self._map(key, start_counter, observation)
            timing_error = abs(
                circular_samples(
                    mapped.local_epoch_sample - prediction.local_epoch_sample,
                    key.rate_hz,
                )
            ) / key.rate_hz
            if (
                mapped.fitted
                or not mapped.positive
                or timing_error > self.timing_innovation_seconds
                or abs(mapped.tracking_cfo_hz - prediction.physical_cfo_hz)
                > self.cfo_innovation_hz
            ):
                return self._blind(
                    engine,
                    raw,
                    key,
                    screen,
                    start_counter,
                    visit_index,
                    "guided_failure",
                    attempts,
                )
            guided.append(mapped)
            pair = self._pair(tuple(guided), key.rate_hz)
            if pair is not None:
                self._accept_guided(key, start_counter, visit_index, pair)
                return DecisionResult(
                    True,
                    "guided",
                    "two fresh predicted-and-verified probes formed a compatible pair",
                    pair,
                    len(screen.windows),
                    attempts,
                    0,
                )
        return self._blind(
            engine,
            raw,
            key,
            screen,
            start_counter,
            visit_index,
            "guided_no_pair",
            attempts,
        )


class TG11Detector(TG11Decision):
    """Constructor-bound engine adapter used by replay and timing harnesses."""

    def __init__(self, engine: Engine, **policy: Any) -> None:
        if engine is None:
            raise ValueError("TG11 detector requires an engine")
        self.engine = engine
        super().__init__(**policy)

    def process(
        self,
        raw: Any,
        key: CacheKey,
        *,
        start_counter: int,
        visit_index: int,
    ) -> DecisionResult:
        return super().process(
            self.engine,
            raw,
            key,
            start_counter=start_counter,
            visit_index=visit_index,
        )

    def snapshot(self) -> StateSnapshot:
        """Copy causal bookkeeping without copying the native engine workspace."""

        return StateSnapshot(tuple(self.states.items()), tuple(self.last_inputs.items()))

    def restore(self, snapshot: StateSnapshot) -> None:
        if not isinstance(snapshot, StateSnapshot):
            raise ValueError("invalid TG11 state snapshot")
        self.states = dict(snapshot.states)
        self.last_inputs = dict(snapshot.last_inputs)
