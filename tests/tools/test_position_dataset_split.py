import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PATH = Path(__file__).parents[2] / "tools" / "research" / "position_dataset_split.py"
SPEC = importlib.util.spec_from_file_location("test_position_dataset_split_subject", PATH)
assert SPEC.loader is not None
SUBJECT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SUBJECT
SPEC.loader.exec_module(SUBJECT)


def _row(number, minute, duration=300):
    return {
        "session_id": f"s{number}",
        "captured_at": f"2026-09-23T{minute // 60:02d}:{minute % 60:02d}:00+00:00",
        "nominal_duration_seconds": duration,
        "evidence_digest": f"digest-{number}",
    }


def _document():
    training = [_row(1, 0)]
    validation = [_row(2, 125)]
    return {
        "embargo": {"primary_minutes": 120},
        "provenance": {"exposed_session_ids": ["s1", "s2", "s3", "s4"]},
        "partitions": {
            "training": {
                "status": "exposed-development",
                "session_ids": ["s1"],
                "latest_capture_start": training[-1]["captured_at"],
                "latest_nominal_capture_end": "2026-09-23T00:05:00+00:00",
                "duration_tiers": SUBJECT._tier_views(training),
            },
            "development_validation": {
                "status": "retrospective-exposed",
                "session_ids": ["s2"],
                "earliest_capture_start": validation[0]["captured_at"],
                "latest_nominal_capture_end": "2026-09-23T02:10:00+00:00",
                "duration_tiers": SUBJECT._tier_views(validation),
            },
            "embargo_quarantine": {"session_ids": ["s3"], "status": "excluded"},
            "test_embargo_quarantine": {"session_ids": [], "status": "excluded"},
            "prospective_test_reserve": {
                "session_ids": ["future"],
                "metadata": [{"session_id": "future", "captured_at": "2026-09-23T04:10:00+00:00"}],
                "status": "reserved",
            },
        },
    }


def test_duration_windows_report_nominal_and_elapsed_time_separately():
    rows = [_row(index, index * 10, duration=280 + index) for index in range(1, 7)]
    window = SUBJECT._windows(rows, 6, "about_1h")[0]
    assert window["summed_nominal_capture_seconds"] == sum(280 + i for i in range(1, 7))
    assert window["elapsed_span_seconds"] == 50 * 60 + 286
    assert window["continuous_iq"] is False


def test_tier_windows_are_nonoverlapping_within_each_tier():
    rows = [_row(index, index * 10) for index in range(12)]
    one_hour = SUBJECT._tier_views(rows)["about_1h"]
    assert len(one_hour["windows"]) == 2
    first, second = (set(row["session_ids"]) for row in one_hour["windows"])
    assert not first.intersection(second)


def test_validate_accepts_disjoint_embargoed_split():
    SUBJECT._validate(_document())


@pytest.mark.parametrize(
    "left,right", [("training", "development_validation"), ("training", "prospective_test_reserve")]
)
def test_validate_rejects_recording_leakage_between_partitions(left, right):
    document = _document()
    document["partitions"][right]["session_ids"] = list(document["partitions"][left]["session_ids"])
    with pytest.raises(ValueError, match="partitions overlap"):
        SUBJECT._validate(document)


def test_validate_rejects_short_temporal_embargo():
    document = _document()
    document["partitions"]["development_validation"]["earliest_capture_start"] = (
        "2026-09-23T02:04:59+00:00"
    )
    with pytest.raises(ValueError, match="embargo"):
        SUBJECT._validate(document)


def test_validate_rejects_exposed_recording_in_prospective_reserve():
    document = _document()
    document["partitions"]["prospective_test_reserve"]["session_ids"] = ["s4"]
    with pytest.raises(ValueError, match="exposed"):
        SUBJECT._validate(document)


def test_validate_rejects_duration_window_crossing_partition():
    document = deepcopy(_document())
    single = document["partitions"]["training"]["duration_tiers"]["single_300s"]
    single["windows"][0]["session_ids"] = ["s2"]
    with pytest.raises(ValueError, match="crosses"):
        SUBJECT._validate(document)


def test_validate_rejects_duplicate_within_partition():
    document = _document()
    document["partitions"]["training"]["session_ids"] = ["s1", "s1"]
    with pytest.raises(ValueError, match="duplicate recording"):
        SUBJECT._validate(document)


def test_validate_rejects_overlapping_windows_within_tier():
    document = _document()
    tier = document["partitions"]["training"]["duration_tiers"]["single_300s"]
    tier["windows"].append(deepcopy(tier["windows"][0]))
    with pytest.raises(ValueError, match="overlap within a tier"):
        SUBJECT._validate(document)


def test_validate_rejects_validation_to_test_short_embargo():
    document = _document()
    document["partitions"]["prospective_test_reserve"]["metadata"][0]["captured_at"] = (
        "2026-09-23T04:09:59+00:00"
    )
    with pytest.raises(ValueError, match="validation-to-test"):
        SUBJECT._validate(document)


def test_candidate_partition_uses_capture_start_not_publication_discovery_time():
    validation_end = SUBJECT._time("2026-09-23T14:35:00+00:00")
    rows = [
        {"session_id": "before", "captured_at": "2026-09-23T15:10:00+00:00"},
        {"session_id": "embargoed", "captured_at": "2026-09-23T15:20:00+00:00"},
        {"session_id": "eligible", "captured_at": "2026-09-23T16:40:00+00:00"},
    ]
    old_as_of = SUBJECT.AS_OF
    SUBJECT.AS_OF = SUBJECT._time("2026-09-23T17:00:00+00:00")
    try:
        effective, quarantine, reserve = SUBJECT._partition_candidate_metadata(rows, validation_end)
    finally:
        SUBJECT.AS_OF = old_as_of
    assert effective == SUBJECT._time("2026-09-23T16:35:00+00:00")
    assert [row["session_id"] for row in quarantine] == ["embargoed"]
    assert [row["session_id"] for row in reserve] == ["eligible"]


def test_load_partition_checks_content_digest_and_unavailable_status(tmp_path):
    document = _document()
    document["content_digest_without_this_field"] = SUBJECT._digest_value(document)
    path = tmp_path / "manifest.json"
    path.write_text(__import__("json").dumps(document))
    assert SUBJECT.load_partition(path, "training") == ("s1",)
    tampered = __import__("json").loads(path.read_text())
    tampered["partitions"]["training"]["session_ids"] = ["changed"]
    path.write_text(__import__("json").dumps(tampered))
    with pytest.raises(ValueError, match="digest mismatch"):
        SUBJECT.load_partition(path, "training")
