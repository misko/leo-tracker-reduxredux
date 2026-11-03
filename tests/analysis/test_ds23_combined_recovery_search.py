import json
from types import SimpleNamespace

import ds23_combined_recovery_search as recovery
import numpy as np
import pytest

from leo.analysis.research.retained_track_likelihood import PERIOD


def test_receiver_groups_keep_original_row_order_and_masked_members():
    tracks = [dict(receiver=2, channel=7), dict(receiver=1, channel=5),
              dict(receiver=1, channel=1), dict(receiver=1, channel=6)]
    p = SimpleNamespace(scan=SimpleNamespace(tracks=tracks),
                        rows=[dict(candidate_index=8) for _ in range(4)],
                        members=[2, 0, 3, 1], slices=[slice(i*12, (i+1)*12) for i in range(4)],
                        keep=np.r_[np.ones(24, bool), np.zeros(12, bool), np.ones(12, bool)])
    blocks = recovery.recovery_blocks(p)
    assert len(blocks) == 1
    assert blocks[0]['receiver'] == 1
    assert blocks[0]['row_indices'] == [0, 2, 3]
    assert blocks[0]['track_indices'] == [2, 3, 1]


def test_simultaneous_swap_updates_original_curved_and_predictive_aliases():
    node = dict(seed=dict(rows=[dict(candidate_index=9, active_curvature=False),
                               dict(candidate_index=5), dict(candidate_index=2)]), aliases=[1, 2])
    entries = [dict(candidate_index=j, norad=j*10, track_index=i, alias=0, observation_ids=[str(i)])
               for i, j in enumerate((5, 2))]
    offers = [dict(block=dict(row_indices=[i], original_index=j, receiver=1),
                   candidate_index=k, norad=100+k, aliases=[-k], predictive_aliases={i: k})
              for i, (j, k) in enumerate(((5, 2), (2, 5)))]
    changed, predictive = recovery.apply_recovery_proposals(
        node, entries, [dict(receiver=1), dict(receiver=1)], offers)
    assert [r['candidate_index'] for r in changed['seed']['rows']] == [9, 2, 5]
    assert changed['aliases'] == [-2, -5]
    assert [e['candidate_index'] for e in predictive] == [2, 5]
    assert [e['alias'] for e in predictive] == [2, 5]
    assert [e['observation_ids'] for e in predictive] == [['0'], ['1']]
    assert node['aliases'] == [1, 2] and entries[0]['candidate_index'] == 5
    with pytest.raises(ValueError, match='overlapping'):
        recovery.apply_recovery_proposals(node, entries, [dict(receiver=1)]*2, offers+offers[:1])


def test_missing_alias_and_predictive_orphan_reject_without_deleting_observations():
    node = dict(seed=dict(rows=[dict(candidate_index=3)]), aliases=[0])
    entries = [dict(candidate_index=3, track_index=0, alias=7, observation_ids=['original'])]
    offer = dict(block=dict(row_indices=[0], original_index=3, receiver=1),
                 candidate_index=6, norad=123, aliases=[1], predictive_aliases={})
    with pytest.raises(ValueError, match='complete predictive aliases'):
        recovery.apply_recovery_proposals(node, entries, [dict(receiver=1)], [offer])
    offer['block']['receiver'] = 2
    with pytest.raises(ValueError, match='unsupported predictive'):
        recovery.apply_recovery_proposals(node, entries, [dict(receiver=1)], [offer])
    assert entries[0]['observation_ids'] == ['original'] and entries[0]['alias'] == 7
    assert node['seed']['rows'][0]['candidate_index'] == 3


def test_alternatives_are_bounded_and_include_same_family_calibration():
    rx = [dict(id=f'rx{i}') for i in range(2)]
    receipt = dict(whole_family_proposals=[dict(id='whole1'), dict(id='whole2')],
                   calibrated_same_family_proposals=[dict(id='same1'), dict(id='same2')])
    offers = recovery.alternatives(rx, receipt)
    assert len(offers) == 6
    assert offers[0] == dict(id='null', proposals=[])
    assert offers[3] == dict(id='receiver_pair', proposals=rx)
    assert [o['id'] for o in offers[-2:]] == ['whole1', 'same1']


