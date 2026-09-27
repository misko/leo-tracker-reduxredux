"""Causal canonical-GLRT tracking over native discovery proposals.

Native observations are timing/CFO proposals only.  Every active observation
is decided by the current repository's ``conditioned_glrt64_score`` at a
preregistered integer epoch.  Cached visits bypass the native rank screen and
score the two prior probe positions directly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
import sys
from typing import Any, Callable, Protocol

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import leo

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("canonical tracking must use the current repository package")

from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S

TG11 = HERE.parent / "tg11"
if str(TG11) not in sys.path:
    sys.path.insert(1, str(TG11))
from decision import CacheKey, circular_samples  # noqa: E402


FRAME_RATE_HZ = 750
PROBE_COUNT = 11
PROBE_MS = 20
PROBE_STRIDE_MS = 10
MARGIN_GATE = 0.025
CFO_GATE_HZ = 8_000.0
TIMING_GATE_SECONDS = 2e-6


class Proposal(Protocol):
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: float
    acquired_cfo_hz: float
    supported: bool
    fitted: bool
    fractional_complete: bool


class ProposalEngine(Protocol):
    def screen(self, raw: Any, *, receiver: int) -> Any: ...

    def blind(self, raw: Any, *, receiver: int, screen: Any) -> tuple[Proposal, ...]: ...


@dataclass(frozen=True, slots=True)
class CanonicalObservation:
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: int
    dwell_epoch_sample: int
    source_epoch_counter: int
    source_epoch_fraction: float
    scoring_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    margin: float
    supported: bool
    fractional_complete: bool
    fitted: bool
    proposal_local_epoch_sample: float
    proposal_fitted: bool
    proposal_fractional_complete: bool
    proposal_order: int
    support_frames: int

    @property
    def positive(self) -> bool:
        return (
            self.supported
            and self.fractional_complete
            and self.margin >= MARGIN_GATE
        )


@dataclass(frozen=True, slots=True)
class CanonicalPair:
    receiver: int
    first: CanonicalObservation
    second: CanonicalObservation


@dataclass(frozen=True, slots=True)
class CanonicalDecision:
    active: bool
    route: str
    reason: str
    pair: CanonicalPair | None
    proposal_count: int
    canonical_score_count: int
    guided_attempts: int
    state_established: bool


@dataclass(frozen=True, slots=True)
class FittedAnchor:
    probe_index: int
    source_epoch_counter: int
    source_epoch_fraction: float


@dataclass(frozen=True, slots=True)
class CanonicalState:
    anchors: tuple[FittedAnchor, FittedAnchor]
    timing_rate_samples_per_s: float
    scoring_cfo_hz: float
    physical_cfo_hz: float
    cfo_rate_hz_per_s: float
    cfo_measurement_counter: int
    cfo_measurement_fraction: float
    last_seen_counter: int
    last_visit_index: int
    guided_accepts_since_discovery: int


@dataclass(frozen=True, slots=True)
class CanonicalSnapshot:
    states: tuple[tuple[CacheKey, CanonicalState], ...]
    last_inputs: tuple[tuple[CacheKey, tuple[int, int]], ...]


@dataclass(frozen=True, slots=True)
class Prediction:
    probe_index: int
    local_epoch_sample: float
    scoring_cfo_hz: float
    physical_cfo_hz: float


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class _VisitCanonicalScorer:
    """Lazy per-probe conversion cache; construction belongs inside call timing."""

    def __init__(
        self,
        raw: Any,
        rate_hz: int,
        edge: str,
        scorer: Callable[..., Any],
    ) -> None:
        values = np.asarray(raw)
        expected = (rate_hz * 120 // 1_000, 2, 2)
        if (
            values.dtype != np.dtype("int16")
            or values.shape != expected
            or not values.flags.c_contiguous
        ):
            raise ValueError("complete C-contiguous natural dual-RX CI16 dwell required")
        self.raw = values
        self.rate_hz = rate_hz
        self.edge = edge
        self.scorer = scorer
        self.probe_samples = rate_hz * PROBE_MS // 1_000
        self.stride_samples = rate_hz * PROBE_STRIDE_MS // 1_000
        self.cache: dict[tuple[int, int], np.ndarray] = {}
        self.score_count = 0

    def probe(self, receiver: int, probe_index: int) -> np.ndarray:
        if receiver not in (0, 1) or not 0 <= probe_index < PROBE_COUNT:
            raise ValueError("invalid canonical probe coordinate")
        key = receiver, probe_index
        if key not in self.cache:
            start = probe_index * self.stride_samples
            selected = self.raw[start : start + self.probe_samples, receiver]
            values = np.empty(self.probe_samples, dtype=np.complex64)
            values.real = selected[:, 0]
            values.imag = selected[:, 1]
            values.setflags(write=False)
            self.cache[key] = values
        return self.cache[key]

    def point(
        self,
        *,
        receiver: int,
        probe_index: int,
        epoch_sample: int,
        scoring_cfo_hz: float,
    ) -> Any:
        if type(epoch_sample) is not int or not _finite(scoring_cfo_hz):
            raise ValueError("canonical point requires integer epoch and finite CFO")
        self.score_count += 1
        return self.scorer(
            self.probe(receiver, probe_index),
            self.rate_hz,
            epoch_sample=epoch_sample,
            acquired_cfo_hz=float(scoring_cfo_hz),
            edge=self.edge,
        )


class CanonicalTrackingDetector:
    """Stateful per-receiver detector with snapshot-safe causal bookkeeping."""

    def __init__(
        self,
        engine: ProposalEngine,
        *,
        scorer: Callable[..., Any] = conditioned_glrt64_score,
        expiry_seconds: float = 2.0,
        guided_accept_limit: int = 31,
        maximum_clock_error_ppm: float = 50.0,
        maximum_cfo_rate_hz_per_s: float = 5_000.0,
    ) -> None:
        if engine is None or not callable(scorer):
            raise ValueError("canonical detector requires engine and scorer")
        values = (expiry_seconds, maximum_clock_error_ppm, maximum_cfo_rate_hz_per_s)
        if (
            not all(_finite(value) and value >= 0 for value in values)
            or expiry_seconds <= 0
            or type(guided_accept_limit) is not int
            or guided_accept_limit < 1
        ):
            raise ValueError("invalid canonical tracking policy")
        self.engine = engine
        self.scorer = scorer
        self.expiry_seconds = float(expiry_seconds)
        self.guided_accept_limit = guided_accept_limit
        self.maximum_clock_error_ppm = float(maximum_clock_error_ppm)
        self.maximum_cfo_rate_hz_per_s = float(maximum_cfo_rate_hz_per_s)
        self.states: dict[CacheKey, CanonicalState] = {}
        self.last_inputs: dict[CacheKey, tuple[int, int]] = {}

    def clear(self) -> None:
        self.states.clear()
        self.last_inputs.clear()

    def snapshot(self) -> CanonicalSnapshot:
        return CanonicalSnapshot(tuple(self.states.items()), tuple(self.last_inputs.items()))

    def restore(self, snapshot: CanonicalSnapshot) -> None:
        if not isinstance(snapshot, CanonicalSnapshot):
            raise ValueError("invalid canonical tracking snapshot")
        self.states = dict(snapshot.states)
        self.last_inputs = dict(snapshot.last_inputs)

    @staticmethod
    def _probe_start(rate_hz: int, probe_index: int) -> int:
        return probe_index * rate_hz * PROBE_STRIDE_MS // 1_000

    def _register(self, key: CacheKey, start_counter: int, visit_index: int) -> None:
        if type(start_counter) is not int or type(visit_index) is not int or visit_index < 0:
            raise ValueError("invalid canonical visit coordinate")
        previous = self.last_inputs.get(key)
        if previous is not None and (
            start_counter <= previous[0] or visit_index <= previous[1]
        ):
            raise ValueError("canonical visits must advance causally within a key")
        self.last_inputs[key] = start_counter, visit_index

    @staticmethod
    def _integer_cells(epoch: float, period: float) -> tuple[int, ...]:
        if not _finite(epoch) or not _finite(period) or period <= 0:
            raise ValueError("invalid canonical proposal epoch")
        normalized = float(epoch) % period
        lower = math.floor(normalized)
        upper = math.ceil(normalized)
        return tuple(dict.fromkeys((lower, upper)))

    def _score_proposal(
        self,
        visit: _VisitCanonicalScorer,
        key: CacheKey,
        start_counter: int,
        proposal: Proposal,
        proposal_order: int,
    ) -> tuple[CanonicalObservation, ...]:
        if proposal.receiver != key.receiver or not proposal.supported:
            return ()
        expected_start = self._probe_start(key.rate_hz, proposal.probe_index)
        if proposal.probe_start_sample != expected_start:
            raise ValueError("native proposal has an invalid probe start")
        period = key.rate_hz / FRAME_RATE_HZ
        output = []
        for epoch in self._integer_cells(proposal.local_epoch_sample, period):
            support_frames = self._canonical_support_frames(key.rate_hz, epoch)
            if support_frames < 2:
                continue
            score = visit.point(
                receiver=key.receiver,
                probe_index=proposal.probe_index,
                epoch_sample=epoch,
                scoring_cfo_hz=proposal.acquired_cfo_hz,
            )
            fields = (
                score.exact_score,
                score.control_score,
                score.margin,
                score.tracking_cfo_hz,
            )
            if not all(_finite(value) for value in fields):
                raise ValueError("canonical scorer returned non-finite output")
            output.append(
                CanonicalObservation(
                    receiver=key.receiver,
                    probe_index=proposal.probe_index,
                    probe_start_sample=expected_start,
                    local_epoch_sample=epoch,
                    dwell_epoch_sample=expected_start + epoch,
                    source_epoch_counter=start_counter + expected_start + epoch,
                    source_epoch_fraction=0.0,
                    scoring_cfo_hz=float(proposal.acquired_cfo_hz),
                    tracking_cfo_hz=float(score.tracking_cfo_hz),
                    exact_score=float(score.exact_score),
                    control_score=float(score.control_score),
                    margin=float(score.margin),
                    supported=True,
                    # This means the integer hypothesis was fully scored.  It
                    # is not a claim that fractional timing was fitted.
                    fractional_complete=True,
                    fitted=False,
                    proposal_local_epoch_sample=float(proposal.local_epoch_sample),
                    proposal_fitted=bool(proposal.fitted),
                    proposal_fractional_complete=bool(proposal.fractional_complete),
                    proposal_order=proposal_order,
                    support_frames=support_frames,
                )
            )
        return tuple(output)

    @staticmethod
    def _canonical_support_frames(rate_hz: int, epoch_sample: int) -> int:
        """Count complete canonical symbols 2..65 in one 20 ms aperture."""

        probe_samples = rate_hz * PROBE_MS // 1_000
        frame_period = rate_hz / FRAME_RATE_HZ
        symbol_period = rate_hz * OFDM_SYMBOL_DURATION_S
        first = round(2 * symbol_period)
        stop = round(66 * symbol_period)
        frames = 0
        while True:
            start = epoch_sample + round(frames * frame_period)
            if start + first >= probe_samples:
                break
            if start >= 0 and start + stop <= probe_samples:
                frames += 1
                continue
            break
        return frames

    @staticmethod
    def _pair(
        observations: tuple[CanonicalObservation, ...], rate_hz: int
    ) -> CanonicalPair | None:
        by_probe: dict[int, list[CanonicalObservation]] = {}
        for observation in observations:
            if observation.positive:
                by_probe.setdefault(observation.probe_index, []).append(observation)
        history: list[CanonicalObservation] = []
        separation = rate_hz * PROBE_MS // 1_000
        for probe_index in sorted(by_probe):
            current = sorted(
                by_probe[probe_index],
                key=lambda item: (-item.margin, item.proposal_order, item.local_epoch_sample),
            )
            for observation in current:
                compatible = [
                    prior
                    for prior in history
                    if observation.probe_start_sample - prior.probe_start_sample >= separation
                    and abs(observation.tracking_cfo_hz - prior.tracking_cfo_hz)
                    <= CFO_GATE_HZ
                ]
                if compatible:
                    first = min(
                        compatible,
                        key=lambda item: (
                            item.probe_index,
                            -item.margin,
                            item.proposal_order,
                            item.local_epoch_sample,
                        ),
                    )
                    return CanonicalPair(observation.receiver, first, observation)
            history.extend(current)
        return None

    @staticmethod
    def _anchor(observation: CanonicalObservation) -> FittedAnchor:
        whole = math.floor(observation.proposal_local_epoch_sample)
        fraction = observation.proposal_local_epoch_sample - whole
        return FittedAnchor(
            observation.probe_index,
            observation.source_epoch_counter
            - observation.local_epoch_sample
            + whole,
            fraction,
        )

    def _establish(
        self,
        key: CacheKey,
        start_counter: int,
        visit_index: int,
        pair: CanonicalPair,
    ) -> bool:
        if not all(
            item.proposal_fitted and item.proposal_fractional_complete
            for item in (pair.first, pair.second)
        ):
            self.states.pop(key, None)
            return False
        anchors = self._anchor(pair.first), self._anchor(pair.second)
        previous = self.states.get(key)
        timing_rate = 0.0
        cfo_rate = 0.0
        if previous is not None:
            old = previous.anchors[1]
            new = anchors[1]
            dt = (
                new.source_epoch_counter
                - old.source_epoch_counter
                + new.source_epoch_fraction
                - old.source_epoch_fraction
            ) / key.rate_hz
            if 0 < dt <= 5.0:
                integer_phase = (
                    (new.source_epoch_counter - old.source_epoch_counter)
                    * FRAME_RATE_HZ
                    % key.rate_hz
                ) / FRAME_RATE_HZ
                fractional_phase = new.source_epoch_fraction - old.source_epoch_fraction
                measured = circular_samples(integer_phase + fractional_phase, key.rate_hz) / dt
                bound = self.maximum_clock_error_ppm * 1e-6 * key.rate_hz
                timing_rate = measured if abs(measured) <= bound else 0.0
            cfo_dt = (
                pair.second.source_epoch_counter
                - previous.cfo_measurement_counter
                + pair.second.source_epoch_fraction
                - previous.cfo_measurement_fraction
            ) / key.rate_hz
            if 0 < cfo_dt <= 5.0:
                measured_cfo_rate = (
                    pair.second.tracking_cfo_hz - previous.physical_cfo_hz
                ) / cfo_dt
                cfo_rate = (
                    measured_cfo_rate
                    if abs(measured_cfo_rate) <= self.maximum_cfo_rate_hz_per_s
                    else 0.0
                )
        self.states[key] = CanonicalState(
            anchors=anchors,
            timing_rate_samples_per_s=timing_rate,
            scoring_cfo_hz=pair.second.scoring_cfo_hz,
            physical_cfo_hz=pair.second.tracking_cfo_hz,
            cfo_rate_hz_per_s=cfo_rate,
            cfo_measurement_counter=pair.second.source_epoch_counter,
            cfo_measurement_fraction=0.0,
            last_seen_counter=start_counter,
            last_visit_index=visit_index,
            guided_accepts_since_discovery=0,
        )
        return True

    def _prediction(
        self,
        key: CacheKey,
        state: CanonicalState,
        anchor: FittedAnchor,
        start_counter: int,
    ) -> Prediction:
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
        elapsed = (
            start_counter
            + probe_start
            + base_whole
            - anchor.source_epoch_counter
            + base_fraction
            - anchor.source_epoch_fraction
        ) / key.rate_hz
        local = (base_epoch + state.timing_rate_samples_per_s * elapsed) % period
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
        physical = state.physical_cfo_hz + state.cfo_rate_hz_per_s * measurement_elapsed
        return Prediction(anchor.probe_index, local, state.scoring_cfo_hz, physical)

    def _discovery(
        self,
        raw: Any,
        visit: _VisitCanonicalScorer,
        key: CacheKey,
        start_counter: int,
        visit_index: int,
        reason: str,
        guided_attempts: int,
    ) -> CanonicalDecision:
        screen = self.engine.screen(raw, receiver=key.receiver)
        proposals = tuple(self.engine.blind(raw, receiver=key.receiver, screen=screen))
        observations = tuple(
            point
            for order, proposal in enumerate(proposals)
            for point in self._score_proposal(visit, key, start_counter, proposal, order)
        )
        pair = self._pair(observations, key.rate_hz)
        route = f"discovery_{reason}"
        if pair is None:
            self.states.pop(key, None)
            return CanonicalDecision(
                False,
                route,
                "all supported native proposals lacked a canonical positive pair",
                None,
                len(proposals),
                visit.score_count,
                guided_attempts,
                False,
            )
        established = self._establish(key, start_counter, visit_index, pair)
        return CanonicalDecision(
            True,
            route,
            "two canonical-positive nonoverlapping proposal confirmations",
            pair,
            len(proposals),
            visit.score_count,
            guided_attempts,
            established,
        )

    def _guided_observation(
        self,
        visit: _VisitCanonicalScorer,
        key: CacheKey,
        start_counter: int,
        prediction: Prediction,
        order: int,
    ) -> CanonicalObservation | None:
        # A predicted proposal is deliberately marked unfitted.  Point-score
        # selection confirms evidence but cannot train timing drift.
        proposal = _PredictedProposal(
            receiver=key.receiver,
            probe_index=prediction.probe_index,
            probe_start_sample=self._probe_start(key.rate_hz, prediction.probe_index),
            local_epoch_sample=prediction.local_epoch_sample,
            acquired_cfo_hz=prediction.scoring_cfo_hz,
        )
        points = self._score_proposal(visit, key, start_counter, proposal, order)
        eligible = [
            point
            for point in points
            if point.positive
            and abs(point.local_epoch_sample - prediction.local_epoch_sample)
            <= key.rate_hz * TIMING_GATE_SECONDS
            and abs(point.tracking_cfo_hz - prediction.physical_cfo_hz) <= CFO_GATE_HZ
        ]
        if not eligible:
            return None
        return min(eligible, key=lambda item: (-item.margin, item.local_epoch_sample))

    def process(
        self,
        raw: Any,
        key: CacheKey,
        *,
        start_counter: int,
        visit_index: int,
        force_discovery: bool = False,
    ) -> CanonicalDecision:
        self._register(key, start_counter, visit_index)
        visit = _VisitCanonicalScorer(raw, key.rate_hz, key.edge, self.scorer)
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
            return self._discovery(
                raw, visit, key, start_counter, visit_index, reason, 0
            )

        guided = []
        for order, anchor in enumerate(state.anchors):
            prediction = self._prediction(key, state, anchor, start_counter)
            observation = self._guided_observation(
                visit, key, start_counter, prediction, order
            )
            if observation is None:
                return self._discovery(
                    raw,
                    visit,
                    key,
                    start_counter,
                    visit_index,
                    "guided_failure",
                    order + 1,
                )
            guided.append(observation)
        pair = self._pair(tuple(guided), key.rate_hz)
        if pair is None:
            return self._discovery(
                raw,
                visit,
                key,
                start_counter,
                visit_index,
                "guided_failure",
                len(guided),
            )
        # Canonical CFO is measured from raw data.  Point-selected timing is
        # intentionally absent from anchors and timing-rate updates.
        measurement = pair.second
        elapsed = (
            measurement.source_epoch_counter
            - state.cfo_measurement_counter
            + measurement.source_epoch_fraction
            - state.cfo_measurement_fraction
        ) / key.rate_hz
        cfo_rate = state.cfo_rate_hz_per_s
        if elapsed > 0:
            measured = (measurement.tracking_cfo_hz - state.physical_cfo_hz) / elapsed
            if abs(measured) <= self.maximum_cfo_rate_hz_per_s:
                cfo_rate = measured
        self.states[key] = replace(
            state,
            scoring_cfo_hz=measurement.tracking_cfo_hz,
            physical_cfo_hz=measurement.tracking_cfo_hz,
            cfo_rate_hz_per_s=cfo_rate,
            cfo_measurement_counter=measurement.source_epoch_counter,
            cfo_measurement_fraction=0.0,
            last_seen_counter=start_counter,
            last_visit_index=visit_index,
            guided_accepts_since_discovery=state.guided_accepts_since_discovery + 1,
        )
        return CanonicalDecision(
            True,
            "guided",
            "two fresh canonical point confirmations formed a compatible pair",
            pair,
            0,
            visit.score_count,
            len(guided),
            True,
        )


@dataclass(frozen=True, slots=True)
class _PredictedProposal:
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: float
    acquired_cfo_hz: float
    supported: bool = True
    fitted: bool = False
    fractional_complete: bool = False


__all__ = [
    "CacheKey",
    "CanonicalDecision",
    "CanonicalObservation",
    "CanonicalPair",
    "CanonicalSnapshot",
    "CanonicalState",
    "CanonicalTrackingDetector",
    "FittedAnchor",
]
