"""Frozen DS9 C5/C6/C7 boundary checks; no production Python is imported."""

from __future__ import annotations

import ctypes
import json
import math
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
COMPONENT = ROOT / "native" / "adaptive" / "location"
FIXTURE = ROOT / "reports" / "2026_09_30_arm_location_prototype"

OK = 0
DONE = 1
SEARCH_SCORE_TOLERANCE_HZ = 1.0e-9


class TleRecord(ctypes.Structure):
    _fields_ = [
        ("satellite_id", ctypes.c_int32),
        ("line1", ctypes.c_char * 70),
        ("line2", ctypes.c_char * 70),
    ]


class OrbitState(ctypes.Structure):
    _fields_ = [("position_km", ctypes.c_double * 3), ("velocity_km_s", ctypes.c_double * 3)]


class OrbitSnapshot(ctypes.Structure):
    _fields_ = [
        ("generation", ctypes.c_uint64),
        ("start_utc_ns", ctypes.c_int64),
        ("knot_start_s", ctypes.c_double),
        ("knot_step_s", ctypes.c_double),
        ("satellite_count", ctypes.c_uint32),
        ("knot_count", ctypes.c_uint32),
        ("satellite_ids", ctypes.POINTER(ctypes.c_int32)),
        ("states", ctypes.POINTER(OrbitState)),
    ]


class Site(ctypes.Structure):
    _fields_ = [("ecef_km", ctypes.c_double * 3), ("up", ctypes.c_double * 3)]


class Track(ctypes.Structure):
    _fields_ = [
        ("track_key", ctypes.c_uint64),
        ("observation_count", ctypes.c_uint32),
        ("weight_s", ctypes.c_uint32),
        ("times_s", ctypes.POINTER(ctypes.c_double)),
        ("measured_hz", ctypes.POINTER(ctypes.c_double)),
        ("training_mask", ctypes.POINTER(ctypes.c_uint8)),
    ]


class ScoreConfig(ctypes.Structure):
    _fields_ = [
        ("carrier_hz", ctypes.c_double),
        ("speed_of_light_km_s", ctypes.c_double),
        ("unmatched_penalty_hz", ctypes.c_double),
        ("tau_first_s", ctypes.c_int32),
        ("tau_last_s", ctypes.c_int32),
        ("tau_step_s", ctypes.c_int32),
    ]


class TrackScore(ctypes.Structure):
    _fields_ = [
        ("matched", ctypes.c_uint8),
        ("candidate_id", ctypes.c_int32),
        ("tau_s", ctypes.c_int32),
        ("heldout_rms_hz", ctypes.c_double),
        ("training_rms_hz", ctypes.c_double),
        ("frequency_offset_hz", ctypes.c_double),
    ]


class PointScore(ctypes.Structure):
    _fields_ = [
        ("weighted_mse_hz2", ctypes.c_double),
        ("residual_rmse_hz", ctypes.c_double),
        ("matched_track_count", ctypes.c_uint32),
        ("unmatched_track_count", ctypes.c_uint32),
    ]


class SearchPolicy(ctypes.Structure):
    _fields_ = [
        ("radius_km", ctypes.c_double),
        ("region_size_km", ctypes.c_double),
        ("level_count", ctypes.c_uint32),
        ("levels_km", ctypes.c_double * 8),
        ("budget_points", ctypes.c_uint32),
    ]


class SearchPoint(ctypes.Structure):
    _fields_ = [
        ("east_km", ctypes.c_double),
        ("north_km", ctypes.c_double),
        ("spacing_km", ctypes.c_double),
        ("depth", ctypes.c_uint32),
    ]


class SearchEvaluation(ctypes.Structure):
    _fields_ = [
        ("east_km", ctypes.c_double),
        ("north_km", ctypes.c_double),
        ("weighted_mse_hz2", ctypes.c_double),
    ]


class SearchResult(ctypes.Structure):
    _fields_ = [
        ("generation", ctypes.c_uint64),
        ("evaluated_points", ctypes.c_uint32),
        ("deferred_cells", ctypes.c_uint32),
        ("complete", ctypes.c_uint8),
        ("cancelled", ctypes.c_uint8),
        ("has_incumbent", ctypes.c_uint8),
        ("incumbent", SearchEvaluation),
    ]


