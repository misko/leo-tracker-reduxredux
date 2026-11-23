from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def parts(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("sparse_rf_recall"), import_module("sparse_rf_carrier")


def lane(oid, time_s, receiver, rf_hz, *, searched=False, paid=False):
    return dict(observation_id=oid, time_s=time_s, receiver=receiver, rf_hz=rf_hz,
                channel=4, searched=searched, paid=paid)


def test_metadata_strips_every_detector_factor_before_generating_opportunities(parts, monkeypatch):
    recall, _ = parts
    raw = dict(edge=2, channel=4, actual_rf_hz=11.5e9, visit_index=4, receiver_id=0,
               candidates=[dict(fractional_tracking_cfo_hz=198000., integer_epoch_sample=77)])

    def read_evidence(document):
        assert document["source"]["probes"] == [dict(raw, candidates=[])]
        return SimpleNamespace(ids=["probe"], time_s=[7.5]), None, None

    monkeypatch.setattr(recall, "functions", lambda: (read_evidence, None, None))
    monkeypatch.setattr(recall, "schedule", lambda probes: (set(), set(), {}))
    result, = recall.metadata(dict(source=dict(probes=[raw])))
    assert result["time_s"] == 7.5 and not result["paid"]
    assert "candidates" not in result and "cfo_hz" not in result


def test_coverage_separates_same_receiver_exact_rf_and_local_time(parts):
    recall, _ = parts
    meta = [lane("a", 10, 0, 11e9, searched=True, paid=True),
            lane("b", 18, 0, 11e9), lane("c", 40, 0, 12e9), lane("d", 70, 1, 11e9),
            lane("e", 20, 0, 11e9, paid=True)]
    sparse = {arm: [dict(observation_id="a", norad=21)] for arm in recall.ARMS}
    full = {arm: {k: dict(observation_id=row["observation_id"], norad=21 if k else 99)
                  for k, row in enumerate(meta)} for arm in recall.ARMS}
    result = recall.coverage(meta, sparse, full)["c0"]
    assert result["changed_satellite"] == result["shared"] == 1
    missing = result["missing"]["unpaid_held"]["coverage"]
    assert missing["satellite"]["within_60_s"] == 3
    assert missing["satellite_receiver"]["within_30_s"] == 2
    assert missing["satellite_receiver_rf"]["within_8_s"] == 1
    assert result["missing"]["paid_warmup"]["full_owner_rows"] == 1


def test_carrier_rank_requires_observed_target_rf_branch_and_caps_slots(parts):
    _, carrier = parts
    period = carrier.PERIOD
    anchors = [dict(lane("a", 10, 0, 11e9), norad=10, measured_cfo_hz=100. + period),
               dict(lane("b", 16, 0, 12e9), norad=20, measured_cfo_hz=200. - period),
               dict(lane("c", 14, 0, 11e9), norad=30, measured_cfo_hz=300. + 2 * period)]
    tables = carrier.anchor_tables(anchors, np.zeros(len(anchors)))
    target = lane("d", 11., 0, 12e9)
    assert carrier.rank(target, tables, transfer=False) == [(20, -1, 200.)]
    assert carrier.rank(target, tables, transfer=True) == [(10, -1, 100.), (30, -1, 300.)]
    assert not carrier.rank(lane("unseen-rf", 12., 0, 13e9), tables, transfer=True)
    assert not carrier.rank(lane("late", 80., 0, 12e9), tables, transfer=True)


def test_signed_scoring_keeps_the_full_cfo_and_counts_wrong_satellite_hits(parts):
    _, carrier = parts
    proposals = {"a": [(1, 40. + carrier.PERIOD), (2, 440.)], "b": [(1, 4551.)],
                 "empty": [(1, 0.)]}
    scored = carrier.score(proposals, {"a": (1, 40.), "b": (1, 1.)})
    assert scored["all_proposals"] == 4 and scored["all_proposal_lanes"] == 3
    assert scored["signed_400_hz"] == 1 and scored["owner_and_signed_400_hz"] == 0
    assert scored["signed_4550_hz"] == 2 and scored["owner_and_signed_4550_hz"] == 1


def test_visit_accounting_counts_both_antennas_only_once(parts):
    _, carrier = parts
    meta = [dict(observation_id="left", visit=10), dict(observation_id="right", visit=10),
            dict(observation_id="odd", visit=12), dict(observation_id="never", visit=13)]
    native = [dict(candidates=[1]), dict(candidates=[2]), dict(candidates=[]), dict(candidates=[3])]
    proposals = {"left": [(1, 4560.)], "right": [(2, 25.)], "odd": [(5, 100.)]}
    ids = carrier.visit_ids(meta, native, proposals, {"left": (1, 10.), "right": (2, 20.)})
    assert ids == {"proposed": [10, 12], "original_factor": [10],
                   "owner_and_signed_400_hz": [10], "owner_and_signed_4550_hz": [10]}
