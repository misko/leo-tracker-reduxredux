from dataclasses import replace

import numpy as np
import pytest
from adapter import Window, replay


def window():
    return Window("a", 0, 0, 0, 0, 0, 123, 123, 0.4, 0.1, True)


def kwargs():
    return dict(
        expected_ids=["a"],
        sample_rate_hz=2_500_000,
        receiver_ids=[0, 1],
        visit_sample_counts={0: 50_000},
        maximum_visit_bytes=400_000,
        read_visit=lambda _: np.zeros((50_000, 2, 2), np.int16),
        evaluate=lambda x, w, fs: {"acquired": w.acquired_cfo_hz, "count": len(x)},
    )


def test_original_anchor_and_sample_count_preserved():
    row = list(replay([window()], **kwargs()))[0]
    assert row["status"] == "complete"
    assert row["result"] == {"acquired": 123, "count": 50_000}


def test_cap_prevents_read_and_preserves_missing_row():
    k = kwargs()
    k["maximum_visit_bytes"] = 1
    k["read_visit"] = lambda _: pytest.fail("must not read")
    assert list(replay([window()], **k)) == [{"window_id": "a", "status": "visit-resource-cap"}]


def test_membership_and_parity_failure_no_replacement():
    with pytest.raises(ValueError, match="membership"):
        list(replay([], **kwargs()))
    row = list(replay([replace(window(), original_passed=False)], **kwargs()))[0]
    assert row["status"] == "parity-or-window-failed"


def test_unsupported_rate_is_explicit():
    k = kwargs()
    k["sample_rate_hz"] = 7_500_000
    k["read_visit"] = lambda _: pytest.fail("must not read")
    assert list(replay([window()], **k))[0]["status"] == "unsupported-sample-rate"


def test_midwindow_failure_no_duplicate_ids_and_read_failure():
    second = replace(window(), window_id="b", receiver=1)
    k = kwargs()
    k["expected_ids"] = ["a", "b"]

    def evaluate(x, w, fs):
        if w.window_id == "b":
            raise ValueError("bad parity")
        return {}

    k["evaluate"] = evaluate
    rows = list(replay([window(), second], **k))
    assert [r["window_id"] for r in rows] == ["a", "b"]
    assert [r["status"] for r in rows] == ["complete", "parity-or-window-failed"]

    def broken(_):
        raise OSError("read failed")

    k["read_visit"] = broken
    rows = list(replay([window(), second], **k))
    assert [r["window_id"] for r in rows] == ["a", "b"]
    assert all(r["status"] == "visit-read-failed" for r in rows)
