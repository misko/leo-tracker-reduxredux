from types import SimpleNamespace as S
import pytest
import reception_endpoints as endpoint


def fixture(monkeypatch):
    anchor = S(candidate_rank=0, fractional_margin=.2)
    common = dict(visit_index=0, probe_index=0, probe_start_ms=0.,
                  channel=1, edge=S(value='lower'), valid_start_counter=100)
    p0 = S(**common, receiver_id=0, candidates=[anchor])
    p1 = S(**common, receiver_id=1, candidates=[])
    raw = S(session_id='scan', sample_rate_hz=2500000, probes=[p0,p1])
    candidate = S(candidate_id='source', candidate_rank=0, receiver_id=0,
                  visit_index=0, probe_index=0, channel=1, edge=common['edge'])
    prepared = S(tracks=[S(track_id='track', observation_ids=['train','reserve'], training_mask=[True,False])])
    monkeypatch.setattr(endpoint, 'project_scanner_candidates', lambda _: [candidate])
    monkeypatch.setattr(endpoint, 'resolve', lambda _: [dict(track_id='track',observation_id='reserve',candidate_ids=['source'])])
    monkeypatch.setattr(endpoint.pairing, 'counterpart', lambda *a: dict(matched=False,log_margin_ratio_rx1_rx0=None))
    return raw, prepared


def test_builds_reserved_endpoint_without_position_or_candidates(monkeypatch):
    raw, prepared = fixture(monkeypatch)
    rows = endpoint.build(raw, prepared, bias_hz=0.)
    assert len(rows)==1 and rows[0]['observation_id']=='reserve'
    assert rows[0]['matched'] is False and rows[0]['east']==0.
    assert not {'candidate_ids','latitude_deg','longitude_deg'} & rows[0].keys()


def test_missing_counterpart_is_not_nondetection(monkeypatch):
    raw, prepared = fixture(monkeypatch)
    raw.probes.pop()
    with pytest.raises(ValueError, match='missing counterpart'):
        endpoint.build(raw, prepared, bias_hz=0.)


def test_ambiguous_anchor_fails_closed(monkeypatch):
    raw, prepared = fixture(monkeypatch)
    monkeypatch.setattr(endpoint, 'resolve', lambda _: [dict(track_id='track',observation_id='reserve',candidate_ids=['source','other'])])
    with pytest.raises(ValueError, match='unique'):
        endpoint.build(raw, prepared, bias_hz=0.)