def synthetic_problem(monkeypatch, catalogue, old_label, target_label):
    times = np.arange(12., dtype=float)
    tracks = [dict(receiver=1, channel=channel, times=times, rf_hz=11.5e9,
                   values=target_label*times**2 - alias*PERIOD + 350. + 70.*(times >= 6))
              for channel, alias in ((5, -1), (1, 2), (6, 1))]
    scan = SimpleNamespace(tracks=tracks, norads=np.asarray(catalogue),
                           sky=dict(
                               time_s=times, position_km=np.arange(len(catalogue))[:, None, None],
                               velocity_km_s=np.zeros((len(catalogue), 1, 1))),
                           rx_basis=[np.ones((12, 1))]*3,
                           hardware=lambda track, beta: np.full(12, beta[0]))
    state = dict(beta=np.array([300.]), smooth=np.array([[50.]]))
    p = SimpleNamespace(scan=scan, rows=[dict(candidate_index=old_label) for _ in range(2)],
                        members=[1, 0], slices=[slice(0, 12), slice(12, 24)],
                        keep=np.ones(24, bool),
                        events=[dict(kind='family', candidate_index=old_label, time_s=6.)],
                        calculate=lambda x: dict(event_amplitudes_hz=[70.]), state=lambda x: state,
                        linear_entries=[dict(candidate_index=old_label, norad=catalogue[old_label],
                                             track_index=2, alias=0,
                                             observation_ids=['predictive'])])
    calls = []
    def prepare(bank, sample_times, phases):
        labels = np.asarray(bank['position_km'])[:, 0, 0].astype(int)
        calls.append(labels.tolist())
        return labels, np.asarray(sample_times), np.asarray(phases)
    def frequency(geometry, *_):
        labels, sample_times, phases = geometry
        f = labels[:, None]*sample_times[None, :]**2 + phases[:, None]*sample_times[None, :]
        return f, np.ones_like(f), np.zeros_like(f)
    monkeypatch.setattr(recovery, 'prepare_phase_geometry', prepare)
    monkeypatch.setattr(recovery, 'phase_linear_frequency', frequency)
    monkeypatch.setattr(recovery, 'phase_widths', lambda scan, labels: (np.ones(len(labels)),
                         [dict(sigma_s=1., age_s=1., previous_epoch_gap_s=None,
                               old_new_alignment_s=None) for _ in labels]))
    return p, calls


@pytest.mark.parametrize('catalogue,old_label,target_label', [
    ([901, 307, 845, 123, 600, 424], 4, 2), ([111, 830, 297, 444, 505], 1, 3)])
def test_screen_searches_catalogue_without_known_identity_and_removes_fitted_events(
        monkeypatch, catalogue, old_label, target_label):
    p, calls = synthetic_problem(monkeypatch, catalogue, old_label, target_label)
    proposals, receipt, means, entries = recovery.screen_blocks(
        p, np.zeros(2), np.ones(2), dict(shrinkage=0., multiplier=1., nu=None))
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal['candidate_index'] == target_label
    assert proposal['norad'] == catalogue[target_label]
    assert proposal['block']['row_indices'] == [0, 1]
    assert proposal['aliases'] == [2, -1]
    assert proposal['predictive_aliases'] == {0: 1}
    assert abs(proposal['phase_s']) < 1e-10
    assert calls[0] == list(range(len(catalogue)))
    assert means.shape == (len(catalogue),)
    assert receipt['whole_family_proposals'][0]['candidate_index'] == target_label
    assert receipt['calibrated_same_family_proposals'][0]['candidate_index'] == old_label
    assert entries[0]['observation_ids'] == ['predictive']
    assert p.linear_entries[0]['alias'] == 0


