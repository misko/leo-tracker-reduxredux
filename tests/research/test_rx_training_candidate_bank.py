from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import pytest

from tools.rx_training_candidate_bank import (
    atomic_json,
    forecast_geometry,
    forecast_structural_mask,
    partition_index,
    rank_candidates,
    score_prediction_blocks,
    select_training_tracks,
    source_window_id,
    training_only_input,
)


@dataclass(frozen=True)
class Probe:
    visit_index: int
    probe_index: int
    receiver_id: int
    probe_start_ms: int = 0
    valid_start_counter: int = 100
    channel: int = 1
    edge: str = "lower"
    actual_rf_hz: float = 11_325_000_000.0
    candidates: tuple = field(default_factory=tuple)


@dataclass(frozen=True)
class Raw:
    session_id: str = "session"
    sample_rate_hz: int = 10_000_000
    probes: tuple[Probe, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Track:
    track_id: str
    observation_ids: tuple[str, ...]
    times_s: np.ndarray
    measured_hz: np.ndarray
    training_mask: np.ndarray


def window(raw: Raw, probe: Probe, role: str) -> dict:
    return {
        "source_window_id": source_window_id(raw, probe),
        "session_id": raw.session_id,
        "role": role,
        "window_start_utc_ns": probe.valid_start_counter,
        "window_end_utc_ns": probe.valid_start_counter + 20,
    }


def test_nontraining_candidate_outcomes_are_removed_before_preparation() -> None:
    train = Probe(0, 0, 0, candidates=("train",))
    held0 = Probe(1, 0, 0, valid_start_counter=200, candidates=("secret-a",))
    held1 = Probe(1, 0, 1, valid_start_counter=200, candidates=("secret-b",))
    raw = Raw(probes=(train, held0, held1))
    rows = {
        row["source_window_id"]: row
        for row in (window(raw, train, "train"), window(raw, held0, "held_frequency"))
    }

    filtered, counts = training_only_input(raw, rows)

    assert filtered.probes == (train,)
    assert counts["source_windows"] == 2
    assert counts["training_windows"] == 1
    assert counts["training_probes"] == 1
    assert counts["excluded_probes"] == 2
    assert counts["training_probe_locators"][0]["source_window_id"] == source_window_id(raw, train)
    assert counts["training_probe_locators_digest"].startswith("sha256:")


def test_partition_validation_rejects_duplicate_or_unknown_role() -> None:
    row = {
        "source_window_id": "window",
        "session_id": "session",
        "role": "train",
        "window_start_utc_ns": 1,
        "window_end_utc_ns": 2,
    }
    assert (
        partition_index({"schema": "rx-grouped-partition/v1", "windows": [row]})["session"][
            "window"
        ]
        == row
    )
    with pytest.raises(ValueError, match="duplicated"):
        partition_index({"schema": "rx-grouped-partition/v1", "windows": [row, row]})
    with pytest.raises(ValueError, match="invalid"):
        partition_index({"schema": "rx-grouped-partition/v1", "windows": [{**row, "role": "test"}]})


def test_atomic_json_replaces_a_parseable_checkpoint(tmp_path) -> None:
    import json

    output = tmp_path / "bank.json"
    atomic_json(output, {"status": "running", "completed_session_ids": ["one"]})
    assert json.loads(output.read_text())["completed_session_ids"] == ["one"]
    atomic_json(output, {"status": "complete", "completed_session_ids": ["one", "two"]})
    assert json.loads(output.read_text())["status"] == "complete"


def test_track_cap_uses_latest_training_end_then_id_and_retains_mask() -> None:
    tracks = [
        Track(name, (name,), np.array([0.0, end]), np.array([1.0, 2.0]), np.array([True, False]))
        for name, end in (("z", 8.0), ("b", 10.0), ("a", 10.0), ("x", 9.0))
    ]
    selected = select_training_tracks(tracks)
    assert [row.track_id for row in selected] == ["a", "b", "x"]
    assert all(row.training_mask.tolist() == [True, False] for row in selected)


def test_installed_public_track_accepts_selected_and_forecast_masks() -> None:
    from leo.analysis.adaptive_tle_prediction import AdaptiveTrackInput

    source = AdaptiveTrackInput(
        "source",
        tuple("abcdef"),
        np.arange(6.0),
        np.arange(6.0),
        np.array([True, True, True, False, False, False]),
    )
    assert select_training_tracks([source])[0] is source
    forecast = AdaptiveTrackInput(
        "forecast",
        tuple("uvwxyz"),
        np.arange(6.0),
        np.zeros(6),
        forecast_structural_mask(6),
    )
    assert forecast.training_mask.tolist() == [True, False, False, False, False, False]


def test_rank_profiles_cfo_on_all_training_rows_with_deterministic_tie_break() -> None:
    ranked = rank_candidates(
        [9, 7, 8],
        [100.0, 102.0, 104.0],
        [[0.0, 2.0, 4.0], [10.0, 12.0, 14.0], [0.0, 3.0, 3.0]],
    )
    assert [row["catalog_number"] for row in ranked] == [7, 9, 8]
    assert ranked[0]["profiled_cfo_hz"] == pytest.approx(90.0)
    assert ranked[0]["training_sse_hz2"] == pytest.approx(0.0)


def test_block_scoring_uses_every_returned_catalogue_candidate() -> None:
    track = Track(
        "t", ("a", "b"), np.array([0.0, 1.0]), np.array([10.0, 11.0]), np.ones(2, dtype=bool)
    )
    blocks = [
        SimpleNamespace(
            track_id="t", candidate_ids=np.array([2]), predictions_hz=np.array([[[0.0, 1.0]]])
        ),
        SimpleNamespace(
            track_id="t", candidate_ids=np.array([1]), predictions_hz=np.array([[[1.0, 0.0]]])
        ),
    ]
    ranked = score_prediction_blocks([track], blocks)["t"]
    assert [row["catalog_number"] for row in ranked] == [2, 1]


def test_forecast_geometry_uses_carrier_and_emits_unit_enu() -> None:
    bank = SimpleNamespace(
        candidate_ids=np.array([42]),
        position_km=np.array([[[[2.0, 0.0, 0.0], [2.0, 0.0, 0.0]]]]),
        velocity_km_s=np.array([[[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]]]),
    )
    receiver = SimpleNamespace(ecef_km=np.array([1.0, 0.0, 0.0]), up=np.array([1.0, 0.0, 0.0]))
    frequency, elevation, east, north, up = forecast_geometry(
        bank,
        receiver,
        [0.0, 0.0],
        reference_rf_hz=11_200_000_000.0,
        light_km_s=300_000.0,
    )[42]
    assert frequency == pytest.approx([-11_200_000_000.0 / 300_000.0, 0.0])
    assert elevation == pytest.approx([90.0, 90.0])
    assert np.sqrt(east**2 + north**2 + up**2) == pytest.approx([1.0, 1.0])
