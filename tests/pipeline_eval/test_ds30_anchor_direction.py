import json
from math import cos, radians

import pytest

from leo.contracts.position_grid import ARMS, binding
from reports.ALGO08.v3.ds30_anchor_direction import canonical, digest, pair_geometry, publication


def surface(endpoint=(0.0, 0.0), *, axes=(0.2, 2.0), additive=1000.0, missing=None):
    a, b = endpoint
    latlon = lambda x, y: [y/111.0, x/111.32]
    samples = []
    for east in range(-3, 4):
        for north in range(-3, 4):
            x, y = a+east/2, b+north/2
            val = additive + (axes[0]*(x-a)**2 + axes[1]*(y-b)**2)/2
            samples.append(dict(east_km=x, north_km=y, latlon=latlon(x, y),
                                scores=dict.fromkeys(ARMS, None if (x, y) == missing else val)))
    return dict(points=samples, region_center=[0.0, 0.0], box_width_km=25.0, local_size=7, local_half_width_km=1.5,
                endpoints=dict.fromkeys(ARMS, [a, b]), endpoint_latlon=dict.fromkeys(ARMS, latlon(a, b)))


def test_shared_points_and_exact_cross_ignore_arbitrary_objective_offsets():
    first, second = surface(), surface((1., 0.), additive=9000.)
    comparison = pair_geometry(first, second, "c0")
    assert comparison["shared_samples"] == 35
    assert comparison["shared_within_scale"] == 35
    assert comparison["best_common_deltas"] == pytest.approx([.025, .025])
    for result in (comparison["first"], comparison["second"]):
        assert result["exact_cross_delta"] == pytest.approx(.1)
        assert result["local_cross"] is None
        for stencil in result["curvatures"]:
            assert stencil["principal_curvatures"] == pytest.approx([.2, 2.])
            assert stencil["directional_curvature"] == pytest.approx(.2)
            assert stencil["quadratic_delta"] == pytest.approx(.1)


def test_interpolation_uses_recorded_cell_and_reports_missing_or_outside():
    cross = surface((.75, .25))
    result = pair_geometry(surface(), cross, "fitted_c")["first"]
    assert result["exact_cross_delta"] is None
    assert result["local_cross"]["corner_deltas"] == pytest.approx([.025, .1, .275, .35])
    assert result["local_cross"]["bilinear_delta"] == pytest.approx(.1875)
    incomplete = pair_geometry(surface(missing=(1., .5)), cross, "fitted_c")["first"]
    assert incomplete["opposing_endpoint_in_local_patch"]
    assert incomplete["local_cross"] is None
    far = pair_geometry(surface(), surface((3., 0.)), "fitted_c")["first"]
    assert far["opposing_endpoint_in_offer"]
    assert not far["opposing_endpoint_in_local_patch"]
    assert far["exact_cross_delta"] is None and far["local_cross"] is None


def test_translated_grids_compare_geographic_points_and_preserve_unresolved_targets():
    first = surface()
    second = surface((.25, .25))
    declat, declon = 2./111., 3./111.32
    second["region_center"] = [declat, declon]
    for row in second["points"]:
        row["latlon"] = [declat+row["north_km"]/111., declon+row["east_km"]/(111.32*cos(radians(declat)))]
    second["endpoint_latlon"] = dict.fromkeys(ARMS, second["points"][24]["latlon"])
    comparison = pair_geometry(first, second, "c0")
    assert comparison["shared_samples"] == 0
    assert comparison["best_common_deltas"] is None
    assert comparison["first"]["direction"] != comparison["second"]["direction"]
    assert comparison["first"]["displacement_km"] == pytest.approx((3.25**2+2.25**2)**.5, abs=1e-6)


def test_grid_digest_and_owner_binding_must_match_receipts(tmp_path):
    def write(path, body):
        data = json.dumps(body).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return digest(data)

    grid = surface()
    run = "case"
    region = dict(center=[0.0, 0.0], width_km=25.)
    terminal_pin = write(tmp_path/"fast-scan-automatic-work"/run/"terminal.json", dict(
        session_id="session", decision="ok", region=region, native_sha256="n", arms=dict.fromkeys(ARMS, {"latlon": [0.0, 0.0]})))
    receipt = dict(run_id=run, terminal_sha256=terminal_pin, region=region, session_id="session", decision="complete")
    manifest = dict(run_id=run, schema_version=3, model_version="test", terminal_sha256=terminal_pin, raw_authority="a",
                    region=region, input_sha256="n", arms=dict.fromkeys(ARMS, dict(
                        owner_sha256="o", endpoint_latlon=[0., 0.], associated_points=1, tracks=1, satellites=1)),
                    artifacts=[dict(name="position", sha256="p")], objective_replay=dict.fromkeys(ARMS, 0.0))
    grid.update(schema_version=1, kind="conditional-position-grid", matched_c_grid=True,
                binding=binding(manifest), conditioning="published satellite ownership and phase linearization fixed",
                nuisance_model="unchanged published marginal likelihood", endpoint_objective_replay=manifest["objective_replay"],
                complete=True, evaluated_points=49, planned_points=49)
    folder = tmp_path/"fast-scan-standard-v2"/run/"final-error-v7"
    write(folder/"manifest.json", manifest)
    envelope = dict(document=grid, sha256=canonical(grid))
    pin = write(folder/"position-grid.json", envelope)
    assert grid == publication(tmp_path, receipt, "n", dict.fromkeys(ARMS, "o"), "p", pin, "a")[0]
    with pytest.raises(ValueError, match="does not bind"):
        publication(tmp_path, receipt, "n", dict.fromkeys(ARMS, "wrong"), "p", pin, "a")
    with pytest.raises(ValueError, match="Changed archived product"):
        publication(tmp_path, receipt, "n", dict.fromkeys(ARMS, "o"), "p", "wrong", "a")
