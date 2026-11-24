from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from four_frame_aperture import choose_schedule, coherent_power, geometry, origin, required_short_fraction, span, timing_gates


def test_farthest_symmetric_schedule_preserves_native_groups():
    assert choose_schedule() == (0, 1, 12, 13)
    profile = geometry()
    stock, wide = profile["contiguous5"], profile["distributed4"]
    assert wide["confirmation_groups"] == [[0, 12], [1, 13]]
    assert wide["physical_parity_counts"] == {"0": 2, "1": 2}
    assert wide["coherent_equal_snr_information"]/stock["coherent_equal_snr_information"] == pytest.approx(14.5, rel=1e-5)
    assert wide["phase_free_equal_snr_information_scale"] == .8


def test_dependencies_keep_late_gate_and_exact_fir_tile_origins():
    assert origin(13) == 173333
    assert origin(13, stride=4) == 43333
    wide = span(choose_schedule(), 200000)
    assert wide["latest_confirmation_exclusive"] == 199777
    assert wide["necessary_fir_outputs"] == 16152
    assert wide["cautious_sample_ranges"] == [(0, 39793), (159984, 199793)]
    with pytest.raises(ValueError):
        span(choose_schedule(), 80000)


def test_coherent_sidelobes_are_not_reduced_to_one_frequency_neighborhood():
    frames = choose_schedule()
    assert coherent_power(frames, 0.) == 1.
    assert coherent_power(frames, 62.5) > .93
    assert coherent_power(frames, 750.) > .999999
    assert coherent_power(frames, 375.) < 1e-7
    assert coherent_power(frames, -62.5) == coherent_power(frames, 62.5)


def test_absolute_budget_and_reciprocal_median_recompute_on_measured_boundaries():
    attempts,short = {},{}
    for case,stock,candidate,native_short in (("a",10.,5.5,1.),("b",20.,15.,3.),("c",40.,20.,.5)):
        attempts[case,"installed"] = {"case":case,"elapsed_s":stock}
        attempts[case,"successor"] = {"case":case,"elapsed_s":candidate}
        short[case] = {"elapsed_s":{"short":native_short}}
    ceiling = timing_gates(attempts,short,1.,clock="elapsed_s")
    assert ceiling["through_exit_s"] == 36.
    assert ceiling["median_paired_speedup"] == pytest.approx(40/19.5)
    assert ceiling["passes"]["2.0"] == {"summed":False,"median_paired":True}
    assert required_short_fraction(attempts,short,"elapsed_s",2.,"summed") is None
    assert required_short_fraction(attempts,short,"elapsed_s",2.,"median_paired") == pytest.approx(.5)
    with pytest.raises(ValueError):
        timing_gates(attempts,{"a":short["a"]},1.,clock="elapsed_s")