def _require_fixtures() -> None:
    required = [
        FIXTURE / "inputs.json",
        FIXTURE / "host-search.json",
        FIXTURE / "local" / "ephemeris-arm-generated.bin",
        FIXTURE / "local" / "tles.txt",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        pytest.fail(f"required frozen DS9 location inputs are missing: {missing}")


@pytest.fixture(scope="module")
def library(tmp_path_factory: pytest.TempPathFactory):
    _require_fixtures()
    output = tmp_path_factory.mktemp("native-location")
    subprocess.run([str(COMPONENT / "build.sh"), "host", str(output)], check=True)
    lib = ctypes.CDLL(str(output / "libleolocation.so"))
    lib.leo_orbit_context_create.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    lib.leo_orbit_context_create.restype = ctypes.c_void_p
    lib.leo_orbit_context_destroy.argtypes = [ctypes.c_void_p]
    lib.leo_orbit_build_tle.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint64,
        ctypes.c_int64,
        ctypes.c_double,
        ctypes.c_double,
        ctypes.c_uint32,
        ctypes.POINTER(TleRecord),
        ctypes.c_uint32,
        ctypes.POINTER(OrbitSnapshot),
    ]
    lib.leo_score_context_create.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
    lib.leo_score_context_create.restype = ctypes.c_void_p
    lib.leo_score_context_destroy.argtypes = [ctypes.c_void_p]
    lib.leo_score_default_config.restype = ScoreConfig
    lib.leo_track_scores_clear.argtypes = [ctypes.POINTER(TrackScore), ctypes.c_uint32]
    lib.leo_score_partition.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(OrbitSnapshot),
        ctypes.POINTER(Track),
        ctypes.c_uint32,
        ctypes.POINTER(Site),
        ctypes.POINTER(ScoreConfig),
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(TrackScore),
        ctypes.c_void_p,
    ]
    lib.leo_point_score_finish.argtypes = [
        ctypes.POINTER(Track),
        ctypes.c_uint32,
        ctypes.POINTER(TrackScore),
        ctypes.POINTER(ScoreConfig),
        ctypes.POINTER(PointScore),
    ]
    lib.leo_search_context_create.argtypes = [ctypes.c_uint32]
    lib.leo_search_context_create.restype = ctypes.c_void_p
    lib.leo_search_context_destroy.argtypes = [ctypes.c_void_p]
    lib.leo_search_begin.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(SearchPolicy)]
    lib.leo_search_next.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint64,
        ctypes.POINTER(SearchPoint),
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.leo_search_submit.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint64,
        ctypes.POINTER(SearchEvaluation),
        ctypes.c_uint32,
    ]
    lib.leo_search_get_result.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint64,
        ctypes.POINTER(SearchResult),
    ]
    lib._component_output = output
    return lib


def _load_scoring_fixture():
    raw = (FIXTURE / "local" / "ephemeris-arm-generated.bin").read_bytes()
    magic, satellite_count, knot_count, track_count, point_count, base, step = struct.unpack_from(
        "<5I2d", raw
    )
    assert magic == 0x31434F4C
    offset = 36
    sites = np.frombuffer(raw, dtype="<f8", count=point_count * 6, offset=offset).reshape(-1, 6)
    offset += point_count * 6 * 8
    track_arrays = []
    tracks = (Track * track_count)()
    for index in range(track_count):
        observations, weight = struct.unpack_from("<2I", raw, offset)
        offset += 8
        times = np.frombuffer(raw, dtype="<f8", count=observations, offset=offset)
        offset += observations * 8
        measured = np.frombuffer(raw, dtype="<f8", count=observations, offset=offset)
        offset += observations * 8
        training = np.frombuffer(raw, dtype=np.uint8, count=observations, offset=offset)
        offset += observations
        track_arrays.extend((times, measured, training))
        tracks[index] = Track(
            index,
            observations,
            weight,
            times.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            measured.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            training.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        )
    ids = np.frombuffer(raw, dtype="<i4", count=satellite_count, offset=offset)
    offset += satellite_count * 4
    states = np.frombuffer(
        raw, dtype="<f8", count=satellite_count * knot_count * 6, offset=offset
    ).reshape(satellite_count, knot_count, 6)
    assert offset + states.nbytes == len(raw)
    snapshot = OrbitSnapshot(
        1,
        1790557997299661326,
        base,
        step,
        satellite_count,
        knot_count,
        ids.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
        states.ctypes.data_as(ctypes.POINTER(OrbitState)),
    )
    return raw, sites, tracks, track_arrays, ids, states, snapshot


