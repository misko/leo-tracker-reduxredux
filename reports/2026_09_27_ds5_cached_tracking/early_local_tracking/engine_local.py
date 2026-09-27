"""Three integer timing confirmations per eligible native proposal."""
from dataclasses import replace
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'early_confirmed_tracking'))
from engine import EarlyConfirmedEngine, NativeEarly, NativeTradeoffDetector, base, positive


class LocalConfirmedEngine(EarlyConfirmedEngine):
    def _confirm(self, raw, point):
        center = round(point.local_epoch_sample)
        candidates = []
        # Prefer the center on exact ties, then earlier timing.
        for offset in (0, -1, 1):
            if center + offset < 0:
                continue
            self.confirmation_calls += 1
            result = self.confirmation.guided(raw, receiver=point.receiver,
                probe_index=point.probe_index,
                predicted_local_epoch_sample=float(center + offset),
                scoring_cfo_hz=point.acquired_cfo_hz,
                expected_physical_cfo_hz=point.tracking_cfo_hz)
            if positive(result):
                candidates.append(result)
        if not candidates:
            return None
        selected = max(candidates, key=lambda p: p.margin)
        # Never teach drift from a small search around a guided prediction.
        return replace(selected, fitted=point.fitted, candidate_index=point.candidate_index)


def create(stack, rate, edge):
    discovery = stack.enter_context(base.NativeGuidedBoundary(rate, edge))
    confirmation = stack.enter_context(NativeEarly(rate, edge))
    engine = LocalConfirmedEngine(discovery, confirmation)
    return NativeTradeoffDetector(engine), engine
