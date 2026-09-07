"""Truth isolation, identity ambiguity, chronological scoring and regional geometry."""

import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    ObservationArc,
    Region,
    ScoreConfig,
    centered_errors,
    fit_local_mode,
    score_states,
    template_score,
)

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "regional_replay", ROOT / "tools/replay_regional_doppler.py"
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def arc_fixture():
    t = np.tile(np.arange(12.0), 2)
    y = -1000 * t + 2 * t**2 + np.repeat([12345.0, -54321.0], 12)
    return ObservationArc(t, y, np.repeat([0, 1], 12), t < 7)


def test_offsets_preserve_rf_normalized_shape():
    arc = arc_fixture()
    rf = np.repeat([10.7096875e9, 10.9403125e9], 12)
    raw = arc.frequency_hz * rf / REFERENCE_RF_HZ
    normalized = raw * REFERENCE_RF_HZ / rf
    corrected = ObservationArc(arc.time_s, normalized, arc.segment, arc.training)
    prediction = -1000 * arc.time_s + 2 * arc.time_s**2
    train, test = centered_errors(corrected, prediction)
    assert max(train, test) < 1e-15
    wrong = ObservationArc(arc.time_s, raw, arc.segment, arc.training)
    assert centered_errors(wrong, prediction)[1] > 1000


def test_holdout_changes_neither_location_score_nor_identity():
    arc = arc_fixture()
    models = np.array([[-1000 * arc.time_s + 2 * arc.time_s**2, -900 * arc.time_s + arc.time_s**2]])
    visible = np.ones((1, 2), bool)
    first = template_score(arc, models, visible, 10)
    y = arc.frequency_hz.copy()
    y[~arc.training] += 1e5
    second = template_score(
        ObservationArc(arc.time_s, y, arc.segment, arc.training), models, visible, 10
    )
    np.testing.assert_array_equal(first["train_logbf"], second["train_logbf"])
    np.testing.assert_array_equal(first["best_index"], second["best_index"])
    assert first["heldout_logbf"][0] > second["heldout_logbf"][0]


def test_invisible_and_missing_satellites_do_not_renormalize_identity_prior():
    arc = arc_fixture()
    one = np.array([[-1000 * arc.time_s + 2 * arc.time_s**2]])
    first = template_score(arc, one, np.ones((1, 1), bool), 100)
    second = template_score(arc, np.repeat(one, 2, axis=1), np.array([[True, False]]), 100)
    np.testing.assert_allclose(first["train_logbf"], second["train_logbf"])
    none = template_score(arc, one, np.zeros((1, 1), bool), 100)
    assert none["train_logbf"][0] == 0
    assert none["heldout_logbf"][0] == pytest.approx(0, abs=1e-12)
    assert none["signal_weight"][0] == 0


def test_equal_candidate_modes_remain_equal_and_offset_invariant():
    arc = arc_fixture()
    models = np.array([[-1000 * arc.time_s + 2 * arc.time_s**2]])
    models = np.concatenate([models, models + 87654321], axis=0)
    result = template_score(arc, models, np.ones((2, 1), bool), 100)
    assert result["train_logbf"][0] == pytest.approx(result["train_logbf"][1])


def synthetic_states(region, t, count=9):
    unit = region.points([0], [0]).ecef_km[0]
    unit = unit / np.linalg.norm(unit)
    east = np.array(
        [-np.sin(np.deg2rad(region.longitude_deg)), np.cos(np.deg2rad(region.longitude_deg)), 0]
    )
    north = np.cross(unit, east)
    positions, velocities = [], []
    for i in range(count):
        direction = east * np.cos(i * 0.71) + north * np.sin(i * 0.71)
        phase = 0.0011 * t + (i % 3 - 1) * 0.12
        positions.append(
            6928 * (np.cos(phase)[:, None] * unit + np.sin(phase)[:, None] * direction)
        )
        velocities.append(
            6928 * 0.0011 * (-np.sin(phase)[:, None] * unit + np.cos(phase)[:, None] * direction)
        )
    return np.array(positions), np.array(velocities)


