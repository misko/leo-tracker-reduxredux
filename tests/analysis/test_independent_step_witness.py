import numpy as np
import pytest
from independent_step_witness import fit_at_time,search


def curve(norad,amplitude,*,receiver=1):
    times=np.linspace(0,60,121)
    return dict(component=str(norad),norad=norad,receiver=receiver,channel=1,rf_hz=11.5e9,
        times_s=times,residual_hz=80.+2.*times+amplitude*(times>=30))


def test_common_step_requires_other_families_and_recovers_time():
    target=curve(1,10000);tracks=[target,curve(2,400),curve(3,400)]
    result=search(tracks,target)
    assert result['supported_exploratory_proposal']
    assert abs(result['best']['time_s']-30)<=.5
    assert result['best']['same_sign_two_sigma_families']==2
    assert {r['norad'] for r in result['best']['family_votes']}=={2,3}


def test_affine_trends_do_not_vote_for_a_step():
    result=search([curve(2,0),curve(3,0)],curve(1,900))
    assert not result['supported_exploratory_proposal']
    assert abs(result['best']['amplitude_hz'])<1e-8


def test_duplicate_channels_do_not_replace_independent_family_support():
    assert fit_at_time([curve(2,500),curve(2,500)],30) is None
    single=fit_at_time([curve(2,400),curve(3,400)],30)
    duplicated=fit_at_time([curve(2,400),curve(2,400),curve(3,400)],30)
    assert single['amplitude_hz']==pytest.approx(duplicated['amplitude_hz'])


def test_receiver_scope_excludes_other_receiver_and_target_family():
    result=search([curve(2,400,receiver=2),curve(3,400,receiver=2),curve(1,900)],curve(1,900))
    assert result['best'] is None and result['witness_curves']==0
