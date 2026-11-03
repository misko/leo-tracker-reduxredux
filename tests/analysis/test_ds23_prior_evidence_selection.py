import math
import pytest

from ds23_prior_evidence_selection import choose_prior


def candidate(c0, fitted, *, valid=True, qualified=True):
    return dict(losses=dict(c0=c0, fitted_c=fitted), paired_valid=valid, qualified_pre_RF=qualified)


def test_one_prior_is_selected_by_c0_loss_and_shared_between_controls():
    result = choose_prior(dict(c0=100., fitted_c=110.),
                          dict(location=candidate(90., 95.), skew=candidate(85., 100.)))
    assert result['model'] == 'skew'
    assert result['same_choice_for_both_c_arms']


@pytest.mark.parametrize('alternative', [candidate(99., 100.), candidate(80., 109.),
    candidate(80., 90., valid=False), candidate(80., 90., qualified=False), candidate(float('nan'), 90.)])
def test_prior_needs_causal_qualification_both_gates_and_penalized_gain_in_both_arms(alternative):
    result = choose_prior(dict(c0=100., fitted_c=110.), dict(trial=alternative))
    assert result['model'] == 'original'
    assert result['penalty'] == pytest.approx(2*math.log(3))
