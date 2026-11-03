"""Membership selection must not select on RF outcomes or readiness."""

import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).with_name("freeze_ds28.py")
SPEC = importlib.util.spec_from_file_location("post_ds26", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def member(identity, stamp, root="/source"):
    return dict(
        case_id=identity,
        captured_utc_ns=stamp,
        recording_state="incomplete",
        tracking_inputs=[],
        sample_rate_hz=2500000,
        raw_recording=dict(identity_sha256=identity, root=root, duplicate_roots=[]),
    )


def test_whole_acquisitions_half_open_window_and_no_readiness_filter():
    parent = dict(cutoff_utc_ns=10, members=[])
    result = MODULE.freeze_members(
        [member("old", 9), member("at_start", 10), member("later", 19), member("at_end", 20)],
        parent,
        20,
        "DS27",
    )
    assert [m["case_id"] for m in result] == ["at_start", "later"]
    assert result[0]["recording_state"] == "incomplete"
    assert result[0]["tracking_inputs"] == []
    assert result[0]["sample_rate_hz"] == 2500000
    assert [m["dataset_label"] for m in result] == ["DS27-0001", "DS27-0002"]


def test_duplicate_physical_recordings_merge_and_disagreement_fails():
    parent = dict(cutoff_utc_ns=10, members=[])
    result = MODULE.freeze_members(
        [member("one", 11), member("one", 11, "/copy")], parent, 20, "DS27"
    )
    assert len(result) == 1
    assert result[0]["raw_recording"]["duplicate_roots"] == ["/copy"]
    with pytest.raises(ValueError, match="disagrees"):
        MODULE.freeze_members([member("one", 11), member("one", 12)], parent, 20, "DS27")


def test_parent_identity_overlap_rejected():
    with pytest.raises(ValueError, match="overlaps"):
        MODULE.freeze_members(
            [member("one", 11)], dict(cutoff_utc_ns=10, members=[member("one", 9)]), 20, "DS27"
        )


def test_capture_rates_ignore_restoration_and_expose_conflicts():
    doc = dict(
        timing=dict(sample_rate_hz=10000000),
        receipt=dict(
            plan=dict(geometry=dict(sample_rate_hz=10000000)),
            restoration=dict(sample_rate_hz=2500000),
        ),
    )
    assert MODULE.sample_rates({"manifest": doc}) == [10000000]
    doc["timing"]["sample_rate_hz"] = 5000000
    assert MODULE.sample_rates(doc) == [5000000, 10000000]


def test_capture_time_prefers_observed_timing_to_publication_time():
    assert (
        MODULE.capture_time(
            dict(manifest=dict(created_utc_ns=20, timing=dict(first_sample_estimate_utc_ns=10)))
        )
        == 10
    )


def prior():
    return dict(dataset_id='DS28', revision=1, start_utc_ns=10, cutoff_utc_ns=20,
                members=[dict(member('old', 15), dataset_label='DS28-0001')])


def test_revision_preserves_labels_even_when_earlier_acquisition_arrives_late():
    rows = MODULE.freeze_members([member('late_copy', 11), member('old', 15), member('new', 25)],
                                 dict(cutoff_utc_ns=10, members=[]), 30, 'DS28')
    result = MODULE.preserve_labels(rows, prior(), dict(cutoff_utc_ns=10), 30)
    assert {m['case_id']: m['dataset_label'] for m in result} == {
        'old': 'DS28-0001', 'late_copy': 'DS28-0002', 'new': 'DS28-0003'}


def test_revision_refuses_missing_or_changed_previous_acquisition():
    with pytest.raises(ValueError, match='missing'):
        MODULE.preserve_labels([member('new', 25)], prior(), dict(cutoff_utc_ns=10), 30)
    with pytest.raises(ValueError, match='start changed'):
        MODULE.preserve_labels([member('old', 16)], prior(), dict(cutoff_utc_ns=10), 30)


def test_revision_requires_same_interval_and_advancing_cutoff():
    with pytest.raises(ValueError, match='interval start'):
        MODULE.preserve_labels([member('old', 15)], prior(), dict(cutoff_utc_ns=11), 30)
    with pytest.raises(ValueError, match='cutoff must advance'):
        MODULE.preserve_labels([member('old', 15)], prior(), dict(cutoff_utc_ns=10), 20)
