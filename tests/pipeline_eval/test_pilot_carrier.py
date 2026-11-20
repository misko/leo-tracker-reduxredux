import numpy as np
import pytest

from tools.pipeline_eval.qualification import differential_pilot_eval as fixture
from tools.pipeline_eval.qualification import pilot_carrier_trial as trial
from tools.pipeline_eval.variants import pilot_carrier as model


@pytest.mark.parametrize("frequency", [-777_000, -227_273, -1, 0, 227_273, 777_000])
def test_short_lag_selects_signed_absolute_alias(frequency):
    def phasor(lag):
        return np.exp(2j * np.pi * frequency * lag / model.timing.RATE)

    result = model.resolve(phasor(model.timing.LAG), phasor(model.SHORT_LAG))
    assert result["absolute_hz"] == pytest.approx(frequency)
    assert abs(result["folded_hz"]) <= model.timing.RATE / model.timing.LAG / 2


@pytest.mark.parametrize("edge", ["upper", "lower"])
def test_genuine_signed_template_recovers_planted_frequency(edge):
    samples, plant = fixture.synthetic(edge, "strong")
    for lane in (0, 1):
        estimate = model.at_epoch(model.products(samples, lane), edge, plant["epoch"])
        assert abs(estimate["absolute_hz"] - plant["cfo_hz"]) < 1_000


def test_empty_samples_supply_no_phase_or_frequency():
    samples = np.zeros((model.timing.SAMPLES, 2, 2), dtype="<i2")
    assert model.at_epoch(model.products(samples, 0), "upper", model.timing.FRAME - 1) is None
    assert trial.proposals([]) == []
    with pytest.raises(ValueError):
        model.at_epoch([], "upper", model.timing.FRAME)


def test_folded_score_does_not_reward_wrong_absolute_alias():
    sample = dict(epoch=1, mode="rank1", estimate=dict(absolute_hz=0, folded_hz=0, grid_hz=0))
    row = trial.errors(sample, model.timing.RATE / 750 - 0.1, model.timing.RATE / model.timing.LAG)
    assert row["epoch_error_samples"] == pytest.approx(1.1)
    assert abs(row["folded_error_hz"]) < 1e-6
    assert row["absolute_error_hz"] < -200_000
    assert row["bin_steps"] == 3
