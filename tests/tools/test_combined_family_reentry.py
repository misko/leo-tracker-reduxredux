from types import SimpleNamespace
import numpy as np
import pytest
from combined_family_reentry import choose_width,offers


def test_wider_prior_requires_predictive_gain_in_both_arms_and_pays_penalty():
    assert choose_width({'c0':5.,'fitted_c':4.})==1000
    assert choose_width({'c0':5.,'fitted_c':-1.})==300
    assert choose_width({'c0':1.,'fitted_c':1.})==300
    with pytest.raises(ValueError):choose_width({'c0':np.nan,'fitted_c':3.})


def test_reentry_never_reuses_associated_points_or_an_active_family():
    tracks=[dict(key=f't{i}',times=np.arange(30.),observation_ids=list(range(i*30,(i+1)*30))) for i in range(4)]
    rows=[dict(component=f't{i}',candidate_index=j,candidate_norad=100+j) for i,j in enumerate([0,0,2,3])]
    p=SimpleNamespace(rows=rows,members=list(range(4)),slices=[slice(i*30,(i+1)*30) for i in range(4)],keep=np.r_[np.ones(30,bool),np.zeros(90,bool)])
    d=dict(scan=SimpleNamespace(tracks=tracks),problems={'c0':(p,np.zeros(2))},entries=[])
    pair={a:dict(proposed_associated_ids=[0,60]) for a in ('c0','fitted_c')}
    result=offers(d,pair)
    assert [r['component'] for r in result]==['t3']
    d['entries']=[dict(candidate_index=3)]
    assert offers(d,pair)==[]


def test_held_values_change_predictive_score_without_changing_training_fit(monkeypatch):
    import combined_family_reentry as reentry

    train=np.array([True,False,True,False,True,False])
    monkeypatch.setattr(reentry,'randomized_blocks',lambda times,seed:(train,{'withheld_blocks':[1]}))
    values=np.arange(6,dtype=float)
    training_means=[]
    p=SimpleNamespace(slices=[slice(0,6)],members=[0])
    d=dict(problems={a:(p,np.zeros(2)) for a in reentry.ARMS},
           scan=SimpleNamespace(tracks=[dict(times=np.arange(6.))]),
           keep=np.zeros(6,bool),means=np.zeros(1),powers=np.ones(1))

    def build(data,keep,arm,reference,target,sigma):
        assert np.array_equal(keep,train)
        mean=values[keep].mean();training_means.append(mean)
        calculation=dict(features=np.ones((6,1)),noise_precision=np.ones(1),
                         coefficient_prior_precision=np.ones(1),conditional_residual_hz=values-mean)
        return SimpleNamespace(calculate=lambda x:calculation,
            state=lambda x:dict(phases=np.zeros(1)),labels=np.array([0]),
            noise_groups=np.zeros(6,int),point_noise=np.ones(6))

    monkeypatch.setattr(reentry,'build',build)
    before=reentry.predict_width(d,0,300,0)
    values[~train]+=100
    after=reentry.predict_width(d,0,300,0)
    assert set(training_means)=={2.}
    for arm in reentry.ARMS:
        assert after['arms'][arm]['objective']>before['arms'][arm]['objective']
        np.testing.assert_equal(after['arms'][arm]['held_sigma_hz'],before['arms'][arm]['held_sigma_hz'])
