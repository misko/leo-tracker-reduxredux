import numpy as np
import pytest

from reports.ALGO08.v3 import joint_pilot_holdout as study


@pytest.fixture
def two_subbands():
    rng = np.random.default_rng(18645)
    pilot = np.zeros(study.N, dtype=np.complex128)
    for sign in (-1, 1):
        bins = (sign * rng.choice(np.arange(4200, 9500), size=16, replace=False)) % study.N
        pilot[bins] = rng.uniform(1, 3, size=16) * np.exp(1j*rng.uniform(-np.pi, np.pi, size=16))
    plans = [study.sparse_plan(pilot, index) for index in range(2)]
    return pilot, plans


@pytest.mark.parametrize("signed_bin, delay", [(-737, 129), (513, 13331)])
def test_independent_subband_scout_preserves_delay_wrap_and_signed_frequency(two_subbands, signed_bin, delay):
    pilot, plans = two_subbands
    n = np.arange(120000)
    sample = np.fft.ifft(pilot)[(n-delay) % study.N] * study.N * 400
    waveform = sample * np.exp(2j * np.pi * signed_bin * n / study.N)
    iq = np.zeros((n.size, 2, 2), dtype="<i2")
    iq[:, 0, 0] = np.rint(waveform.real)
    iq[:, 0, 1] = np.rint(waveform.imag)
    factor = (0, delay, 0, signed_bin*study.BIN_HZ, 0, 0)
    result = study.assay(iq, 0, plans, factor)
    assert result["full"]["views"] == [True, True]
    for view, plan in enumerate(plans):
        actual = (plan["observed"]+study.N//2) % study.N - study.N//2
        assert np.all(actual < 0) if view == 0 else np.all(actual >= 0)
    held = result["views"][1]
    iq[:study.N] = 0
    assert study.assay(iq, 0, plans, factor)["views"] == ([], held)


def test_empty_with_two_confident_views_is_counted_as_a_proposal_not_a_factor():
    fake = dict(views=([(0, 10_000, 1)], [(study.PERIOD-2, 10000, 1)]), paired_intersections=1, full=None)
    counts = study.count_panel([dict(scans=[fake])])["full_primary"]
    assert counts == {"empty": 1, "empty_either_emits": 1, "empty_views_agree": 1}


def test_zero_cost_budget_charges_positive_misses_after_granting_every_empty():
    result = {"dense": {"summary": {"short": dict(positive=20, supported_either=10, supported_both=5)}}}
    profile = {"profile": {"grouped": {kind: {"stage_ns_per_lane": dict(lag_timing=2, carrier_grid=3)}
                                        for kind in ("positive", "empty")}}}
    transfer = {"projections": {"DS30-0008": dict(positive=6000, short_calls=10000,
        projections={"all_timing_and_carrier_grids": {"cpu_saved": 5.0}})}}
    price = study.budget(result, profile, transfer)
    assert price["assumed_zero_cost_positive_grant_all_empty_cpu_s"] == pytest.approx(3.5)
    assert price["assumed_zero_cost_positive_both_all_empty_cpu_s"] == pytest.approx(2.75)
    assert price["positive_recall_needed_80us_all_empty"] > price["positive_recall_needed_free_all_empty"]
