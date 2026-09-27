"""Native acquisition plus fresh, early-symbol raw confirmation before caching."""
from dataclasses import replace
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'native_early_profile'))
from early_profile import NativeEarly, base
sys.path.insert(0, str(HERE.parent / 'native_tradeoff'))
from native_tradeoff_detector import NativeTradeoffDetector


def positive(point):
    return (point is not None and point.status == 0 and point.supported
            and point.valid_bounds and point.support_frames >= 2
            and point.fractional_complete and point.margin >= .025)


class EarlyConfirmedEngine:
    """Two explicit engine ports. No cached result substitutes for fresh scoring.

    Acquisition keeps its nuisance-aware positive gate. Canonical confirmation
    may veto it; a raw positive cannot resurrect a nuisance-rejected proposal.
    Extra point work is counted separately from the reused controller counters.
    """
    def __init__(self, discovery, confirmation):
        if discovery is confirmation:
            raise ValueError('distinct discovery and confirmation workspaces required')
        self.discovery = discovery
        self.confirmation = confirmation
        self.confirmation_calls = 0

    def screen(self, raw, *, receiver):
        return self.discovery.screen(raw, receiver=receiver)

    def _confirm(self, raw, point):
        self.confirmation_calls += 1
        result = self.confirmation.guided(raw, receiver=point.receiver,
            probe_index=point.probe_index,
            predicted_local_epoch_sample=float(round(point.local_epoch_sample)),
            scoring_cfo_hz=point.acquired_cfo_hz,
            expected_physical_cfo_hz=point.tracking_cfo_hz)
        if result is None:
            return None
        # Discovery fitted the timing; rounding it is an explicit quantization.
        # Guided point predictions remain unfitted and cannot train drift rates.
        return replace(result, fitted=point.fitted, candidate_index=point.candidate_index)

    def blind(self, raw, *, receiver, screen):
        output = []
        for point in self.discovery.blind(raw, receiver=receiver, screen=screen):
            if positive(point):
                result = self._confirm(raw, point)
                if result is not None:
                    output.append(result)
        return tuple(output)

    def guided(self, raw, **kwargs):
        point = self.discovery.guided(raw, **kwargs)
        return self._confirm(raw, point) if positive(point) else None


def create(stack, rate, edge):
    discovery = stack.enter_context(base.NativeGuidedBoundary(rate, edge))
    confirmation = stack.enter_context(NativeEarly(rate, edge))
    engine = EarlyConfirmedEngine(discovery, confirmation)
    return NativeTradeoffDetector(engine), engine
