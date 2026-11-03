from types import SimpleNamespace

import finite_set_epoch_increments as epoch
import numpy as np
import pytest


def _metadata_row(
    candidate_id,
    row_index,
    *,
    session="capture",
    visit=0,
    receiver=0,
    probe=0,
    integer_epoch=10,
    integer_session=100,
    offset=0.0,
    measured=25.0,
    sample_rate=7500.0,
):
    fractional_epoch = integer_epoch + offset
    return {
        "candidate_id": candidate_id,
        "probe_key": [session, visit, receiver, probe],
        "local_probe_key": [visit, receiver, probe],
        "integer_epoch_sample": integer_epoch,
        "integer_session_sample": integer_session,
        "fractional_epoch_offset_samples": offset,
        "fractional_epoch_samples": fractional_epoch,
        "tracking_cfo_hz": measured,
        "candidate_spec": {
            "integer_epoch_sample": str(integer_epoch),
            "integer_session_sample": str(integer_session),
            "integer_device_sample_counter": str(50_000 + integer_session),
            "fractional_epoch_offset_samples": offset,
            "fractional_time_s": (integer_session + offset) / sample_rate,
        },
        "_row_index": row_index,
    }


def _bound_data(rows, *, sample_rate=7500.0):
    count = len(rows)
    data = SimpleNamespace(
        times=np.arange(count, dtype=float),
        measured=np.asarray([row["tracking_cfo_hz"] for row in rows]),
        rf=np.full(count, 11.2e9),
        receiver=np.asarray([row["local_probe_key"][1] for row in rows]),
        channel=np.ones(count, dtype=int),
        group=np.arange(count),
        original_rows=np.asarray([row["_row_index"] for row in rows]),
    )
    cleaned = [{key: value for key, value in row.items() if key != "_row_index"} for row in rows]
    receipt = {
        "schema": "alias-family-capture-export/v1",
        "sealed": True,
        "session_id": "capture",
        "sample_rate_hz": sample_rate,
        "representative_original_indices": data.original_rows.tolist(),
        "accounting": {"grouped_family_count": count},
        "grouping": {"representative_rows": cleaned},
    }
    return data, receipt


def test_binding_uses_frame_epoch_not_session_modulo_and_accepts_string_counters():
    rows = [
        _metadata_row("a", 2, integer_epoch=9, integer_session=108, offset=0.25),
        _metadata_row("b", 5, integer_epoch=1, integer_session=127, offset=-0.25),
    ]
    data, receipt = _bound_data(rows)

    bound = epoch.bind_representative_metadata(data, receipt)

    assert bound["device_counter_origin"] == 50_000
    assert bound["physical_period_samples"] == 10.0
    assert bound["rows"][0]["frame_phase_samples"] == 9.25
    assert bound["rows"][1]["frame_phase_samples"] == 0.75
    assert all(row["acquisition_ring_seam"] for row in bound["rows"])
    assert 108.25 % 10 != bound["rows"][0]["frame_phase_samples"]
    assert 126.75 % 10 != bound["rows"][1]["frame_phase_samples"]

    data.original_rows = data.original_rows[::-1]
    with pytest.raises(ValueError, match="order differs"):
        epoch.bind_representative_metadata(data, receipt)


def test_binding_rejects_inconsistent_fractional_epoch():
    rows = [_metadata_row("a", 0, integer_epoch=9, offset=0.25)]
    data, receipt = _bound_data(rows)
    receipt["grouping"]["representative_rows"][0]["fractional_epoch_samples"] = 9.5

    with pytest.raises(ValueError, match="epoch metadata differs"):
        epoch.bind_representative_metadata(data, receipt)


def test_posterior_selection_and_circular_increment_strata():
    rows = []
    for index, (visit, time_s, phase) in enumerate(
        [(0, 0.0, 9.8), (0, 0.2, 0.2), (1, 0.7, 0.5), (3, 2.0, 0.6)]
    ):
        rows.append(
            {
                "row_index": index,
                "candidate_id": str(index),
                "visit_index": visit,
                "receiver": 0,
                "probe_index": index,
                "channel": 1,
                "group": index,
                "fractional_time_s": time_s,
                "frame_epoch_samples": phase,
                "frame_phase_samples": phase,
                "acquisition_ring_seam": phase < 0.25 or phase > 9.75,
            }
        )
    association = np.array([[0.9, 0.1], [0.85, 0.1], [0.8, 0.1], [0.79, 0.2]])
    selected = epoch.select_strongest_satellite_rows(
        rows, association, np.array([1, 2]), np.array([100, 101, 102]), threshold=0.8
    )

    result = epoch.summarize_epoch_increments(
        selected, sample_rate_hz=7500.0, max_gap_s=1.0
    )

    assert result["selected_row_count"] == 3
    assert result["all"]["pair_count"] == 2
    assert result["same_visit"]["pair_count"] == 1
    assert result["different_visit"]["pair_count"] == 1
    assert result["different_visit"]["continuity_claimed"] is False
    assert result["session_time_modulo_closure_tested"] is False
    assert np.isclose(
        result["same_visit"]["frame_epoch_increment_samples"]["median"], 0.4
    )
    assert np.isclose(
        result["same_visit"]["frame_epoch_increment_us"]["median"],
        0.4 / 7500 * 1e6,
    )
    assert result["all"]["acquisition_ring_seam_pair_count"] == 2


def test_pairing_separates_catalog_receiver_channel_and_reports_exclusions():
    def row(candidate, time_s, *, catalog=10, receiver=0, channel=1, phase=0.0):
        return {
            "candidate_id": candidate,
            "catalog_number": catalog,
            "receiver": receiver,
            "channel": channel,
            "visit_index": 0,
            "fractional_time_s": time_s,
            "frame_phase_samples": phase,
            "acquisition_ring_seam": False,
        }

    rows = [
        row("a", 0.0, phase=0.0),
        row("b", 0.5, phase=1.0),
        row("c", 2.0, phase=2.0),
        row("same-time", 2.0, phase=2.5),
        row("other-catalog", 0.2, catalog=11),
        row("other-rx", 0.2, receiver=1),
        row("other-channel", 0.2, channel=2),
    ]

    result = epoch.summarize_epoch_increments(rows, sample_rate_hz=7500.0)

    assert result["candidate_adjacent_pair_count"] == 3
    assert result["all"]["pair_count"] == 1
    assert result["gap_excluded_adjacent_pair_count"] == 1
    assert result["nonpositive_gap_excluded_adjacent_pair_count"] == 1
    assert len(result["strata"]) == 1
    assert result["strata"][0]["catalog_number"] == 10


def test_run_is_restricted_to_two_pilots_and_declares_no_fit_or_reference(monkeypatch):
    monkeypatch.setattr(
        epoch,
        "diagnose_unit",
        lambda unit_id, **kwargs: {"unit_id": unit_id, "status": "complete"},
    )

    receipt = epoch.run(["DS11-S02", "DS10-S01"])

    assert receipt["provenance"] == {
        "reference_accessed": False,
        "evaluation_artifact_accessed": False,
        "iq_read": False,
        "rf_collection_performed": False,
        "fit_performed": False,
    }
    assert [unit["unit_id"] for unit in receipt["units"]] == list(epoch.SUPPORTED_UNITS)
    with pytest.raises(ValueError, match="requires exactly"):
        epoch.run(["DS10-S01"])
    with pytest.raises(ValueError, match="requires exactly"):
        epoch.run(["DS10-S01", "DS10-S01"])
