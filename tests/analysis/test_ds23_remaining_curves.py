from probe_ds23_dbg01_iteration002_extra_curves import remaining_targets
from diagnose_ds23_iteration002_curves import conditional_noise
from finalize_ds23_iteration002_growth import extension_offers
from probe_ds23_iteration002_family_alternatives import common_family_candidates
from probe_ds23_iteration002_curved_promotion import promotable_curves
import numpy as np


def test_remaining_curve_offer_keeps_previous_cap_and_excludes_partial_and_small_tracks():
    rows = [dict(component=str(k), curved=True, points=20, original_points=20) for k in range(7)]
    rows[3]['original_points'] = 22
    rows[4]['points'] = 3
    rows[5]['curved'] = False
    assert [r['component'] for r in remaining_targets(rows)] == ['6']


def test_diagnostic_shared_uncertainty_absorbs_common_offset_without_independent_point_noise_inflation():
    sigma = np.ones(3)*2.
    raw = np.array([9., 10., 11.])
    residual, cost = conditional_noise(raw, np.diag(sigma*sigma), sigma)
    np.testing.assert_allclose(residual, raw)
    assert cost == raw@raw/4.
    residual, _ = conditional_noise(raw, np.diag(sigma*sigma)+100*np.ones((3,3)), sigma)
    assert abs(residual.mean()) < .14
    np.testing.assert_allclose(np.diff(residual), [1., 1.])


def test_only_existing_family_nominations_extend_an_accepted_seed():
    seed = dict(additions=[dict(component='seed', candidate_index=8, norad=100, alias=0)])
    nominations = dict(targets=[dict(target=dict(component=key), best=dict(
        candidate_index=j, norad=n, aliases=[1])) for key,j,n in [('same',8,100),('other',9,200)]])
    offers = extension_offers([seed], nominations)
    assert [r['component'] for r in offers] == ['same', 'seed']
    assert next(r for r in offers if r['component']=='same')['alias'] == 1


def test_joint_alternative_keeps_a_shared_second_candidate_and_excludes_unqualified():
    def curve(key, candidates):
        return dict(target=dict(component=key),candidates=[dict(candidate_index=j,qualified=ok) for j,ok in candidates])
    nominations=[curve('a',[(1,True),(2,True),(3,False)]),curve('b',[(4,True),(2,True),(3,True)])]
    common=common_family_candidates([dict(component='a'),dict(component='b')],nominations)
    assert [j for j,_ in common]==[2]


def test_curved_promotion_preserves_linear_evidence_and_excludes_partial_or_active_curves():
    rows=[dict(component=k,compatible=True,points=10) for k in ['unused','active','partial','linear']]
    chosen=promotable_curves(rows,{'unused','active','partial'},{'active'},dict(unused=10,active=10,partial=12,linear=10))
    assert [r['component'] for r in chosen]==['unused']
