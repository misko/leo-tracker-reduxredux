import hashlib
import json

import numpy as np
import pytest
from bundle import Data


def write_bundle(directory, *, bad_rows=False, nonuniform_nodes=False):
    observation_count = 3
    candidate_count = 64
    nodes = np.arange(-11.0, 311.25, 0.25)
    if nonuniform_nodes:
        nodes[2] += 0.01
    position = np.zeros((candidate_count, len(nodes), 3))
    position[..., 0] = 7000
    velocity = np.zeros_like(position)
    velocity[..., 1] = 1
    arrays = {
        "times": np.array([0.0, 1.0, 2.0]),
        "measured": np.zeros(observation_count),
        "rf": np.full(observation_count, 11.2e9),
        "receiver": np.array([0, 1, 0]),
        "channel": np.array([1, 2, 1]),
        "group": np.array([0, 1, 2]),
        "margin": np.ones(observation_count),
        "nodes": nodes,
        "position": position,
        "velocity": velocity,
        "numbers": np.arange(100, 100 + candidate_count),
        "initial": np.zeros(6 + candidate_count),
    }
    archive = directory / "bundle.npz"
    np.savez_compressed(archive, **arrays)
    manifest = {
        "schema": "coherent-localization-bundle/v1",
        "session_id": "scan-test",
        "tracks": [
            {
                "track_id": "track",
                "rows": [0, 3] if bad_rows else [0, 2],
                "candidate_indices": list(range(candidate_count)),
                "receiver": 0,
                "channel": 1,
            }
        ],
        "track_mapping": {"track_observations": 2},
        "provenance": {"scope": "test"},
        "artifacts": {"bundle_npz_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()},
    }
    (directory / "bundle.json").write_text(json.dumps(manifest))


def test_bundle_data_exposes_common_interface_and_mapping(tmp_path):
    write_bundle(tmp_path)
    data = Data(tmp_path)
    assert data.session_id == "scan-test"
    np.testing.assert_array_equal(data.tracks[0]["rows"], [0, 2])
    prediction, visible = data.predict(data.initial)
    assert prediction.shape == visible.shape == (3, 64)
    assert np.all(np.isfinite(prediction))


def test_bundle_rejects_track_rows_outside_raw_arrays(tmp_path):
    write_bundle(tmp_path, bad_rows=True)
    with pytest.raises(ValueError, match="outside"):
        Data(tmp_path)


def test_bundle_rejects_archive_digest_mismatch(tmp_path):
    write_bundle(tmp_path)
    manifest_path = tmp_path / "bundle.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"]["bundle_npz_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="digest"):
        Data(tmp_path)


def test_bundle_rejects_nonuniform_nodes(tmp_path):
    write_bundle(tmp_path, nonuniform_nodes=True)
    with pytest.raises(ValueError, match="uniformly spaced"):
        Data(tmp_path)
