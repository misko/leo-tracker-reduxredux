from copy import deepcopy

import pytest

from anchor_only_0049 import prove_graph_rows, source_views
from empty_recovery_0049 import restore_empty_lanes
from matched_donor_0049 import derive, owner_counts, replace_disagreement, same_carrier
from signed_cfo_time_readout import canonical, opportunities
from sparse_only_drop_0049 import exclude_sparse_only


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


def test_sparse_only_exclusion_keeps_all_other_measured_factors_verbatim():
    stock, sparse = native_pair()
    stock['source']['probes'][0]['candidates'] = []  # full anchor stays positive
    stock['source']['probes'][7]['candidates'] = [dict(factor(-1800), passed_fractional_margin_gate=False)]
    originals = deepcopy((stock, sparse))
    derived, audit = exclude_sparse_only(stock, sparse)
    assert (stock, sparse) == originals
    before, after = opportunities(sparse), opportunities(derived)
    assert list(before) == list(after)
    removed_id, = [oid for oid, a in before.items() if a['row']['visit_index'] == 3 and a['radio'] == 0]
    for oid in before:
        old, new = before[oid], after[oid]
        if oid == removed_id:
            assert new['factor'] is None
            assert new['row'] == dict(old['row'], candidates=[])
        else:
            assert old == new
    assert audit['removed_count'] == 1
    assert audit['removed'][0]['observation_id'] == removed_id
    assert audit['removed'][0]['original'] == before[removed_id]['factor']
    assert audit['recipe']['exclusion_sha256'] == canonical(audit['removed'])
    assert audit['derived_native_sha256'] == canonical(derived)
    assert audit['recipe_sha256'] == derived['provenance']['detector_sha256'] != sparse['provenance']['detector_sha256']
    assert audit['replaced'] == 0
    assert owner_counts({'c0': [[removed_id, 4, 0.0]]}, audit['removed'], label='removed') == {
        'c0': dict(total=1, removed=1)}


def test_never_silently_derives_the_same_packet():
    stock, sparse = native_pair()
    for probe in stock['source']['probes']:
        probe['candidates'] = [factor(400000)]
    with pytest.raises(ValueError, match='literally empty'):
        exclude_sparse_only(stock, sparse)


def test_restore_all_empty_short_lanes_using_complete_selected_installed_tuple():
    stock, sparse = native_pair()
    anchor = sparse['source']['probes'][0]
    anchor['candidates'] = []
    row = stock['source']['probes'][8]
    first = dict(factor(-3000, margin=20, rank=0), passed_fractional_margin_gate=False)
    selected = dict(factor(-7200, samples=.23, margin=6, rank=2), fractional_exact_score=.794,
                    fractional_control_score=.24)
    row['candidates'] = [first, factor(-7300, margin=2, rank=1), selected]
    before = deepcopy((stock, sparse))

    derived, audit = restore_empty_lanes(stock, sparse)
    assert (stock, sparse) == before
    new, original = (p['source']['probes'] for p in (derived, sparse))
    assert len(new) == len(original)
    assert new[8] == dict(original[8], candidates=[selected])
    assert new[9] == dict(original[9], candidates=stock['source']['probes'][9]['candidates'])
    assert new[:8] == original[:8] and new[10:] == original[10:]
    assert new[0]['candidates'] == []  # A positive installed anchor stays unchanged.
    assert audit['inserted_count'] == 2 and audit['original_winners'] == 7
    assert [r['receiver'] for r in audit['inserted']] == [0, 1]
    assert audit['recipe']['insertion_sha256'] == canonical(audit['inserted'])
    assert audit['recipe']['installed_native_sha256'] == canonical(stock)
    assert audit['recipe']['sparse_native_sha256'] == canonical(sparse)
    assert audit['recipe']['scope'] == 'saved research counterfactual'
    assert derived['provenance']['detector_sha256'] != sparse['provenance']['detector_sha256']
    assert audit['derived_native_sha256'] == canonical(derived)
    assert derived['clock_anchor'] == sparse['clock_anchor'] and derived['delivery_clocks'] == sparse['delivery_clocks']


def test_restore_does_not_overwrite_a_nonempty_sparse_row_without_a_passed_winner():
    stock, sparse = native_pair()
    sparse['source']['probes'][8]['candidates'] = [dict(factor(-1800), passed_fractional_margin_gate=False)]
    with pytest.raises(ValueError, match='single selected winner or be empty'):
        restore_empty_lanes(stock, sparse)


def test_disagreement_substitution_includes_epoch_only_and_keeps_anchors_and_empties():
    stock, sparse = native_pair()
    sparse['source']['probes'][0]['candidates'] = [factor(60000)]  # Anchor disagreement.
    sparse['source']['probes'][3]['candidates'] = [factor(-1900, 40_000/3+5.0)]  # Epoch-only disagreement.
    original = deepcopy((stock, sparse))

    restored, audit = replace_disagreement(stock, sparse)
    assert (stock, sparse) == original
    changed = {3, 4, 5}
    assert audit['substituted'] == len(changed) and audit['same_membership']
    assert audit['recipe']['schema'] == 'private-0049-shifted-native-donor-v1'
    assert audit['recipe']['donation_sha256'] == canonical(audit['donations'])
    assert audit['recipe_sha256'] != derive(stock, sparse)[1]['recipe_sha256']
    before, after, installed = (p['source']['probes'] for p in (sparse, restored, stock))
    for i, (a, b, donor) in enumerate(zip(before, after, installed, strict=True)):
        assert b == (dict(a, candidates=donor['candidates']) if i in changed else a)


def test_anchor_only_derivations_prove_exact_arrays_and_original_graph_rows():
    stock, sparse = native_pair()
    stock['source']['probes'][0]['candidates'] = []
    sparse['source']['probes'][1]['candidates'] = stock['source']['probes'][1]['candidates']
    stock_plus, edited_sparse, audit = source_views(stock, sparse)
    assert audit['short_edit_counts'] == dict(matched=2, shifted=2, empty=2, sparse_only=2)
    assert stock_plus['source']['probes'] == edited_sparse['source']['probes']
    anchor, = audit['anchors']
    assert anchor['receiver'] == 0 and anchor['visit'] == 0

    def convert(packet):
        return [dict(observation_id=i, cfo=r['factor']['fractional_tracking_cfo_hz'], counter=r['counter'])
                for i,r in opportunities(packet).items() if r['factor'] is not None], {}

    proof = prove_graph_rows(stock, stock_plus, edited_sparse, audit['anchors'], convert)
    assert proof['two_derivations_exact'] and proof['added_full_anchor_rows'] == 1
    assert not proof['equals_installed'] and not proof['graph_called']
    with pytest.raises(ValueError, match='pre-Graph proof failed'):
        prove_graph_rows(stock, stock_plus, sparse, audit['anchors'], convert)


def test_anchor_only_refuses_a_second_unexplained_anchor_difference():
    stock, sparse = native_pair()
    stock['source']['probes'][0]['candidates'] = []
    with pytest.raises(ValueError, match='identical native tuple arrays'):
        source_views(stock, sparse)