def test_ds9_tle_orbit_snapshot_matches_arm_generated_fixture(library):
    manifest = json.loads((FIXTURE / "inputs.json").read_text())
    _, _, _, _, expected_ids, expected_states, _ = _load_scoring_fixture()
    lines = (FIXTURE / "local" / "tles.txt").read_text().splitlines()
    count = int(lines[0])
    assert count == manifest["valid_count"] == len(expected_ids)
    records = (TleRecord * count)()
    for index in range(count):
        line1, line2 = lines[1 + 2 * index : 3 + 2 * index]
        assert len(line1) == len(line2) == 69
        records[index].satellite_id = int(manifest["satellite_ids"][index])
        records[index].line1 = line1.encode()
        records[index].line2 = line2.encode()
    context = library.leo_orbit_context_create(count, expected_states.shape[1])
    assert context
    try:
        actual = OrbitSnapshot()
        status = library.leo_orbit_build_tle(
            context,
            9,
            manifest["start_utc_ns"],
            manifest["knot_start_s"],
            10.0,
            expected_states.shape[1],
            records,
            count,
            ctypes.byref(actual),
        )
        assert status == OK
        actual_ids = np.ctypeslib.as_array(actual.satellite_ids, shape=(count,))
        actual_states = np.ctypeslib.as_array(
            ctypes.cast(actual.states, ctypes.POINTER(ctypes.c_double)),
            shape=(count * expected_states.shape[1] * 6,),
        ).reshape(expected_states.shape)
        np.testing.assert_array_equal(actual_ids, expected_ids)
        np.testing.assert_allclose(actual_states, expected_states, rtol=0, atol=7.3e-11)
    finally:
        library.leo_orbit_context_destroy(context)


def test_ds9_all_track_scores_preserve_128_winners_and_taus(library):
    manifest = json.loads((FIXTURE / "inputs.json").read_text())
    raw, sites, tracks, arrays, ids, states, snapshot = _load_scoring_fixture()
    assert raw and arrays and ids.size and states.size  # retain pointer owners
    maximum_observations = max(track.observation_count for track in tracks)
    context = library.leo_score_context_create(maximum_observations, 11)
    assert context
    config = library.leo_score_default_config()
    scores = (TrackScore * len(tracks))()
    try:
        for point_index, expected_point in enumerate(manifest["points"]):
            site = Site(tuple(sites[point_index, :3]), tuple(sites[point_index, 3:]))
            library.leo_track_scores_clear(scores, len(tracks))
            assert (
                library.leo_score_partition(
                    context,
                    ctypes.byref(snapshot),
                    tracks,
                    len(tracks),
                    ctypes.byref(site),
                    ctypes.byref(config),
                    0,
                    len(ids),
                    scores,
                    None,
                )
                == OK
            )
            point = PointScore()
            assert (
                library.leo_point_score_finish(
                    tracks, len(tracks), scores, ctypes.byref(config), ctypes.byref(point)
                )
                == OK
            )
            assert abs(point.residual_rmse_hz - expected_point["expected_score_hz"]) < 0.004
            assert point.matched_track_count == len(tracks)
            for score, expected in zip(scores, expected_point["expected_tracks"], strict=True):
                assert score.matched
                assert score.candidate_id == int(expected["candidate_id"])
                assert score.tau_s == expected["tau_s"]
                assert abs(score.heldout_rms_hz - expected["heldout_rms_hz"]) < 0.12
    finally:
        library.leo_score_context_destroy(context)


def test_ds9_cli_one_and_two_worker_scores_are_identical(library):
    fixture = FIXTURE / "local" / "ephemeris-arm-generated.bin"
    outputs = []
    for workers in (1, 2):
        result = subprocess.run(
            [str(library._component_output / "leo-location"), "score", str(fixture), str(workers)],
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]
    parsed = json.loads(outputs[0])
    assert [point["matched_tracks"] for point in parsed["points"]] == [64, 64]


