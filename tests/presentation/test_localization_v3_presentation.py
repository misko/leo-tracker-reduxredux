from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from leo.presentation import localization_v3 as presentation


def fixture(monkeypatch):
    region = SearchRegion((10.0, 20.0))
    track = dict(observation_ids=["a", "b"], key="track")
    p = SimpleNamespace(
        scan=SimpleNamespace(tracks=[track], search_region=region),
        rows=[dict(candidate_norad=123)],
        members=[0],
        slices=[slice(0, 2)],
        calculate=lambda x: dict(conditional_residual_hz=np.array([3.0, 5.0])),
    )
    context = dict(
        problems={a: (p, np.array([0.0, 0.0])) for a in ("c0", "fitted_c")},
        entries=[],
        families=[],
        scan=p.scan,
    )
    observations = [
        dict(observation_id=oid, receiver=1, channel=1, time_s=float(k), measured_cfo_hz=100.0 + k)
        for k, oid in enumerate(["a", "b", "unused"])
    ]
    owners = {a: {"a": 123, "b": 123} for a in ("c0", "fitted_c")}
    expected = {a: dict(endpoint_latlon=[10.0, 20.0], objective=42.0) for a in owners}
    monkeypatch.setattr(presentation, "objective", lambda p, d, x: 42.0)
    monkeypatch.setattr(presentation, "calibrated_lanes", lambda *args: ("lanes",))
    return context, owners, expected, observations, [track]


def test_preparation_preserves_owners_native_observations_and_reference_frame(monkeypatch):
    values = fixture(monkeypatch)
    packet = presentation.prepare_packet(
        *values, selected_model="selected", position_path=dict(stages=[]), include_grid=False
    )
    assert packet["observations"] is values[3]
    assert [r["observation_id"] for r in packet["rows"]["fitted_c"]] == ["a", "b"]
    assert [r["prediction_hz"] for r in packet["rows"]["fitted_c"]] == [97.0, 96.0]
    assert packet["arms"]["c0"]["associated_percent"] == 100 * 2 / 3
    assert packet["arms"]["c0"]["owner_sha256"] == presentation.owner_digest(values[1]["c0"])
    assert packet["objective_replay"] == dict(c0=0.0, fitted_c=0.0)
    assert "position_grid" not in packet


@pytest.mark.parametrize("fault", ["position", "objective", "missing_owner", "duplicate_native"])
def test_stale_or_incomplete_evidence_cannot_be_rendered(monkeypatch, fault):
    values = fixture(monkeypatch)
    if fault == "position":
        values[2]["c0"]["endpoint_latlon"][0] += 1.0
    elif fault == "objective":
        values[2]["c0"]["objective"] += 1.0
    elif fault == "missing_owner":
        values[1]["fitted_c"]["unused"] = 123
    else:
        values[3].append(values[3][0])
    with pytest.raises(ValueError):
        presentation.prepare_packet(
            *values, selected_model="selected", position_path={}, include_grid=False
        )


@pytest.mark.parametrize('parallel', [False, True])
def test_grid_uses_declared_region_and_same_fixed_fit_in_both_arms(monkeypatch, parallel):
    from leo.operations.localization_v3_parallel import map_grid_batches
    values = fixture(monkeypatch)
    packet = presentation.prepare_packet(
        *values, selected_model="selected", position_path={}, clock=lambda: 0.0, grid_seconds=300.0,
        map_grid_batches=map_grid_batches if parallel else None,
    )
    grid = packet["position_grid"]
    assert grid["complete"] and grid["maximum_seconds"] == 300.0
    assert grid["region_center"] == [10.0, 20.0]
    assert grid["points"][0]["latlon"] == [10.0, 20.0]
    assert all(p["scores"] == dict(c0=42.0, fitted_c=42.0) for p in grid["points"])
