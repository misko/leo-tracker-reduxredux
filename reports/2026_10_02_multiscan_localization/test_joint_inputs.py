import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from joint_inputs import (
    OrbitStates,
    assemble_unit,
    load_joint_data,
    observation_nodes,
    save_joint_data,
)

SNAPSHOT = {
    "provider": "space-track",
    "collected_utc_ns": 900_000_000_000,
    "digest": "sha256:" + "1" * 64,
}


def analytic_states(satellite_ids, nodes, *, moving=True):
    satellite_ids = np.asarray(satellite_ids, dtype=np.int64)
    nodes = np.asarray(nodes, dtype=float)
    position = np.empty((len(satellite_ids), len(nodes), 3), dtype=float)
    velocity = np.empty_like(position)
    for index in range(len(satellite_ids)):
        position[index, :, 0] = 7000.0 + 3.0 * index
        position[index, :, 1] = 2.0 * nodes
        position[index, :, 2] = 100.0 + index
        velocity[index, :, 0] = 0.05 * index if moving else 0.0
        velocity[index, :, 1] = 2.0 if moving else 0.0
        velocity[index, :, 2] = -0.02 if moving else 0.0
    return position, velocity


def write_child(
    scans_root,
    session_id,
    origin_utc_ns,
    *,
    numbers,
    times,
    groups,
    receiver=None,
    tracks=None,
    snapshot=SNAPSHOT,
    initial=None,
    nodes=None,
    position=None,
    velocity=None,
):
    directory = scans_root / session_id
    directory.mkdir(parents=True)
    numbers = np.asarray(numbers, dtype=np.int64)
    times = np.asarray(times, dtype=float)
    groups = np.asarray(groups, dtype=np.int64)
    receiver = (
        np.arange(len(times), dtype=np.int64) % 2
        if receiver is None
        else np.asarray(receiver, dtype=np.int64)
    )
    nodes = observation_nodes(times) if nodes is None else np.asarray(nodes, dtype=float)
    if position is None or velocity is None:
        position, velocity = analytic_states(numbers, nodes)
    initial = (
        np.zeros(6 + len(numbers), dtype=float)
        if initial is None
        else np.asarray(initial, dtype=float)
    )
    if tracks is None:
        tracks = [
            {
                "track_id": f"track-{session_id}",
                "rows": [0],
                "candidate_indices": list(range(len(numbers))),
                "receiver": int(receiver[0]),
                "channel": 1,
            }
        ]
    arrays = {
        "times": times,
        "measured": np.linspace(100.0, 100.0 + len(times) - 1, len(times)),
        "rf": np.linspace(11.0e9, 11.2e9, len(times)),
        "receiver": receiver,
        "channel": np.ones(len(times), dtype=np.int64),
        "group": groups,
        "margin": np.ones(len(times)),
        "nodes": nodes,
        "position": np.asarray(position, dtype=float),
        "velocity": np.asarray(velocity, dtype=float),
        "numbers": numbers,
        "initial": initial,
    }
    archive = directory / "bundle.npz"
    np.savez(archive, **arrays)
    manifest = {
        "schema": "coherent-localization-bundle/v1",
        "dataset": "DS10",
        "session_id": session_id,
        "origin_utc_ns": int(origin_utc_ns),
        "tracks": tracks,
        "track_mapping": {},
        "provenance": {"tle_snapshot": dict(snapshot)},
        "artifacts": {"bundle_npz_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()},
    }
    (directory / "bundle.json").write_text(json.dumps(manifest))
    return directory


def write_selection(tmp_path, session_ids, *, unit_id="DS10-U01"):
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps(
            {
                "datasets": {
                    "DS10": {
                        "units": [
                            {
                                "unit_id": unit_id,
                                "size": len(session_ids),
                                "session_ids": list(session_ids),
                                "origin_utc_ns": 123,
                                "capture_time_offsets_s": [999.0] * len(session_ids),
                            }
                        ]
                    }
                }
            }
        )
    )
    return path


