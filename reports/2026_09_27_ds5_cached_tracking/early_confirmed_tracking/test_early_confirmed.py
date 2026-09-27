from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from engine import EarlyConfirmedEngine, NativeTradeoffDetector

spec = importlib.util.spec_from_file_location('early_controller_fixtures',
    HERE.parent / 'native_tradeoff/test_native_tradeoff_detector.py')
fixtures = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixtures
spec.loader.exec_module(fixtures)


class Port:
    def __init__(self, margin=.2):
        self.margin = margin
        self.calls = []

    def guided(self, raw, **kwargs):
        self.calls.append(kwargs)
        return fixtures.Observation(kwargs['receiver'], kwargs['probe_index'],
            fixtures.probe_start(kwargs['probe_index']), kwargs['predicted_local_epoch_sample'],
            margin=self.margin, fitted=False)

    def screen(self, raw, *, receiver):
        return fixtures.Screen(receiver, tuple(fixtures.Window(i, fixtures.probe_start(i)) for i in range(11)))

    def blind(self, raw, *, receiver, screen):
        return tuple(fixtures.Observation(receiver, i, fixtures.probe_start(i),
                     fixtures.phase_local(0, 317, i), margin=self.margin) for i in (0, 2))


def test_nuisance_rejected_discovery_cannot_be_resurrected_by_raw_score():
    discovery, confirmation = Port(0.), Port(.9)
    engine = EarlyConfirmedEngine(discovery, confirmation)
    assert engine.blind(None, receiver=0, screen=None) == ()
    assert confirmation.calls == []


def test_confirmation_is_integer_and_preserves_only_discovery_fit_provenance():
    discovery, confirmation = Port(), Port()
    engine = EarlyConfirmedEngine(discovery, confirmation)
    points = engine.blind(None, receiver=0, screen=None)
    assert len(points) == 2 and all(p.fitted for p in points)
    assert all(c['predicted_local_epoch_sample'].is_integer() for c in confirmation.calls)
    result = engine.guided(None, receiver=0, probe_index=2,
        predicted_local_epoch_sample=317.4, scoring_cfo_hz=300000., expected_physical_cfo_hz=100000.)
    assert not result.fitted
    assert engine.confirmation_calls == 3


def test_rejected_fresh_confirmation_clears_existing_cache_after_failed_fallback():
    discovery, confirmation = Port(), Port()
    detector = NativeTradeoffDetector(EarlyConfirmedEngine(discovery, confirmation))
    key = fixtures.key()
    first = detector.process(None, key, start_counter=0, visit_index=0)
    assert first.active and key in detector.states
    confirmation.margin = 0.
    second = detector.process(None, key, start_counter=300000, visit_index=1)
    assert not second.active and second.route == 'blind_guided_failure'
    assert key not in detector.states