def test_regional_search_recovers_unknown_identity_synthetic_position():
    region = Region(20.0, 30.0)
    grid = region.grid(50)
    truth = region.points([175.0], [-225.0]).ecef_km[0]
    t = np.linspace(-35, 35, 24)
    p, v = synthetic_states(region, t)
    score = np.zeros(len(grid))
    for satellite in (1, 4, 7):
        unit = p[satellite] - truth
        unit /= np.linalg.norm(unit, axis=-1)[:, None]
        y = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(unit * v[satellite], axis=-1) + 30000
        arc = ObservationArc(t, y, np.zeros(len(t)), t < 8)
        result = score_states(arc, p, v, grid, len(p), ScoreConfig(signal_sigma_hz=50))
        score += result["train_logbf"]
    best = np.argmax(score)
    assert grid.east_km[best] == pytest.approx(175)
    assert grid.north_km[best] == pytest.approx(-225)


def test_region_surface_and_bounds_not_flat_tangent_plane():
    region = Region(37.8, -122.3)
    grid = region.grid(25)
    assert len(grid) == 1600
    centre = region.points([0], [0])
    assert centre.latitude_deg[0] == pytest.approx(37.8)
    assert centre.longitude_deg[0] == pytest.approx(-122.3)
    assert np.ptp(np.linalg.norm(grid.ecef_km, axis=-1)) < 5
    with pytest.raises(ValueError, match="outside"):
        region.points([501], [0])
    with pytest.raises(ValueError, match="work bound"):
        region.grid(0.01)


def test_continental_region_and_batched_projection_match_direct_geometry():
    region = Region(43.6914344, -106.8991205, 5000.0, 5000.0)
    grid = region.grid(1000.0)
    assert len(grid) == 25
    assert np.max(np.abs(grid.latitude_deg)) <= 90
    with pytest.raises(ValueError, match="dimensions"):
        Region(0, 0, 5001, 5000)
    arc = arc_fixture()
    p, v = synthetic_states(region, arc.time_s)
    delta = p[None] - grid.ecef_km[:, None, None]
    unit = delta / np.linalg.norm(delta, axis=-1)[..., None]
    prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(unit * v[None], axis=-1)
    visible = np.min(
        np.sum(unit * grid.up[:, None, None], axis=-1)[..., arc.training], axis=-1
    ) >= np.sin(np.deg2rad(-1.0))
    direct = template_score(arc, prediction, visible, len(p))
    batched = score_states(arc, p, v, grid, len(p))
    for key in direct:
        # At the centre, three rotationally symmetric synthetic orbits are
        # exactly degenerate. Floating-point order may select another tied ID;
        # the mixture evidence and selected residual must still agree.
        if key == "best_index":
            continue
        np.testing.assert_allclose(direct[key], batched[key], atol=1e-6, rtol=1e-8, equal_nan=True)


def test_observation_adapter_ignores_site_and_prior_identity_fields():
    row = {
        "tracklet_id": "a",
        "t_s": list(range(10)),
        "y_hz": list(range(10)),
        "candidate_ids": list(range(10)),
        "actual_rf_hz": 10.7e9,
        "channel": 1,
    }
    doc = {"series": [row], "episodes": [{"episode_id": "e", "members": ["a"]}]}
    clean = replay.load_observations(doc)
    doc["truth"] = {"latitude": -70, "longitude": 100}
    doc["observer"] = {"latitude": 0, "longitude": 0}
    doc["episodes"][0]["match"] = {"norad": 999999, "tau_s": 999}
    poisoned = replay.load_observations(doc)
    np.testing.assert_array_equal(clean[0][1].frequency_hz, poisoned[0][1].frequency_hz)
    assert clean[0][0] == poisoned[0][0]
    doc["episodes"].append({"episode_id": "duplicate", "members": ["a"]})
    with pytest.raises(ValueError, match="duplicate"):
        replay.load_observations(doc)