class RecordingProvider:
    def __init__(self, *, moving=True, mutate=None):
        self.moving = moving
        self.mutate = mutate
        self.calls = []

    def __call__(self, snapshot, satellite_ids, origin_utc_ns, nodes_s):
        self.calls.append(
            (dict(snapshot), satellite_ids.copy(), int(origin_utc_ns), nodes_s.copy())
        )
        position, velocity = analytic_states(satellite_ids, nodes_s, moving=self.moving)
        result_ids = satellite_ids.copy()
        if self.mutate == "missing":
            result_ids = result_ids[:-1]
            position = position[:-1]
            velocity = velocity[:-1]
        elif self.mutate == "nonfinite":
            position[0, len(nodes_s) // 2, 0] = np.nan
        return OrbitStates(result_ids, position, velocity, dict(snapshot))


def assembled_small_joint(tmp_path):
    scans = tmp_path / "scans"
    initial = np.array([2.0, -1.0, 50.0, 0.25, -30.0, -0.5, 0.1, -0.2, 0.3])
    write_child(
        scans,
        "only",
        1_000_000_000_000,
        numbers=[10, 20, 30],
        times=[1.0, 4.0],
        groups=[7, 8],
        receiver=[0, 1],
        initial=initial,
    )
    selection = write_selection(tmp_path, ["only"])
    return assemble_unit(
        selection,
        "DS10",
        "DS10-U01",
        scans,
        RecordingProvider(),
    )


def test_assembler_uses_child_origins_and_preserves_lineage_and_union_mapping(tmp_path):
    scans = tmp_path / "scans"
    first_origin = 1_000_000_000_000
    second_origin = first_origin + 100_000_000_000
    write_child(
        scans,
        "first",
        first_origin,
        numbers=[10, 20],
        times=[0.0, 1.0],
        groups=[5, 5],
        tracks=[
            {
                "track_id": "a",
                "rows": [0, 1],
                "candidate_indices": [1],
                "receiver": 0,
                "channel": 1,
            }
        ],
    )
    write_child(
        scans,
        "second",
        second_origin,
        numbers=[20, 30],
        times=[0.5, 1.5],
        groups=[5, 8],
        tracks=[
            {
                "track_id": "b",
                "rows": [1],
                "candidate_indices": [0, 1],
                "receiver": 1,
                "channel": 1,
            }
        ],
    )
    selection = write_selection(tmp_path, ["first", "second"])
    provider = RecordingProvider()

    data = assemble_unit(selection, "DS10", "DS10-U01", scans, provider)

    np.testing.assert_allclose(data.times, [0.0, 1.0, 100.5, 101.5])
    np.testing.assert_array_equal(data.group, [0, 0, 1, 2])
    np.testing.assert_array_equal(data.capture_index, [0, 0, 1, 1])
    np.testing.assert_array_equal(data.numbers, [10, 20, 30])
    assert data.position.shape == (3, len(data.nodes), 3)
    assert data.tracks[0]["session_id"] == "first"
    assert data.tracks[0]["track_id"] == "first:a"
    np.testing.assert_array_equal(data.tracks[0]["rows"], [0, 1])
    np.testing.assert_array_equal(data.tracks[0]["candidate_indices"], [1])
    assert data.tracks[1]["session_id"] == "second"
    np.testing.assert_array_equal(data.tracks[1]["rows"], [3])
    np.testing.assert_array_equal(data.tracks[1]["candidate_indices"], [1, 2])
    assert len(provider.calls) == 1
    called_snapshot, called_ids, called_origin, called_nodes = provider.calls[0]
    assert called_snapshot == SNAPSHOT
    np.testing.assert_array_equal(called_ids, [10, 20, 30])
    assert called_origin == first_origin
    assert called_nodes[0] <= -11.0
    assert called_nodes[-1] > data.times[-1] + 11.0
    np.testing.assert_allclose(np.diff(called_nodes), 0.25)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "every union satellite"),
        ("nonfinite", "full union ephemeris must be finite"),
    ],
)
def test_incomplete_orbit_coverage_is_rejected(tmp_path, mutation, message):
    scans = tmp_path / "scans"
    write_child(
        scans,
        "only",
        1_000_000_000_000,
        numbers=[10, 20],
        times=[0.0, 1.0],
        groups=[0, 1],
    )
    selection = write_selection(tmp_path, ["only"])

    with pytest.raises(ValueError, match=message):
        assemble_unit(
            selection,
            "DS10",
            "DS10-U01",
            scans,
            RecordingProvider(mutate=mutation),
        )


def test_receiver_slope_uses_receive_time_not_tau_shifted_orbit_time(tmp_path):
    scans = tmp_path / "scans"
    write_child(
        scans,
        "only",
        1_000_000_000_000,
        numbers=[10, 20],
        times=[2.0, 8.0],
        groups=[0, 1],
        receiver=[0, 1],
    )
    selection = write_selection(tmp_path, ["only"])
    data = assemble_unit(
        selection,
        "DS10",
        "DS10-U01",
        scans,
        RecordingProvider(moving=False),
    )
    parameters = np.array([0.0, 0.0, 100.0, 3.0, -50.0, -2.0, 0.0, 0.0])
    shifted = parameters.copy()
    shifted[6:] = [9.0, -7.0]

    baseline, _ = data.predict(parameters)
    changed_tau, _ = data.predict(shifted)

    expected_offsets = np.array(
        [
            100.0 + 3.0 * (data.times[0] - data.reference_time_s),
            -50.0 - 2.0 * (data.times[1] - data.reference_time_s),
        ]
    )
    np.testing.assert_allclose(baseline[:, 0], expected_offsets)
    np.testing.assert_allclose(baseline, changed_tau)


