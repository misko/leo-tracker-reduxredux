import numpy as np
import pytest

from tools.pipeline_eval.qualification.partner_local_eval import distinct, pair
from tools.pipeline_eval.variants.partner_local import FRAME, PartnerLocal, primary_centers


def candidate(integer, offset=0.0, margin=0.05, status="complete"):
    return {
        "epoch": integer,
        "fractional_epoch": {"offset_samples": offset, "margin": margin, "status": status},
    }


def test_two_current_epochs_keep_rank_order_and_wrap():
    row = {
        "candidates": [
            candidate(30, margin=0.024),
            candidate(FRAME - 1, 0.71, margin=0.11),
            candidate(1, 0.8, margin=0.10),
            candidate(50, -0.6),
            candidate(70),
            candidate(10, status="unbracketed", margin=None),
        ]
    }
    assert primary_centers(row) == (0, 49)
    assert primary_centers({"candidates": [candidate(7, margin=0.025)]}) == (7,)


def test_scoring_collapses_cfo_aliases_but_counts_separate_partner_families():
    def factor(rank, epoch, cfo, margin):
        return {
            "candidate_rank": rank,
            "integer_epoch_sample": epoch,
            "fractional_tracking_cfo_hz": cfo,
            "fractional_epoch_offset_samples": 0,
            "fractional_margin": margin,
            "passed_fractional_margin_gate": True,
        }

    stock = [
        factor(1, 0, 480000, 0.08),
        factor(2, FRAME - 1, 480000 - 1 / 4.4e-6, 0.09),
        factor(3, 350, 513000, 0.06),
    ]
    assert [value["candidate_rank"] for value in distinct(stock)] == [2, 3]
    report = pair(distinct(stock), [factor(1, 0, 480010, 0.06)])
    assert report["production_only"] == 1
    assert report["native_only"] == 0
    assert report["positive_matches"][0]["aliased_cfo_delta_hz"] == pytest.approx(10)


def test_short_window_rejects_wrong_layout_before_native_entry():
    window = object.__new__(PartnerLocal)
    with pytest.raises(ValueError, match="two lanes"):
        window.analyze(np.empty((200000, 1, 2), dtype="<i2"))
    with pytest.raises(ValueError, match="contiguous"):
        window.analyze(np.empty((200000, 2, 2), dtype="<i2")[::-1])


def test_zero_primary_emits_empty_physical_partner_without_touching_native(monkeypatch):
    from threading import Lock

    window = object.__new__(PartnerLocal)
    window.lock = Lock()
    window.partner = object()
    window.counts = ("receiver_id", "candidate_count")
    window.timings = ("total_cpu",)
    calls = []

    class Native:
        def analyze(self, paired, *, include_timings):
            calls.append(paired.copy())
            return {"rows": [{"receiver_id": 0, "candidates": []}]}

    window.native = Native()
    data = np.zeros((200000, 2, 2), dtype="<i2")
    data[:, 0, 0] = 111
    doc = window.analyze(data, primary=1)
    assert len(calls) == 1 and not np.any(calls[0])
    assert [row["receiver_id"] for row in doc["rows"]] == [0, 1]
    assert doc["rows"][0]["candidates"] == []
