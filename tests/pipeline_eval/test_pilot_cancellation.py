import numpy as np
import pytest

from tools.pipeline_eval.qualification import pilot_cancellation_overlap as overlap
from tools.pipeline_eval.qualification import pilot_cancellation_trial as trial
from tools.pipeline_eval.variants import pilot_cancellation as pilot


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_two_injected_literal_pilots_and_sidelobe_control(edge):
    samples, targets = trial.planted(edge, "two_pilots")
    raw = pilot.lane_values(samples)[0]
    cancel = trial.lane(raw, edge, (-800_000, 800_000), "cancelled")
    raw_retry = trial.lane(raw, edge, (-800_000, 800_000), "raw_retry")
    for key, target in zip(("primary", "secondary"), targets, strict=True):
        selected = cancel[key]
        assert (
            pilot.relationship(selected["phase"], selected["cfo_hz"], target.phase, target.cfo_hz)
            == "literal"
        )
    assert cancel["held_removal_coherent"] > 0.95
    assert raw_retry["held_removal_coherent"] == 0
    blind = raw_retry["secondary"]
    assert (
        blind is None
        or pilot.relationship(blind["phase"], blind["cfo_hz"], targets[1].phase, targets[1].cfo_hz)
        != "literal"
    )


@pytest.mark.parametrize("condition", ["noise", "zero", "one_pilot"])
def test_controls_require_a_second_independent_waveform(condition):
    iq, target = trial.planted("lower", condition)
    raw = pilot.lane_values(iq)[0]
    result = trial.lane(raw, "lower", (-800_000, 800_000), "cancelled")
    assert bool(result["primary"]) == bool(target)
    assert result["secondary"] is None


def test_holding_samples_out_leaves_training_frequency_and_amplitude_unchanged():
    iq, (target,) = trial.planted("upper", "one_pilot")
    raw = pilot.lane_values(iq)[0]
    muted = raw.copy()
    muted[pilot.SPLIT :] = 0
    centers = pilot.scout(raw, "upper")[: pilot.BASE_CENTERS]
    assert pilot.scout(muted, "upper")[: pilot.BASE_CENTERS] == centers
    reference = pilot.discover(raw, "upper", centers, -800_000, 800_000)
    assert pilot.discover(muted, "upper", centers, -800_000, 800_000) == reference
    fit = reference[0]
    assert pilot.relationship(fit.phase, fit.cfo_hz, target.phase, target.cfo_hz) == "literal"
    assert pilot.evidence(raw, "upper", fit).coded
    assert not pilot.evidence(muted, "upper", fit).coded


def test_wrapped_coordinates_preserve_literal_alias_and_family_distinctions():
    near_boundary = pilot.PERIOD - 0.25
    assert pilot.relationship(near_boundary, 10_000, 0.25, 10_500) == "literal"
    assert pilot.relationship(near_boundary, 10_000, 0.25, 10_000 + pilot.ALIAS_HZ) == "alias"
    assert pilot.relationship(50, 10_000, 0.25, 10_000) == "distinct"
    primary = pilot.Pilot(30, 0, 10_000, 0, 1000, 10 + 0j)
    sidelobe = pilot.Pilot(37, 0, 10_000, 1, 90, 3 + 0j)
    other = pilot.Pilot(37, 0, 16_000, 2, 80, 3 + 0j)
    assert pilot.comparable(primary, sidelobe)
    assert not pilot.comparable(primary, other)


def test_ci16_keeps_physical_receivers_separate():
    raw = np.zeros((pilot.SAMPLES, 2, 2), dtype="<i2")
    raw[11, 0] = [5, -3]
    raw[29, 1] = [-2, 7]
    out = pilot.lane_values(raw)
    assert out[0, 11] == 5 - 3j and out[1, 29] == -2 + 7j
    assert np.count_nonzero(out) == 2
    with pytest.raises(ValueError, match="dual-CI16"):
        pilot.lane_values(raw[:, :1])


def test_joint_projection_separates_simultaneous_and_sequential_pilots():
    iq, (first, second) = trial.planted("lower", "two_pilots")
    raw = pilot.lane_values(iq)[0]
    assert overlap.check(raw, "lower", first, second)["supported"]
    midpoint = pilot.SPLIT + 2 * overlap.BLOCK
    raw[pilot.SPLIT : midpoint] -= pilot.render("lower", second)[pilot.SPLIT : midpoint]
    raw[midpoint:] -= pilot.render("lower", first)[midpoint:]
    measured = overlap.check(raw, "lower", first, second)
    assert not measured["supported"]
    assert sum(measured["simultaneous"]) <= 1
