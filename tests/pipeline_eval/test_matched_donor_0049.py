from copy import deepcopy

import pytest

from matched_donor_0049 import derive, owner_counts, same_carrier
from signed_cfo_time_readout import canonical, opportunities


def factor(hz, samples=0.0, *, margin=4.0, rank=0):
    return dict(fractional_tracking_cfo_hz=hz, integer_epoch_sample=1234,
                fractional_epoch_offset_samples=samples, passed_fractional_margin_gate=True,
                fractional_margin=margin, candidate_rank=rank)


def native_pair():
    candidate = factor(-1800.0, margin=3.5)
    stock = factor(-1900.0, samples=1.5, margin=11.0, rank=1)
    stock_probes, sparse_probes = [], []
    for visit, pair in enumerate(((stock, candidate), (stock, candidate), (stock, factor(90000.0)),
                                  (None, candidate), (stock, None), (None, None))):
        for radio in (0, 1):
            row = dict(edge=0, channel=1, actual_rf_hz=11720000000, visit_index=visit,
                       valid_start_counter=visit*200000, receiver_id=radio)
            stock_probes.append(dict(row, candidates=[] if pair[0] is None else [pair[0]]))
            sparse_probes.append(dict(row, candidates=[] if pair[1] is None else [pair[1]]))
    source = dict(session_id='original', input_manifest_sha256='same', raw_recording_authority_digest='raw',
                  capture_start_utc_ns=1, analysis_manifest_sha256='source-packet')
    context = dict(clock_anchor={'same': 1}, delivery_clocks=[2], last_sample_counter=1200000,
                   provenance=dict(detector_sha256='old', run_id='parent', excluded_windows=[3]))
    return dict(context, source=dict(source, probes=stock_probes)), dict(context, source=dict(source, probes=sparse_probes))


def test_threshold_uses_original_signed_frequency_and_wrapped_native_epoch():
    period = 40_000/3
    anchor = factor(-1200.0)
    assert same_carrier(anchor, factor(-950.0, period+1.75))
    assert same_carrier(anchor, factor(-1450.0, -period-2))
    assert not same_carrier(anchor, factor(-949.99, period+1.75))
    assert not same_carrier(anchor, factor(-950.0, -period-2.01))
    assert not same_carrier(anchor, factor(-1200.0+1/4.4e-6))


def test_only_matching_nonanchors_change_and_maintain_original_opportunity_metadata():
    stock, sparse = native_pair()
    originals = deepcopy((stock, sparse))
    derived, audit = derive(stock, sparse)
    assert (stock, sparse) == originals
    old, new = opportunities(sparse), opportunities(derived)
    assert list(old) == list(new)
    for oid in old:
        a, b = (p[oid] for p in (old, new))
        assert bool(a['factor']) == bool(b['factor'])
        assert a['row'] | {'candidates': b['row']['candidates']} == b['row']
        if a['row']['visit_index'] == 1:
            assert b['factor'] == opportunities(stock)[oid]['factor']
        else:
            assert a == b
    assert sorted(audit['coverage']) == ['rx0/anchor', 'rx0/short', 'rx1/anchor', 'rx1/short']
    assert audit['coverage']['rx0/short'] == {
        'opportunities': 5, 'substitutions': 1, 'matches': 1, 'carrier_disagreement': 1,
        'sparse_only': 1, 'installed_only': 1, 'both_empty': 1}
    assert audit['substituted'] == 2
    assert audit['feature_changes'] == dict(fractional_tracking_cfo_hz=2, fractional_epoch_offset_samples=2,
                                           fractional_margin=2, candidate_rank=2)
    assert audit['raw_authority'] == 'raw'
    assert audit['recipe_sha256'] == derived['provenance']['detector_sha256'] == canonical(audit['recipe'])
    assert audit['derived_native_sha256'] == canonical(derived) != canonical(sparse)
    assert audit['recipe']['sparse_native_sha256'] == canonical(sparse)
    assert audit['recipe']['installed_native_sha256'] == canonical(stock)
    donor, _ = audit['donations']
    sample = [[donor['observation_id'], 4, 0.0], ['not_donated', 4, 1.0]]
    assert owner_counts({'c0': sample}, audit['donations']) == {'c0': dict(total=2, donated=1)}


def test_refuse_different_clock_or_conditioned_sparse_lane():
    stock, sparse = native_pair()
    sparse['source']['probes'][2]['actual_rf_hz'] += 1
    with pytest.raises(ValueError, match='stereo visit identity'):
        derive(stock, sparse)
    stock, sparse = native_pair()
    sparse['source']['probes'][2]['candidates'].append(factor(-1000.0, rank=1))
    with pytest.raises(ValueError, match='exactly one'):
        derive(stock, sparse)