def test_no_known_site_imports_in_solver_or_adapter():
    paths = [
        ROOT / "src/leo/analysis/research/regional_doppler.py",
        ROOT / "tools/replay_regional_doppler.py",
        ROOT / "tools/refine_regional_grid.py",
        ROOT / "tools/polish_regional_doppler.py",
    ]
    forbidden = (
        "evaluate_scan_pnt",
        "sky.sites",
        "blinded_position_evaluation",
        "sqlalchemy",
        "psycopg",
    )
    for path in paths:
        tree = ast.parse(path.read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [
            a.name for node in ast.walk(tree) if isinstance(node, ast.Import) for a in node.names
        ]
        assert not any(word in item for item in imports for word in forbidden)
        assert "37.858988" not in path.read_text()
        assert "37.8490428024417" not in path.read_text()
        assert "-122.48567437412359" not in path.read_text()


def test_compact_publication_verification_never_silently_skips_missing_evidence(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "regional_verify", ROOT / "tools/verify_regional_doppler.py"
    )
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    intermediate = {"scan-hop-123abc.npz": "unused"}
    with pytest.raises(FileNotFoundError):
        verify.verify_run_files(tmp_path, intermediate)
    assert verify.verify_run_files(tmp_path, intermediate, published_only=True) == [
        "scan-hop-123abc.npz"
    ]
    with pytest.raises(FileNotFoundError):
        verify.verify_run_files(tmp_path, {"result.json": "missing"}, published_only=True)
    path = tmp_path / "result.json"
    path.write_text("{}")
    assert verify.verify_run_files(tmp_path, {path.name: verify.sha(path)}) == []
    with pytest.raises(AssertionError):
        verify.verify_run_files(tmp_path, {path.name: "changed"}, published_only=True)


def test_refinement_proposals_ignore_heldout_maps_and_evaluation_fields(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "regional_refine", ROOT / "tools/refine_regional_grid.py"
    )
    refine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(refine)
    result = {
        "complete": True,
        "region": {"width_km": 5000, "height_km": 5000},
        "altitude_m": 0,
    }
    (tmp_path / "result.json").write_text(json.dumps(result))
    np.savez(tmp_path / "grid.npz", east_km=[-100, 100, -100, 100], north_km=[-100, -100, 100, 100])
    np.savez(tmp_path / "accumulated.npz", train=[10, 0, 0, 0], heldout=[0, 0, 0, 999])
    refine.propose(tmp_path, tmp_path / "first.json", modes=1, divisions=2)
    result["evaluation_truth"] = {"latitude_deg": -70, "longitude_deg": 100}
    (tmp_path / "result.json").write_text(json.dumps(result))
    np.savez(tmp_path / "accumulated.npz", train=[10, 0, 0, 0], heldout=[0, 999, 0, 0])
    refine.propose(tmp_path, tmp_path / "second.json", modes=1, divisions=2)
    first = json.loads((tmp_path / "first.json").read_text())
    second = json.loads((tmp_path / "second.json").read_text())
    for key in ("east_km", "north_km", "selected_centres_km"):
        assert first[key] == second[key]
    assert first["selected_centres_km"] == [[-100, -100]]
    assert first["training_map_digest"] != second["training_map_digest"]


def test_regional_catalogue_excludes_future_epochs_and_non_starlink(monkeypatch):
    region = Region(43.6914344, -106.8991205, 5000, 5000)
    catalogue = SimpleNamespace(
        names=("STARLINK-1", "STARLINK-2", "STARLINK-3", "UNRELATED"),
        element_epoch_utc_ns=lambda: (99, 100, 101, 90),
    )
    called = []

    def states(cat, indices, reference_ns, times, **kwargs):
        called.extend(indices)
        unit = region.points([0], [0]).up[0]
        p = np.broadcast_to(6928 * unit, (len(indices), len(times), 3))
        return p, np.zeros_like(p), np.array(indices)

    monkeypatch.setattr(replay, "state_arrays", states)
    selected, count = replay.regional_catalogue(catalogue, 100, region)
    assert called == [0]
    assert count == 1
    assert selected.tolist() == [0]


def test_fine_continental_proposal_avoids_full_grid_and_refuses_late_catalogue(tmp_path):
    points = tmp_path / "points.json"
    points.write_text(json.dumps({"east_km": [0, 1], "north_km": [0, 1]}))
    (tmp_path / "inventory.json").write_text(
        json.dumps(
            {"scans": [{"included": True, "session_id": "late", "reference_utc_ns": 10**12}]}
        )
    )
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/late.json").write_text(
        json.dumps({"inventory": {"reference_utc_ns": 10**12, "tle_collected_ns": 10**12}})
    )
    args = SimpleNamespace(
        output=tmp_path / "output",
        evidence=tmp_path,
        max_per_partition=6,
        center_lat=43.6914344,
        center_lon=-106.8991205,
        region_size_km=5000,
        spacing_km=1,
        altitude_m=0,
        shifted_grid=False,
        points=points,
        sigma_hz=250,
        effective_count=6,
        scan_limit=None,
        clock_s=0,
        individual_sources=False,
    )
    # A full grid at this requested spacing would exceed the work bound. Only
    # the two declared proposal points should be constructed, before causality
    # rejects the intentionally late snapshot without attempting propagation.
    with pytest.raises(ValueError, match="noncausal catalogue snapshot"):
        replay.run(args)
    assert len(np.load(args.output / "grid.npz")["east_km"]) == 2