@pytest.mark.parametrize("name,radius", [("sacramento", 250.0), ("reno", 500.0)])
def test_ds9_native_search_matches_each_400_point_reference_trace(library, name, radius):
    reference = json.loads((FIXTURE / "host-search.json").read_text())[name]
    expected = [event for event in reference["trace"] if event["event"] == "evaluate"]
    assert len(expected) == 400
    policy = SearchPolicy(radius, 1000.0, 4, (100.0, 50.0, 25.0, 12.5), 400)
    generation = 71
    context = library.leo_search_context_create(400)
    assert context
    consumed = 0
    try:
        assert library.leo_search_begin(context, generation, ctypes.byref(policy)) == OK
        while True:
            points = (SearchPoint * 128)()
            count = ctypes.c_uint32()
            status = library.leo_search_next(
                context, generation, points, len(points), ctypes.byref(count)
            )
            if status == DONE:
                break
            assert status == OK and count.value > 0
            evaluations = (SearchEvaluation * count.value)()
            for index in range(count.value):
                oracle = expected[consumed + index]
                assert points[index].east_km == oracle["east_km"]
                assert points[index].north_km == oracle["north_km"]
                assert points[index].spacing_km == oracle["spacing_km"]
                evaluations[index] = SearchEvaluation(
                    points[index].east_km,
                    points[index].north_km,
                    oracle["weighted_mse_hz2"],
                )
            consumed += count.value
            assert (
                library.leo_search_submit(context, generation, evaluations, count.value) == OK
            )
        assert consumed == len(expected)
        result = SearchResult()
        assert library.leo_search_get_result(context, generation, ctypes.byref(result)) == OK
        assert result.evaluated_points == 400 and result.has_incumbent and not result.complete
        assert result.incumbent.east_km == reference["selected"]["east_km"]
        assert result.incumbent.north_km == reference["selected"]["north_km"]
        assert math.sqrt(result.incumbent.weighted_mse_hz2) == pytest.approx(
            reference["selected"]["residual_rmse_hz"], abs=1e-12
        )
    finally:
        library.leo_search_context_destroy(context)


@pytest.mark.parametrize(
    "name,latitude,longitude,radius,deferred_cells",
    [
        ("sacramento", 38.5816, -121.4944, 250.0, 95),
        ("reno", 39.5296, -119.8138, 500.0, 175),
    ],
)
def test_ds9_cli_integrates_scorer_and_original_400_point_search(
    library, name, latitude, longitude, radius, deferred_cells
):
    fixture = FIXTURE / "local" / "ephemeris-arm-generated.bin"
    reference = json.loads((FIXTURE / "host-search.json").read_text())[name]
    expected = [event for event in reference["trace"] if event["event"] == "evaluate"]
    assert len(expected) == 400

    completed = subprocess.run(
        [
            str(library._component_output / "leo-location"),
            "search",
            str(fixture),
            str(latitude),
            str(longitude),
            str(radius),
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    actual = json.loads(completed.stdout)
    assert actual["schema"] == "org.leo.native-adaptive-location-search/v2"
    assert actual["evaluated_points"] == actual["budget_points"] == 400
    assert actual["deferred_cells"] == deferred_cells
    assert not actual["complete"]
    assert actual["stop_reason"] == "point-budget-reached"
    assert len(actual["evaluations"]) == len(expected)

    for observed, oracle in zip(actual["evaluations"], expected, strict=True):
        assert observed[0] == oracle["east_km"]
        assert observed[1] == oracle["north_km"]
        assert abs(observed[2] - math.sqrt(oracle["weighted_mse_hz2"])) <= (
            SEARCH_SCORE_TOLERANCE_HZ
        )

    assert actual["selected"]["east_km"] == reference["selected"]["east_km"]
    assert actual["selected"]["north_km"] == reference["selected"]["north_km"]
    assert abs(
        actual["selected"]["score_hz"] - reference["selected"]["residual_rmse_hz"]
    ) <= SEARCH_SCORE_TOLERANCE_HZ
