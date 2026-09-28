import copy

import pytest

import run_shared_geometry_replay as runner


def scores(value=1.):
    return {"D": value, "D_plus_detection": 2., "D_plus_geometry": 3.,
            "D_plus_reversed_geometry": 4.}


def fixture():
    point = {"east_km": 0., "north_km": 0., "latitude_deg": 1., "longitude_deg": 2.,
             "variant_scores": {"old": scores(), "mean": scores(), "mixture": scores()}}
    saved = {"grid_count": 1, "point_components": [point]}
    current = {**point, "variant_scores": {"old": scores(), "mixture": scores(),
                                             "shared": scores()},
               "quadrature_maximum_candidate_loglik_absolute_difference": {
                   "old": 0., "mixture": 0., "shared": 1e-5}}
    return saved, [current]


def test_parity_checks_saved_variants_D_and_quadrature():
    saved, rows = fixture(); assert runner.parity_report(saved, rows)["passed"]
    bad = copy.deepcopy(rows); bad[0]["variant_scores"]["mixture"]["D_plus_geometry"] += 2e-7
    with pytest.raises(ValueError, match="score parity"):
        runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows); bad[0]["variant_scores"]["shared"]["D"] += 2e-12
    with pytest.raises(ValueError, match="Doppler-only"):
        runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows)
    bad[0]["quadrature_maximum_candidate_loglik_absolute_difference"]["shared"] = .002
    with pytest.raises(ValueError, match="quadrature"):
        runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows); bad[0]["latitude_deg"] += 1e-5
    with pytest.raises(ValueError, match="coordinate"):
        runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows); bad[0]["variant_scores"]["shared"]["D"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows)
    bad[0]["quadrature_maximum_candidate_loglik_absolute_difference"]["shared"] = -1.
    with pytest.raises(ValueError, match="quadrature receipt"):
        runner.parity_report(saved, bad)


def test_selection_is_deterministic_score_east_north():
    _saved, rows = fixture(); other = copy.deepcopy(rows[0]); other["east_km"] = -1.
    assert runner.select_min([rows[0], other], "shared")["east_km"] == -1.


def test_random_effect_binding_accepts_complete_real_artifact():
    receipt, sigma = runner.random_effect_binding()
    assert receipt["advancement_checks"] and all(receipt["advancement_checks"].values())
    assert 0 < sigma < 8