def test_growth_searches_new_catalogue_labels_and_keeps_every_fragment_point(monkeypatch):
    p, _ = synthetic_problem(monkeypatch, [98, 135, 730, 482, 865], 4, 2)
    p.keep[:] = False
    p.linear_entries = []
    offers = recovery.growth_offers(p, np.zeros(2), np.ones(2),
                                     dict(shrinkage=0., multiplier=1., nu=None))
    assert len(offers) == 1
    offer = offers[0]
    assert offer['candidate_index'] == 2 and offer['norad'] == 730
    assert offer['rows'] == [0, 1] and offer['aliases'] == [2, -1]
    assert offer['added_points'] == 24
    assert offer['distinct_receiver_channel_owners'] == 2
    assert not offer['new_label_supported_by_retained_curves']
    assert offer['block']['predictive_entry_indices'] == []
    assert not p.keep.any()
    node = dict(seed=dict(rows=p.rows), aliases=[0, 0])
    changed, _ = recovery.apply_recovery_proposals(node, [], p.scan.tracks, offers)
    assert [r['candidate_index'] for r in changed['seed']['rows']] == [2, 2]
    assert node['aliases'] == [0, 0]


def test_growth_rejects_single_owner_new_label_and_short_fragments(monkeypatch):
    p, _ = synthetic_problem(monkeypatch, [98, 135, 730, 482, 865], 4, 2)
    p.rows, p.members, p.slices = p.rows[:1], p.members[:1], p.slices[:1]
    p.keep = np.zeros(12, bool)
    model = dict(shrinkage=0., multiplier=1., nu=None)
    assert recovery.growth_offers(p, np.zeros(2), np.ones(1), model) == []
    p.scan.tracks[p.members[0]]['times'] = np.linspace(0., 9., 12)
    assert recovery.growth_offers(p, np.zeros(2), np.ones(1), model) == []


def test_growth_never_remaps_surviving_predictive_family(monkeypatch):
    p, _ = synthetic_problem(monkeypatch, [98, 135, 730, 482, 865], 4, 2)
    p.keep[:] = False
    offers = recovery.growth_offers(p, np.zeros(2), np.ones(2),
                                     dict(shrinkage=0., multiplier=1., nu=None))
    # A third retained curved fragment still supports the original predictive
    # family. Only the two unassociated growth rows may change identity.
    node = dict(seed=dict(rows=p.rows+[dict(candidate_index=4)]), aliases=[0, 0, 8])
    changed, predictive = recovery.apply_recovery_proposals(
        node, p.linear_entries, p.scan.tracks, offers)
    assert changed['seed']['rows'][-1]['candidate_index'] == 4
    assert predictive == p.linear_entries and predictive is not p.linear_entries
    with pytest.raises(ValueError, match='unsupported predictive'):
        recovery.apply_recovery_proposals(dict(seed=dict(rows=p.rows), aliases=[0, 0]),
                                           p.linear_entries, p.scan.tracks, offers)


@pytest.mark.parametrize('only_incumbent_hidden', [False, True])
def test_invisible_catalogue_receipts_are_strict_json_serializable(
        monkeypatch, only_incumbent_hidden):
    p, _ = synthetic_problem(monkeypatch, [98, 135, 730, 482, 865], 4, 2)
    original_frequency = recovery.phase_linear_frequency
    def hidden_frequency(geometry, *position):
        frequency, elevation, derivative = original_frequency(geometry, *position)
        hidden = geometry[0] == 4 if only_incumbent_hidden else np.ones(len(elevation), bool)
        elevation[hidden] = -1.
        return frequency, elevation, derivative
    monkeypatch.setattr(recovery, 'phase_linear_frequency', hidden_frequency)
    proposals, receipt, _, _ = recovery.screen_blocks(
        p, np.zeros(2), np.ones(2), dict(shrinkage=0., multiplier=1., nu=None))
    json.dumps(dict(proposals=proposals, receipt=receipt), allow_nan=False,
               default=lambda value: value.tolist())
    if only_incumbent_hidden:
        assert proposals[0]['candidate_index'] == 2
        assert proposals[0]['proposal_gain'] is None
    else:
        assert proposals == []
        assert all(r['best_score'] is None for r in receipt['coarse_blocks'])
