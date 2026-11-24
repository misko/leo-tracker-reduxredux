import json

import pytest

from leo.contracts.position_grid import binding
from reports.ALGO08.v3.ds30_grid_triage import (
    ARMS, CURVATURE_LIMIT, OFFER, canonical, cost_and_fixes, digest, grid_information, ranked, scientific_grid, tau_b,
)


def test_rank_direction_and_ties():
    assert tau_b([(1, 1), (2, 2), (3, 3)]) == 1
    assert tau_b([(1, 3), (2, 2), (3, 1)]) == -1
    assert tau_b([(1, 1), (1, 2), (2, 3)]) == pytest.approx(2 / 6**.5)
    assert tau_b([(1, 2), (1, 2)]) is None


def case(label, c0, free, stock_error, candidate_error, original_information=1.0):
    def role(error, elapsed, cpu):
        return dict(c0_error_km=error, fitted_c_error_km=error, elapsed_s=elapsed, cpu_s=cpu)

    return dict(
        case=label, candidate_grid={"information": {"c0": c0, "fitted_c": free}},
        installed_grid={"information": dict.fromkeys(ARMS, original_information)},
        installed=role(stock_error, 10, 8), successor=role(candidate_error, 4, 3),
    )


def test_whole_retry_makes_one_paid_choice_for_both_arms_withholds_included():
    rows = [
        case("weak_fitted", 20, CURVATURE_LIMIT, None, .7),
        case("strong_or_missing", 20, None, .8, 1.2),
        case("weak_c0", -1, 20, .8, 1.4),
    ]
    paid = cost_and_fixes(rows)
    assert paid["retried"] == ["weak_fitted", "weak_c0"]
    assert paid["clocks"]["elapsed_s"]["full_retry_s"] == 20
    assert paid["clocks"]["elapsed_s"]["total_s"] == 32
    assert paid["clocks"]["elapsed_s"]["mean_retry_budget_s"] == 9
    assert paid["clocks"]["elapsed_s"]["mean_retry_budget_for_half_s"] == 1.5
    for arm in ARMS:
        assert paid["results"][arm]["successor"]["fixes"] == 3
        assert paid["results"][arm]["with_retry"]["fixes"] == 2
        assert paid["results"][arm]["with_retry"]["within_1km"] == 1


def test_rank_uses_only_shared_scored_fixes_and_keeps_enrollment_ties():
    result = ranked([
        case("first", 2, 6, .4, .9, 3), case("second", 2, 6, .6, 1.4, None),
        case("strong", 8, 8, .8, .9, 6), case("pending", 1, 5, None, 10),
        case("missing", None, 7, .2, 10),
    ], "c0")
    assert result["n"] == 3
    assert result["weakest_third"]["cases"] == ["first"]
    assert result["tau_b"]["delta"] > 0
    assert result["uncertainty_comparison"] == {"n": 2, "tau_b": 1}


def test_signed_grid_requires_exact_fit_and_original_offer(tmp_path):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(value).encode()
        path.write_bytes(body)
        return digest(body)

    run, centre = "arbitrary_test", [0., 0.]
    offer = {"center": centre, "width_km": 25.}
    coordinates = dict.fromkeys(ARMS, centre)
    arm_values = dict.fromkeys(ARMS, {"latlon": centre})
    terminal = dict(region=offer, native_sha256="input", decision="ok", session_id="session", arms=arm_values)
    terminal_pin = write(tmp_path/"fast-scan-automatic-work"/run/"terminal.json", terminal)
    receipt = dict(run_id=run, session_id="session", terminal_sha256=terminal_pin, region=offer)
    manifest = dict(run_id=run, terminal_sha256=terminal_pin, schema_version=3, model_version="model",
                    region=offer, raw_authority="authority", input_sha256="input",
                    arms=dict.fromkeys(ARMS, {"endpoint_latlon": centre, "owner_sha256": "owners"}),
                    artifacts=[{"name": "position", "sha256": "position"}])
    points = [dict(east_km=x, north_km=y, latlon=[y/111., x/111.32],
                   scores={"c0": 10+x*x+2*y*y, "fitted_c": 20+3*x*x+2*y*y})
              for x in (-.5, 0., .5) for y in (-.5, 0., .5)]
    grid = dict(schema_version=1, kind="conditional-position-grid", matched_c_grid=True,
                conditioning="published satellite ownership and phase linearization fixed", binding=binding(manifest),
                points=points, region_center=centre, box_width_km=25., endpoint_latlon=coordinates, endpoints=coordinates,
                complete=True, evaluated_points=9, planned_points=9, endpoint_objective_replay=dict.fromkeys(ARMS, 0.))
    result = dict(outcome="complete", native_sha256="input", raw_identity={"region_sha256": OFFER},
                  evidence=dict(receipt=receipt, raw_authority="authority", artifacts=manifest["artifacts"], arms=arm_values,
                                owners=dict.fromkeys(ARMS, "owners"), scientific_digests={"grid": canonical(scientific_grid(grid))}))
    folder = tmp_path/"fast-scan-standard-v2"/run/"final-error-v7"
    write(folder/"manifest.json", manifest)
    path = folder/"position-grid.json"
    write(path, dict(document=grid, sha256=canonical(grid)))
    prediction = grid_information(result, tmp_path, offer)
    assert prediction["state"] == "bound"
    assert prediction["information"] == {"c0": 2., "fitted_c": 4.}
    points[0]["scores"]["c0"] += 1
    write(path, dict(document=grid, sha256=canonical(grid)))
    assert grid_information(result, tmp_path, offer)["state"] == "unbound_numerical_grid"
    assert grid_information(result, tmp_path, offer | {"width_km": 50.})["state"] == "different_offer"
