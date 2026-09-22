from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def _subject():
    path = Path(__file__).parents[2] / "tools/research/validate_blind_shared_orbit.py"
    spec = importlib.util.spec_from_file_location("validate_blind_shared_orbit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _documents(subject, heldout_offset=0.0):
    return {
        session: (
            {
                "catalogue_snapshot": {"digest": "catalogue"},
                "tracks": [
                    {
                        "tracklet_id": "track",
                        "observations": [
                            {
                                "support_center_utc_ns": 1_000_000_000 * (index + 1),
                                "measured_cfo_hz": float(index)
                                + (heldout_offset if index >= 6 else 0.0),
                            }
                            for index in range(10)
                        ],
                    }
                ],
            },
            "fixture-digest",
        )
        for session in subject.FIT_SESSIONS + subject.TRANSFER_SESSIONS
    }


def test_partition_holds_out_contiguous_tail_and_excludes_transfer_scans():
    subject = _subject()
    tracks, exclusions = subject._tracks(_documents(subject))
    assert not exclusions
    assert len(tracks) == len(subject.FIT_SESSIONS)
    assert {track["session_id"] for track in tracks} == set(subject.FIT_SESSIONS)
    for track in tracks:
        np.testing.assert_array_equal(track["training"], [True] * 6 + [False] * 4)
        assert track["utc_ns"][track["training"]].max() < track["utc_ns"][~track["training"]].min()


def test_heldout_measurements_cannot_change_exported_training_support():
    subject = _subject()
    clean, _ = subject._tracks(_documents(subject))
    poisoned, _ = subject._tracks(_documents(subject, heldout_offset=1e8))
    for left, right in zip(clean, poisoned, strict=True):
        np.testing.assert_array_equal(left["training"], right["training"])
        np.testing.assert_array_equal(
            left["observed_hz"][left["training"]], right["observed_hz"][right["training"]]
        )


def test_full_catalogue_episode_batches_are_lazy_iterables(monkeypatch):
    subject = _subject()
    tracks, _ = subject._tracks(_documents(subject))
    calls = []
    sentinel = object()

    def candidate_batch(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(subject, "_candidate_batch", candidate_batch)
    catalogue = SimpleNamespace(satellite_numbers=np.asarray([101, 102]))
    episodes, _ = subject._episodes(
        tracks[:1],
        {"catalogue": {"catalogue": catalogue, "indices": np.asarray([0, 1])}},
        39.7392,
        -104.9903,
        "fixture-branch",
    )
    assert not calls
    assert tuple(episodes[0].batches) == (sentinel,)
    assert len(calls) == 1


def test_orbit_phase_shifts_propagation_but_not_receive_time_rotation(monkeypatch):
    subject = _subject()
    julian_inputs = []
    rotation_inputs = []

    def julian(utc_ns):
        julian_inputs.append(np.asarray(utc_ns).copy())
        return np.asarray(utc_ns, dtype=float), np.zeros(len(utc_ns))

    class Propagator:
        def __init__(self, _satellites):
            pass

        def sgp4(self, jd, fraction):
            position = np.ones((2, len(jd), 3)) * 7_000
            velocity = np.ones_like(position)
            velocity[1, 0, 0] = np.nan
            return np.zeros((2, len(jd)), dtype=int), position, velocity

    def rotation(jd, fraction):
        rotation_inputs.append(jd.copy())
        return np.zeros(len(jd))

    monkeypatch.setattr(subject, "SatrecArray", Propagator)
    monkeypatch.setattr(subject, "julian_day_from_utc_ns", julian)
    monkeypatch.setattr(subject, "greenwich_mean_sidereal_time_rad", rotation)
    monkeypatch.setattr(subject, "teme_to_ecef", lambda p, v, angle: (p, v))
    utc_ns = np.asarray([10_000_000_000, 20_000_000_000], dtype=np.int64)
    usable, _, _ = subject._propagate(
        SimpleNamespace(satellites=[object(), object()]),
        np.asarray([0, 1]),
        utc_ns,
        np.asarray([0.25, 0.5]),
    )
    np.testing.assert_array_equal(julian_inputs[0], utc_ns + [250_000_000, 500_000_000])
    np.testing.assert_array_equal(julian_inputs[1], utc_ns)
    np.testing.assert_array_equal(rotation_inputs[0], utc_ns)
    np.testing.assert_array_equal(usable, [True, False])


def test_seal_digest_matches_serialized_numerical_result(tmp_path):
    import json

    subject = _subject()
    result = {"rates": np.asarray([0.1, -0.2]), "count": np.int64(2)}
    digest = subject._digest(result)
    path = tmp_path / "sealed.json"
    subject._atomic_create(path, result)
    assert subject._digest(json.loads(path.read_text())) == digest


def test_qualification_withholds_complete_when_exact_replay_fails():
    subject = _subject()
    result = {
        "selected_shared_result": {
            "shared_fit": {"converged": True},
            "exact_replay_audits": [{"state": "complete", "maximum_error_hz": 0.200001}],
        },
        "selected_nominal_result": {"shared_fit": {"converged": True}},
        "transfer_evaluation": {
            "shared_fit": {"converged": True},
            "exact_replay_audits": [{"state": "complete", "maximum_error_hz": 0.1}],
        },
    }
    answer = subject._qualification(result, True, True, 0.2)
    assert answer == {
        "state": "insufficient",
        "reasons": ("exact-replay-tolerance-failed",),
    }


def test_coarse_result_digest_rejects_same_shape_different_partition(tmp_path, monkeypatch):
    import json

    subject = _subject()
    result_path = tmp_path / "full-region-1000km.json"
    result = {"track_count": 205, "observation_count": 4895, "spacing_km": 1000.0}
    result_path.write_text(json.dumps(result))
    documents = {
        session_id: ({}, f"digest-{index}") for index, session_id in enumerate(subject.FIT_SESSIONS)
    }
    (tmp_path / "configuration.json").write_text(
        json.dumps(
            {
                "source_shard_digests": sorted(value[1] for value in documents.values()),
                "truth_accessed": False,
            }
        )
    )
    monkeypatch.setattr(
        subject,
        "COARSE_RUNNER_SHA256",
        subject._file_digest(Path(subject.__file__).with_name("run_blind_shared_orbit_coarse.py")),
    )
    monkeypatch.setattr(
        subject, "CHRONOLOGICAL_COARSE_RESULT_SHA256", subject._file_digest(result_path)
    )
    subject._load_coarse_result(result_path, documents)
    result["partition"] = "randomized-observation-split"
    result_path.write_text(json.dumps(result))
    with np.testing.assert_raises_regex(ValueError, "chronological protocol"):
        subject._load_coarse_result(result_path, documents)


def test_runner_declares_single_thread_numerical_environment():
    subject = _subject()
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        assert subject.os.environ[name] == "1"
