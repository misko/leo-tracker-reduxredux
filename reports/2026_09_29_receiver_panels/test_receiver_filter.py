"""Check exhaustive receiver partitions, record retention and invalid metadata."""

import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "receiver_filter", Path(__file__).with_name("receiver_filter.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sample():
    return [
        {
            "session_id": "a",
            "tracks": [
                {"track_id": "x", "receiver_id": 0, "training_mask": [True, False]},
                {"track_id": "y", "receiver_id": 1, "training_mask": [False, True]},
                {"track_id": "z", "receiver_id": 0, "training_mask": [True, True]},
            ],
        },
        {
            "session_id": "b",
            "tracks": [
                {"track_id": "v", "receiver_id": "1"},
                {"track_id": "w", "receiver_id": "0"},
            ],
        },
    ]


def test_partitions_preserve_records_masks_and_source():
    documents = sample()
    before = copy.deepcopy(documents)
    zero, one = [module.receiver_documents(documents, r) for r in (0, 1)]
    assert documents == before
    assert [d["session_id"] for d in zero] == [d["session_id"] for d in one] == ["a", "b"]
    for original, left, right in zip(documents, zero, one, strict=True):
        a, b = ({t["track_id"] for t in d["tracks"]} for d in (left, right))
        assert not a & b and a | b == {t["track_id"] for t in original["tracks"]}
        assert left["tracks"] == [t for t in original["tracks"] if str(t["receiver_id"]) == "0"]
        assert right["tracks"] == [t for t in original["tracks"] if str(t["receiver_id"]) == "1"]


@pytest.mark.parametrize(
    "case", ("unknown_requested", "unknown_track", "missing_receiver", "duplicate_track")
)
def test_invalid_partition_fails_closed(case):
    docs = sample()
    requested = 0
    if case == "unknown_requested":
        requested = 2
    elif case == "unknown_track":
        docs[0]["tracks"][0]["receiver_id"] = 2
    elif case == "missing_receiver":
        docs[0]["tracks"] = [docs[0]["tracks"][0]]
    else:
        docs[0]["tracks"][1]["track_id"] = "x"
    with pytest.raises(ValueError):
        module.receiver_documents(docs, requested)
