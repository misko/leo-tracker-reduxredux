from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import probe_initial_weak_track_nomination as probe
import pytest


def track(key, span=25., count=30, pieces=1):
    return dict(key=key, times=np.linspace(0, span, count), values=np.zeros(count),
                observation_ids=[key+str(i) for i in range(count)], pieces=[{}]*pieces)


def initial():
    state = dict(beta=np.zeros(8), phases=np.zeros(3), smooth=np.zeros((2, 1)))
    return dict(status='complete', selected_hypothesis=0, choices=[dict(hypothesis=0,
        node=dict(seed=dict(rows=[]), aliases=[]), arms={a: dict(
            all_graph_associations=dict(tracks=[]), state=deepcopy(state), reference=np.zeros(1),
            fit=dict(score=5., parameters=np.array([1., 2.]))) for a in probe.ARMS})])


def test_weak_selector_excludes_both_arm_owners_and_preserves_radio_only_order():
    tracks = [track('short', span=14.), track('second', span=20.), track('first', span=30.),
              track('curved', span=60.), track('owned', span=50.), track('pieces', pieces=2)]
    saved = initial()
    saved['choices'][0]['arms']['fitted_c']['all_graph_associations']['tracks'] = [
        dict(component='owned', compatible=True)]
    value = probe.select_targets(tracks, [3], saved, maximum=3)
    assert [r['component'] for r in value['targets']] == ['first', 'second']
    assert value['weak_unowned_tracks'] == 4
    assert value['eligible_targets'] == 2
    assert probe.select_targets(tracks, [3], saved, maximum=1)['targets'][0]['component']=='first'
    assert value['ledger'][0]['exclusion_reasons'] == ['shorter_than_15_seconds']
    assert value['ledger'][-1]['exclusion_reasons'] == ['requires_explicit_fragment_view']


def test_physical_duplicates_and_unbounded_prefix_are_rejected():
    first = track('same')
    with pytest.raises(ValueError, match='Duplicate physical'):
        probe.select_targets([first, deepcopy(first)], [], initial())
    with pytest.raises(ValueError, match='one to three'):
        probe.select_targets([first], [], initial(), maximum=4)


def test_empty_and_one_point_tracks_are_ineligible_without_reduction_errors():
    value = probe.select_targets([track('empty', count=0), track('one', count=1)], [], initial())
    assert value['targets'] == []
    assert all(r['duration_s'] == 0 for r in value['ledger'])


def test_reference_coordinates_do_not_affect_radio_only_target_selection():
    tracks = [track('second', span=20.), track('first', span=30.)]
    saved = initial()
    baseline = probe.select_targets(tracks, [], saved)
    saved['evaluation_reference'] = dict(latitude_deg=-80., longitude_deg=100.)
    tracks[0]['GPS_position'] = [80., -100.]
    assert probe.select_targets(tracks, [], saved) == baseline


def test_focus_cannot_change_nomination_inputs_and_never_forces_a_candidate(monkeypatch):
    scan = SimpleNamespace(tracks=[track('weak')], norads=np.array([10, 20, 30]))
    selection = dict(targets=[dict(track_index=0, component='weak')])
    seen = []

    def nominate(context, base, index, mask, limit):
        seen.append((context['scan'], base, index, mask.copy(), limit))
        offers = [dict(candidate_index=1, cost=1., phase_s=0., position=np.zeros(2), arm='c0'),
                  dict(candidate_index=0, cost=3., phase_s=3., position=np.ones(2), arm='fitted_c')]
        return offers[:1], dict(offers=offers[::-1], training_indices=np.arange(16))

    monkeypatch.setattr(probe, 'nominate', nominate)
    base = {arm: object() for arm in probe.ARMS}
    first = probe.nominate_targets(scan, base, selection, focus_norad=20)[0]
    missing = probe.nominate_targets(scan, base, selection, focus_norad=30)[0]
    assert first['focus_offer']['rank'] == 1
    assert first['focus_offer']['selected'] is True
    assert missing['focus_offer'] is None
    assert probe.fingerprint(first['nomination_receipt']) == probe.fingerprint(
        missing['nomination_receipt'])
    assert first['position_inclusion_authorized'] is False
    assert first['predictive_validation_performed'] is False
    assert first['training_fold_shortlist_reuse_authorized'] is False
    assert all(row[0] is scan and row[1] is base and row[2] == 0 and row[4] == 12 for row in seen)
    assert all(row[3].all() for row in seen)


def test_paired_replay_keeps_saved_context_reference_and_rejects_mismatch(monkeypatch):
    saved = initial()
    calls = []

    class Problem:
        def __init__(self, scan, node, sigma, fitted_c, *, reference):
            calls.append((node, fitted_c, reference))

        def residual(self, point):
            np.testing.assert_array_equal(point, [1., 2.])
            return np.array([1., 2.])

        def state(self, point):
            return saved['choices'][0]['arms']['c0']['state']

    monkeypatch.setattr(probe, 'NormalPosition', Problem)
    base, replay = probe.replay_pair(SimpleNamespace(radio_sigma_hz=150.), saved)
    assert list(base) == list(probe.ARMS)
    assert [r[1] for r in calls] == [False, True]
    assert all(r['score_difference'] == 0. for r in replay.values())
    saved['choices'][0]['arms']['fitted_c']['fit']['score'] = 6.
    with pytest.raises(ValueError, match='score replay mismatch: fitted_c'):
        probe.replay_pair(SimpleNamespace(radio_sigma_hz=150.), saved)


def test_existing_or_qnap_output_is_rejected_before_loading(tmp_path):
    for output in (str(tmp_path), '/mnt/qnap01/probe'):
        with pytest.raises(SystemExit):
            probe.main(['--request', '/missing', '--native-manifest', '/missing',
                        '--source-root', '/missing', '--output', output])
