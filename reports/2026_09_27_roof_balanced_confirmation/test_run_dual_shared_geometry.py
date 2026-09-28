import copy

import pytest

import run_dual_shared_geometry as runner


def scores(value=1.):
    return {"D": value, "D_plus_detection": 2., "D_plus_geometry": 3.,
            "D_plus_reversed_geometry": 4.}


def fixture():
    point = {"east_km": 0., "north_km": 0., "latitude_deg": 1., "longitude_deg": 2.,
             "variant_scores": {"old": scores(), "mixture": scores(), "shared": scores()}}
    saved = {"grid_count": 1, "point_components": [point]}
    current = {**point, "variant_scores": {name: scores() for name in runner.VARIANTS},
               "quadrature_maximum_candidate_loglik_absolute_difference": {
                   name: 1e-5 for name in runner.VARIANTS}}
    return saved, [current]


def test_parity_checks_mapping_D_finiteness_coordinates_and_quadrature():
    saved, rows = fixture(); assert runner.parity_report(saved, rows)["passed"]
    bad = copy.deepcopy(rows); bad[0]["variant_scores"]["detection"]["D_plus_geometry"] += 2e-7
    with pytest.raises(ValueError, match="score parity"): runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows); bad[0]["variant_scores"]["dual"]["D"] += 2e-12
    with pytest.raises(ValueError, match="Doppler-only"): runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows); bad[0]["variant_scores"]["dual"]["D"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"): runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows); bad[0]["latitude_deg"] += 1e-5
    with pytest.raises(ValueError, match="coordinate"): runner.parity_report(saved, bad)
    bad = copy.deepcopy(rows)
    bad[0]["quadrature_maximum_candidate_loglik_absolute_difference"]["dual"] = .002
    with pytest.raises(ValueError, match="quadrature"): runner.parity_report(saved, bad)


def test_deterministic_selection_and_real_ratio_binding():
    _saved, rows = fixture(); other = copy.deepcopy(rows[0]); other["east_km"] = -1.
    assert runner.select_min([rows[0], other], "dual")["east_km"] == -1.
    receipt, tau = runner.ratio_effect_binding()
    assert all(receipt["advancement_checks"].values()) and 0 < tau < 4
