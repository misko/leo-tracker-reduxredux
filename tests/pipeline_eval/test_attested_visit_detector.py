from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3.attested_visit_detector import equal_original, observation_id, ordered_windows, pin


def fixture():
    targets = {"a": {"target_id": "a", "edge": "lower"}}
    visits, bytes_ = [], b""
    for sequence, n in enumerate((2, 0, 4)):
        data = bytes([sequence]) * (8*n)
        start = 100 + 100*sequence
        row = dict(sequence=sequence, receiver_count=2, target_id="a", sample_count=n,
                   payload_offset_bytes=len(bytes_), payload_bytes=len(data), iq_sha256=pin(data),
                   acquisition=dict(global_visit=sequence, sample_start=start, sample_end=start+n))
        visits.append(dict(sequence=sequence, signed_row=row, target=targets["a"], receiver_ids=[0, 1],
                           decoded_offset_bytes=len(bytes_), decoded_bytes=len(data), sha256=pin(data)))
        bytes_ += data
    schema = SimpleNamespace(model_validate=lambda row: SimpleNamespace(**row))
    return dict(windows=visits), [v["signed_row"] for v in visits], targets, memoryview(bytes_), schema


def test_attested_rows_preserve_zero_invalid_extent_and_end_at_last_full_original_hash():
    attested, rows, targets, body, schema = fixture()
    output = ordered_windows(attested, rows, targets, body, schema, np)
    assert [i[2].shape for i in output] == [(2, 2, 2), (0, 2, 2), (4, 2, 2)]
    assert all(not i[2].flags.writeable for i in output)
    with pytest.raises(ValueError, match="last complete"):
        ordered_windows(attested, rows, targets, memoryview(bytes(body) + b"x"), schema, np)
    with pytest.raises(ValueError, match="digest"):
        ordered_windows(attested, rows, targets, body[:-3], schema, np)


@pytest.mark.parametrize("problem", ["reorder", "offset", "radio", "target", "counter"])
def test_window_metadata_is_bound_to_original_row(problem):
    attested, rows, targets, body, schema = fixture()
    altered = deepcopy(attested)
    windows = altered["windows"]
    if problem == "reorder":
        windows[0], windows[1] = windows[1], windows[0]
    elif problem == "offset":
        windows[1]["decoded_offset_bytes"] = 0
    elif problem == "radio":
        windows[0]["receiver_ids"] = [1, 0]
    elif problem == "target":
        windows[0]["target"]["edge"] = "upper"
    elif problem == "counter":
        windows[0]["signed_row"]["acquisition"]["sample_start"] += 1
    with pytest.raises(ValueError, match="metadata"):
        ordered_windows(altered, rows, targets, body, schema, np)


def test_named_gate_retains_signed_alias_and_lane_identity():
    lane = {"receiver_id": 0, "valid_start_counter": 45, "candidates": [{"fractional_tracking_cfo_hz": -0.0}]}
    difference = dict(lane, candidates=[{"fractional_tracking_cfo_hz": 0.0}])
    assert not equal_original(lane, difference)
    assert observation_id("same", lane) != observation_id("same", dict(difference, receiver_id=1))
