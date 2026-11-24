from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import anchor_primary_transfer as screen
from anchor_primary_dense_prefix import check_candidates


def test_unexposed_primary_can_replace_a_second_scan_winner():
    first = dict(candidate_rank=0, passed_fractional_margin_gate=True, fractional_margin=.2)
    second = dict(candidate_rank=1, passed_fractional_margin_gate=True, fractional_margin=.4)
    check_candidates([second], [second, first], [first])
    with pytest.raises(ValueError, match="rank zero"):
        check_candidates([second], [second, first], [])


def test_replaces_only_the_ambiguous_antenna_and_keeps_time(monkeypatch):
    ranks = [1, 0, 0, None]
    probes = [dict(visit_index=i//2, receiver_id=i%2, candidates=[] if rank is None else [dict(candidate_rank=rank)])
              for i, rank in enumerate(ranks)]
    monkeypatch.setattr(screen, "enroll", lambda _: [(i//2, i//2, i%2, (), "anchor" if i<2 else "short", ()) for i in range(4)])
    monkeypatch.setattr(screen, "bind", lambda a,b: None)
    monkeypatch.setattr(screen, "selection", lambda record: ({"route":"unfiltered"}, record["source"]["probes"]))
    output = screen.sensitivity({"source":{"probes":probes}})
    assert output["ambiguous_keys"] == [(0,0)]
    assert output["changes"] == {"edited_anchor_lost":1}
    assert output["erased_selected"] == 2
