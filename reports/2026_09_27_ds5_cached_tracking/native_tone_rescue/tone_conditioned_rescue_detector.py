"""Two-port rescue controller with auditable tone-conditioned point calls.

The primary controller owns a :class:`NativeGuidedBoundary` engine.  Rescue
calls use a separate :class:`NativeToneGuided` port.  The frozen raw-rescue
controller supplies the acquisition, routing, gate, budget, and rollback
policy; this module only makes the second port explicit and retains its full
observations (including nuisance-fit receipts) for later serialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
SRC = ROOT / "src"
TRADEOFF = REPORT / "native_tradeoff"
RAW_RESCUE = REPORT / "native_rescue"

for entry in (str(SRC), str(TRADEOFF), str(RAW_RESCUE)):
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)

from leo.analysis.starlink.acquisition import acquire_symbolwise  # noqa: E402
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score  # noqa: E402
from native_rescue_detector import (  # noqa: E402
    RescueEvent,
    RescueVisitDecision,
    SameRxRescueDetector,
)
from native_tradeoff_detector import NativeTradeoffDetector  # noqa: E402


@dataclass(frozen=True, slots=True)
class ToneGuidedCall:
    """One rescue-port request and the full engine response, if available."""

    receiver: int
    probe_index: int
    predicted_local_epoch_sample: float
    scoring_cfo_hz: float
    expected_physical_cfo_hz: float
    observation: Any | None


@dataclass(frozen=True, slots=True)
class ToneConditionedRescueVisitDecision:
    """Frozen rescue decision plus full tone-conditioned engine receipts."""

    decisions: tuple[Any, Any]
    primary_decisions: tuple[Any, Any]
    rescue_receiver: int | None
    rescue_acquisition_count: int
    rescue_candidate_count: int
    rescue_candidate_score_count: int
    rescue_seed_guided_count: int
    rescue_confirmation_guided_count: int
    rescue_events: tuple[RescueEvent, ...]
    tone_guided_calls: tuple[ToneGuidedCall, ...]

    def decision(self, receiver: int) -> Any:
        if type(receiver) is not int or receiver not in (0, 1):
            raise ValueError("receiver must be zero or one")
        return self.decisions[receiver]

    @property
    def primary_scoring_count(self) -> int:
        return sum(item.scoring_count for item in self.primary_decisions)

    @property
    def total_scoring_count(self) -> int:
        return (
            self.primary_scoring_count
            + self.rescue_candidate_score_count
            + self.rescue_seed_guided_count
            + self.rescue_confirmation_guided_count
        )


class _RecordingToneGuidedPort:
    """Narrow adapter retaining full responses without changing call arguments."""

    def __init__(self, engine: Any) -> None:
        if engine is None or not callable(getattr(engine, "guided", None)):
            raise ValueError("tone-conditioned rescue engine needs a guided port")
        self.engine = engine
        self.calls: list[ToneGuidedCall] = []

    def clear_calls(self) -> None:
        self.calls.clear()

    def guided(self, raw: Any, **kwargs: Any) -> Any | None:
        observation = self.engine.guided(raw, **kwargs)
        self.calls.append(ToneGuidedCall(
            receiver=kwargs["receiver"],
            probe_index=kwargs["probe_index"],
            predicted_local_epoch_sample=float(kwargs["predicted_local_epoch_sample"]),
            scoring_cfo_hz=float(kwargs["scoring_cfo_hz"]),
            expected_physical_cfo_hz=float(kwargs["expected_physical_cfo_hz"]),
            observation=observation,
        ))
        return observation


class ToneConditionedSameRxRescueDetector(SameRxRescueDetector):
    """The frozen rescue policy with separate primary and rescue point ports.

    The inherited algorithm is intentionally pinned as a source dependency.
    Its constructor is not used because it requires one shared engine.  Both
    ports are instead fixed here at construction and never replaced.
    """

    def __init__(
        self,
        primary: NativeTradeoffDetector,
        rescue_engine: Any,
        *,
        acquisition: Callable[..., Any] = acquire_symbolwise,
        scorer: Callable[..., Any] = conditioned_glrt64_score,
    ) -> None:
        if (
            not isinstance(primary, NativeTradeoffDetector)
            or rescue_engine is None
            or primary.engine is rescue_engine
            or not callable(getattr(rescue_engine, "guided", None))
            or not callable(acquisition)
            or not callable(scorer)
        ):
            raise ValueError(
                "tone rescue requires distinct fixed primary and guided rescue ports"
            )
        self.primary = primary
        self.rescue_engine = rescue_engine
        self._recording_rescue_port = _RecordingToneGuidedPort(rescue_engine)
        # The inherited frozen rescue algorithm calls this fixed port.
        self.guarded_engine = self._recording_rescue_port
        self.acquisition = acquisition
        self.scorer = scorer

    def process(
        self,
        raw: Any,
        keys: Any,
        *,
        start_counter: int,
        visit_index: int,
        force_discovery: bool = False,
    ) -> ToneConditionedRescueVisitDecision:
        self._recording_rescue_port.clear_calls()
        core: RescueVisitDecision = super().process(
            raw,
            keys,
            start_counter=start_counter,
            visit_index=visit_index,
            force_discovery=force_discovery,
        )
        return ToneConditionedRescueVisitDecision(
            decisions=core.decisions,
            primary_decisions=core.primary_decisions,
            rescue_receiver=core.rescue_receiver,
            rescue_acquisition_count=core.rescue_acquisition_count,
            rescue_candidate_count=core.rescue_candidate_count,
            rescue_candidate_score_count=core.rescue_candidate_score_count,
            rescue_seed_guided_count=core.rescue_seed_guided_count,
            rescue_confirmation_guided_count=core.rescue_confirmation_guided_count,
            rescue_events=core.rescue_events,
            tone_guided_calls=tuple(self._recording_rescue_port.calls),
        )


__all__ = [
    "ToneConditionedRescueVisitDecision",
    "ToneConditionedSameRxRescueDetector",
    "ToneGuidedCall",
]
