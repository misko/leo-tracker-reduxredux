from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import acceptance, position
from tools.pipeline_eval.variants import v5_screen_winner

from reports.ALGO08.v3.nomination_handoff import NominationHandoff, capture_race


@pytest.fixture
def admitted():
    nodes = [dict(seed=dict(rows=[dict(component=f"track-{i}", candidate_index=i)], state={}),
                  aliases=[i-1]) for i in range(3)]
    calls = []
    prepared = dict(tracks=dict(tracks=[dict(times=[1., 2.], values=[4., 6.])]),
                    sky=dict(metadata={}, nominal_elements={}, previous_receipt={}, previous_tle="earlier",
                             bank=dict(time_s=np.array([0., 5.]), position_km=np.ones((3, 2, 3)))))
    region, bound = object(), object()

    def scan(*args):
        calls.append("scan")
        return SimpleNamespace(radio_sigma_hz=150.)

    def rank(context):
        calls.append("rank")
        return deepcopy(nodes)

    core = SimpleNamespace(scan_context=scan, ranked_initial_nodes=rank)
    record = NominationHandoff(core, v5_screen_winner, rank, {})
    owned = record.prepare(prepared, region, "noise", bound, "previous")
    ranked = record.rank(owned)
    outcomes = {i: (n, np.array([float(i), .5]), {i: -1.5}, float((i != 1) * i))
                for i, n in enumerate(ranked)}
    return SimpleNamespace(record=record, core=core, calls=calls, prepared=prepared, region=region,
                           bound=bound, owned=owned, ranked=ranked, outcomes=outcomes)


def test_completed_prefix_preserves_original_order_tie_and_remaining_fits(admitted, monkeypatch):
    r = admitted
    r.record.capture(r.owned, r.ranked, r.outcomes)
    visits = []

    def reload_model(scan, node, sigma, fitted_c, reference):
        visits.append((node, reference.copy()))
        return SimpleNamespace(rows=node["seed"]["rows"], alias=node["aliases"], labels=[0],
                               state=lambda point: dict(phases=np.array([8.])))

    monkeypatch.setattr(position, "NormalPosition", reload_model)
    monkeypatch.setattr(position, "fit", lambda model, anchor, **kw: dict(parameters=anchor + 1, score=50.))
    monkeypatch.setattr(position, "refreshed", lambda *args, **kw: pytest.fail("Rescored the admitted prefix"))
    monkeypatch.setattr(acceptance, "actual_metrics", lambda *args: {"gate": True})
    stats = {}
    with r.record.fallback():
        scan = r.core.scan_context(r.prepared, r.region, "noise", r.bound, "previous")
        answer, count = v5_screen_winner.screen_nodes(scan, r.core.ranked_initial_nodes(scan), stats)
    assert r.calls == ["scan", "rank"]
    assert stats["screen_c0_scores"] == [0., 0., 2.] and stats["winning_rank"] == 0
    assert count == len(visits) == 3
    assert all(node == r.ranked[0] for node, phase in visits)
    np.testing.assert_array_equal(visits[0][1], [-1.5])
    np.testing.assert_array_equal(visits[-1][1], [8.])
    assert answer["choices"][0]["arms"]["c0"]["metrics"] == {"gate": True}
    assert r.record.consume(r.owned, r.ranked) is None


def test_missing_or_reordered_rank_and_prefix_remain_independent(admitted):
    r = admitted
    r.record.capture(r.owned, r.ranked, {0: r.outcomes[0]})
    assert r.record.checkpoint is None
    r.record.capture(r.owned, list(reversed(r.ranked)), r.outcomes)
    assert r.record.checkpoint is None
    r.record.nodes = None
    assert len(r.record.replay_rank(r.owned)) == 3
    with r.record.fallback():
        fresh = r.core.scan_context(r.prepared, r.region, "noise", r.bound, "previous")
        assert fresh is not r.owned
        assert len(r.core.ranked_initial_nodes(fresh)) == 3
    assert r.record.counts["rank_reuses"] == 0


@pytest.mark.parametrize("bad", ("score", "anchor", "phase", "labels", "node"))
def test_bad_checkpoint_does_not_arm_resume(admitted, bad):
    r = admitted
    node, anchor, phase, score = r.outcomes[0]
    if bad == "score":
        score = np.inf
    elif bad == "anchor":
        anchor[0] = np.nan
    elif bad == "phase":
        phase[0] = 15.1
    elif bad == "labels":
        phase = {1: -1.5}
    else:
        node = deepcopy(node)
        node["aliases"][0] += 1
    r.outcomes[0] = node, anchor, phase, score
    r.record.capture(r.owned, r.ranked, r.outcomes)
    assert r.record.checkpoint is None
    assert r.record.counts["invalid_prefix"] == 1


@pytest.mark.parametrize("mismatch", ("new_input", "changed_bank", "changed_bound", "changed_region", "other_prior"))
def test_mismatched_owner_geometry_or_prior_reranks(admitted, mismatch):
    r = admitted
    r.record.capture(r.owned, r.ranked, r.outcomes)
    prepared, region, bound, mode = r.prepared, r.region, r.bound, "previous"
    if mismatch == "new_input":
        prepared = deepcopy(prepared)
    elif mismatch == "changed_bank":
        prepared["sky"]["bank"]["position_km"][0, 0, 0] += 1.
    elif mismatch == "changed_bound":
        bound = object()
    elif mismatch == "changed_region":
        region = object()
    else:
        mode = "genuine_previous"
    with r.record.fallback():
        fresh = r.core.scan_context(prepared, region, "noise", bound, mode)
        assert fresh is not r.owned
        assert len(r.core.ranked_initial_nodes(fresh)) == 3
        assert r.record.consume(fresh, r.ranked) is None
    assert r.record.counts["rank_reuses"] == r.record.counts["prefixes_reused"] == 0


def test_external_adapter_captures_actual_partial_return(admitted):
    r = admitted
    raw_partial = lambda *args: (r.outcomes, [])
    race = SimpleNamespace(partial_fits=raw_partial)

    def ordinary(mode, prepared, region, bound):
        return race.partial_fits(r.owned, r.ranked, 12.5, {})

    race.refine = ordinary
    assert capture_race(race, r.record)("race", r.prepared, r.region, r.bound) == (r.outcomes, [])
    assert r.record.checkpoint is not None
    assert race.partial_fits is raw_partial
