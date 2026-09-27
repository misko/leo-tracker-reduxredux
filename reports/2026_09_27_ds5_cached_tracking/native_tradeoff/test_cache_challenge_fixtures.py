import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("native_cache_challenge_fixtures", HERE / "cache_challenge_fixtures.py")
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_tone_controls_are_readonly_natural_ci16_and_have_declared_frequency():
    raw, seeds = module.negative_array(2_500_000, 1)
    assert raw.shape == (300_000, 2, 2)
    assert raw.dtype == np.dtype("<i2") and not raw.flags.writeable
    assert seeds[0] != seeds[1]
    values = raw[:, 0, 0].astype(float) + 1j * raw[:, 0, 1]
    measured = np.angle(np.vdot(values[:-1], values[1:])) * 2_500_000 / (2 * np.pi)
    assert abs(measured - 4000) < 10


def test_clipped_challenge_is_rejected(monkeypatch):
    monkeypatch.setattr(module, "TONE_AMPLITUDE", 40_000.0)
    with pytest.raises(ValueError, match="clipping"):
        module.negative_array(2_500_000, 0)


def test_sequences_keep_one_key_exact_counters_and_explicit_negative_truth():
    for steps in module.sequences():
        assert len(steps) == 7
        rate = steps[0].case.rate
        assert len({(s.case.session, s.case.channel, s.case.edge,
                     s.case.tuning_identity, s.case.calibration_identity) for s in steps}) == 1
        for index, step in enumerate(steps):
            assert type(step.case.source_counter) is int and step.case.source_counter > 2**55
            assert step.case.source_counter - steps[0].case.source_counter == index * rate * 120 // 1000
            assert step.expected_active == (index % 2 == 0)
            assert step.carrier_phase_reset
            if not step.expected_active:
                assert step.case.injected == ((), ())
                assert step.noise_seeds and step.tone_frequencies_hz
                assert step.raw is not steps[0].raw
        assert 0 in steps[1].tone_frequencies_hz
        assert 0 in steps[5].tone_frequencies_hz