def test_refuses_nonchronological_or_invalid_data():
    with pytest.raises(ValueError, match="precede"):
        ObservationArc(
            np.arange(6.0), np.arange(6.0), np.zeros(6), np.array([1, 0, 1, 0, 1, 0], bool)
        )
    with pytest.raises(ValueError, match="finite"):
        Region(float("nan"), 0)
    with pytest.raises(ValueError, match="ordered"):
        ScoreConfig(signal_sigma_hz=-1)


def test_local_polish_is_truth_free_and_heldout_invariant():
    region = Region(20.0, 30.0)
    t = np.linspace(-35, 35, 30)
    group = np.repeat(np.arange(3), len(t))
    training = np.tile(t < 8, 3)

    def predict(x, shifts):
        receiver = region.points([x[0]], [x[1]]).ecef_km[0]
        values = []
        for g, satellite in enumerate((1, 4, 7)):
            p, v = synthetic_states(region, t + shifts[g])
            delta = p[satellite] - receiver
            values.extend(
                -REFERENCE_RF_HZ
                / LIGHT_KM_S
                * np.sum(delta * v[satellite], axis=-1)
                / np.linalg.norm(delta, axis=-1)
            )
        return np.array(values)

    y = predict([175.0, -225.0], np.zeros(3)) + np.repeat([1e5, -2e5, 3e5], len(t))
    args = (group, training, group, predict, [180.0, -220.0], [-500.0, -500.0], [500.0, 500.0])
    first = fit_local_mode(y, *args)
    np.testing.assert_allclose(first["position_km"], [175.0, -225.0], atol=1e-3)
    altered = y.copy()
    altered[~training] += 1e5
    second = fit_local_mode(altered, *args)
    np.testing.assert_allclose(first["position_km"], second["position_km"], atol=1e-8)
    assert second["heldout_rms_hz"] > 99900
    assert first["converged"]


def test_local_orbit_corrections_are_bounded_shared_and_penalized():
    t = np.tile(np.linspace(-1, 1, 30), 3)
    group = np.repeat(np.arange(3), 30)
    training = t < 0.4

    def predict(x, tau):
        return 1e4 * (x[0] * t + x[1] * t**2 + tau[group] * t**3)

    y = predict([0.5, -0.7], np.array([0.2, -0.3, 3.0]))
    result = fit_local_mode(
        y,
        group,
        training,
        group,
        predict,
        [0.0, 0.0],
        [-5.0, -5.0],
        [5.0, 5.0],
        fit_orbit_time=True,
        orbit_sigma_s=1.0,
        orbit_bound_s=2.0,
    )
    assert np.max(np.abs(result["orbit_times_s"])) <= 2.0
    assert len(result["orbit_times_s"]) == 3
    assert all(
        b["objective"] <= a["objective"] + 1e-8
        for a, b in zip(result["history"], result["history"][1:], strict=False)
    )
