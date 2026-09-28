import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_local_grid as local


def test_full_grid_has_289_points_and_contains_center():
    points = local.local_grid(0., 0., 500.)
    assert len(points) == 289
    assert (0., 0.) in points
    assert len(set(points)) == len(points)


def test_grid_is_clipped_to_prior_disk():
    points = local.local_grid(99., 0., 100.)
    assert 0 < len(points) < 289
    assert (99., 0.) in points
    assert all(east**2 + north**2 <= 100**2 + 1e-8 for east, north in points)


def test_symmetric_tie_selection_is_deterministic():
    rows = [dict(east_km=east, north_km=north,
                 scores={"D": 1., "D_plus_geometry": 1.})
            for east, north in ((1., 0.), (-1., 0.), (0., 1.), (0., -1.))]
    assert local.select_min(rows, "D")["east_km"] == -1.
    assert local.select_min(rows, "D")["north_km"] == 0.


def seed_payload(session_id="scan", *, finished=True, contract="sha256:contract"):
    return {
        "session_id": session_id, "finished": finished,
        "contract_sha256": contract,
        "branches": {name: {"arms": {"D": {"selected": {
            "east_km": 1., "north_km": 2.}}}}
            for name in local.base.PRIORS},
    }


def test_seed_binding_rejects_incomplete_or_changed_search(tmp_path):
    path = tmp_path / "search.json"
    path.write_text(json.dumps(seed_payload(finished=False)))
    digest = local.base.digest(path.read_bytes())
    distances = {"complete": True, "contract_sha256": "sha256:contract",
                 "search_sha256": {"scan": digest}}
    with pytest.raises(ValueError, match="identity|contract"):
        local.validated_seed("scan", path, distances, "sha256:contract")
    path.write_text(json.dumps(seed_payload()))
    with pytest.raises(ValueError, match="incomplete or changed"):
        local.validated_seed("scan", path, distances, "sha256:contract")


def test_seed_binding_accepts_completed_hash_bound_search(tmp_path):
    path = tmp_path / "search.json"
    path.write_text(json.dumps(seed_payload()))
    digest = local.base.digest(path.read_bytes())
    search, actual = local.validated_seed(
        "scan", path, {"complete": True, "contract_sha256": "sha256:contract",
                       "search_sha256": {"scan": digest}},
        "sha256:contract")
    assert search["finished"] is True and actual == digest
