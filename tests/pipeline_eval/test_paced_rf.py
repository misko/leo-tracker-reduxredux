import pytest

from tools.pipeline_eval.qualification import paced_rf
from tools.pipeline_eval.qualification.paced_rf_results import material


def test_only_actual_service_starts_age_an_rf_and_unseen_replaces_waiter():
    q = paced_rf.Waiting()
    a, b, c = [(key, 11_000_000_000 + key) for key in range(3)]
    assert q.offer("a", {"visit": 0}, a)[0] == "immediate"
    assert q.last_start == {}
    assert q.offer("b", {"visit": 1}, b)[0] == "waiting"
    assert q.offer("c", {"visit": 2}, c) == ("rejected", {"visit": 1}, [None, None])
    assert q.start(lambda: 100) == ("a", {"visit": 0}, 100)
    assert q.last_start == {a: 100}
    q.finish()
    assert q.offer("a2", {"visit": 3}, a)[0] == "waiting"
    assert q.offer("c2", {"visit": 4}, c) == ("replaced_waiter", {"visit": 3}, [100, None])
    assert q.offer("c3", {"visit": 5}, c)[0] == "rejected"
    assert q.start(lambda: 120) == ("b", {"visit": 1}, 120)
    q.finish()
    q.close()
    assert q.start(lambda: 140) == ("c2", {"visit": 4}, 140)
    q.finish()
    assert q.start(lambda: 145) is None


def test_later_drop_and_invalid_cannot_retire_before_earlier_detector():
    seen = []
    ledger = paced_rf.Chronological(seen.append)
    ledger.retire({"visit": 2, "outcome": "invalid_capture"})
    ledger.retire({"visit": 1, "outcome": "queue_drop"})
    assert not seen
    ledger.retire({"visit": 0, "outcome": "emitted"})
    assert [row["visit"] for row in seen] == [0, 1, 2]
    assert not ledger.waiting
    with pytest.raises(ValueError, match="retired twice"):
        ledger.retire({"visit": 1})


def test_factor_fit_uses_actual_payload_and_retains_complete_clocks_and_exclusions():
    before = [{"visit_index": i, "receiver_id": rx} for i in (0, 3) for rx in (0, 1)]
    doc = {
        "source": {"probes": before},
        "provenance": {"excluded_windows": [{"visit": 1}], "window_count": 4},
        "delivery_clocks": ["sample-0", "sample-1", "sample-2", "sample-3"],
    }
    out = material(doc, [3], before[2:], "source-hash")
    assert out["source"]["probes"] == before[2:]
    assert out["delivery_clocks"] is doc["delivery_clocks"]
    assert out["provenance"]["excluded_windows"] is doc["provenance"]["excluded_windows"]
    assert out["provenance"]["window_count"] == 4
    assert out["provenance"]["processed_windows"] == 1
    with pytest.raises(ValueError, match="selected original reference"):
        material(doc, [3], before[:2], "source-hash")