def test_persisted_joint_data_round_trips_dynamic_bank_and_predictions(tmp_path):
    data = assembled_small_joint(tmp_path)
    parameters = data.initial.copy()
    parameters[6:] = [0.25, -0.5, 0.75]
    full_prediction, full_visible = data.predict(parameters)
    rows = np.array([0, 1])
    satellites = np.array([2, 0])
    paired_prediction, paired_visible = data.predict(parameters, rows, satellites)
    output = tmp_path / "persisted" / data.unit_id

    manifest = save_joint_data(data, output)
    loaded = load_joint_data(output)

    assert manifest["candidate_count"] == 3
    assert loaded.reference_time_s == data.reference_time_s
    assert loaded.reference_epoch_utc_ns == data.reference_epoch_utc_ns
    assert loaded.provenance == data.provenance
    np.testing.assert_array_equal(loaded.numbers, data.numbers)
    np.testing.assert_array_equal(loaded.child_origins_utc_ns, data.child_origins_utc_ns)
    assert loaded.tracks[0]["rows"].dtype == np.int64
    assert loaded.tracks[0]["candidate_indices"].dtype == np.int64
    loaded_full, loaded_full_visible = loaded.predict(parameters)
    loaded_paired, loaded_paired_visible = loaded.predict(parameters, rows, satellites)
    np.testing.assert_allclose(loaded_full, full_prediction)
    np.testing.assert_array_equal(loaded_full_visible, full_visible)
    np.testing.assert_allclose(loaded_paired, paired_prediction)
    np.testing.assert_array_equal(loaded_paired_visible, paired_visible)


def test_load_rejects_joint_archive_digest_corruption(tmp_path):
    data = assembled_small_joint(tmp_path)
    output = tmp_path / "persisted" / data.unit_id
    save_joint_data(data, output)
    with (output / "bundle.npz").open("ab") as stream:
        stream.write(b"corruption")

    with pytest.raises(ValueError, match="digest mismatch"):
        load_joint_data(output)


def load_old_bundle_module():
    reports_root = Path(__file__).resolve().parent.parent
    path = reports_root / "2026_10_02_localization_benchmark" / "bundle.py"
    spec = importlib.util.spec_from_file_location("single_child_old_bundle_adapter", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load old bundle adapter from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_single_child_prediction_matches_old_data_with_reference_epoch_conversion(tmp_path):
    scans = tmp_path / "scans"
    numbers = np.arange(1000, 1064, dtype=np.int64)
    times = np.array([0.25, 2.75])
    nodes = observation_nodes(times)
    position, velocity = analytic_states(numbers, nodes)
    initial = np.zeros(70)
    initial[2:6] = [120.0, 0.5, -80.0, -0.25]
    child = write_child(
        scans,
        "only",
        1_000_000_000_000,
        numbers=numbers,
        times=times,
        groups=[0, 1],
        receiver=[0, 1],
        tracks=[
            {
                "track_id": "all",
                "rows": [0, 1],
                "candidate_indices": list(range(64)),
                "receiver": 0,
                "channel": 1,
            }
        ],
        initial=initial,
        nodes=nodes,
        position=position,
        velocity=velocity,
    )
    selection = write_selection(tmp_path, ["only"])

    class ChildStateProvider:
        def __call__(self, snapshot, satellite_ids, origin_utc_ns, nodes_s):
            assert origin_utc_ns == 1_000_000_000_000
            np.testing.assert_array_equal(satellite_ids, numbers)
            np.testing.assert_array_equal(nodes_s, nodes)
            return OrbitStates(numbers.copy(), position.copy(), velocity.copy(), dict(snapshot))

    joint = assemble_unit(selection, "DS10", "DS10-U01", scans, ChildStateProvider())
    old = load_old_bundle_module().Data(child)
    old_parameters = np.zeros(70)
    old_parameters[:6] = [4.0, -3.0, 200.0, 0.75, -90.0, -0.4]
    old_parameters[6:] = np.linspace(-0.1, 0.1, 64)
    joint_parameters = old_parameters.copy()
    for receiver in (0, 1):
        intercept = 2 + 2 * receiver
        slope = intercept + 1
        joint_parameters[intercept] = old_parameters[intercept] + old_parameters[slope] * (
            joint.reference_time_s - 150.0
        )

    old_full, old_visible = old.predict(old_parameters)
    joint_full, joint_visible = joint.predict(joint_parameters)
    np.testing.assert_allclose(joint_full, old_full, rtol=0.0, atol=1e-10)
    np.testing.assert_array_equal(joint_visible, old_visible)

    rows = np.array([0, 1])
    satellites = np.array([3, 61])
    old_paired, old_paired_visible = old.predict(old_parameters, rows, satellites)
    joint_paired, joint_paired_visible = joint.predict(joint_parameters, rows, satellites)
    np.testing.assert_allclose(joint_paired, old_paired, rtol=0.0, atol=1e-10)
    np.testing.assert_array_equal(joint_paired_visible, old_paired_visible)
    np.testing.assert_allclose(joint_paired, joint_full[rows, satellites])
