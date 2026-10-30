import numpy as np
from training_curve_confidence import training_profile
from evaluate_ds23_family_weighting import family_weights


def test_candidate_confidence_ignores_excluded_points():
    t=np.arange(8.);f=np.array([t*t,t*t+t]);d=np.array([t,t+2]);e=np.ones_like(f)*30
    track=dict(values=f[0]+3,rf_hz=11.5e9);use=np.array([1,1,0,1,0,1,1,0],bool)
    radio=np.zeros(8);width=np.ones(2)
    a=training_profile(track,use,f,d,e,radio,width)
    changed=dict(track,values=track['values'].copy());changed['values'][~use]+=1e6
    f[:,~use]-=1e6;d[:,~use]+=1e6;e[:,~use]=-90;radio[~use]+=1e6
    b=training_profile(changed,use,f,d,e,radio,width)
    for key in a:np.testing.assert_array_equal(a[key],b[key])


def test_support_uses_only_active_training_owners_and_per_curve_confidence():
    rows=[dict(candidate_index=0)]*3
    tracks=[dict(receiver=1,channel=1),dict(receiver=1,channel=2),dict(receiver=2,channel=1)]
    weights,owners,_=family_weights(rows,[0,1,2],tracks,[1.,.7,1.],'cross_rx_support',[10,10,0])
    np.testing.assert_array_equal(weights,[.6,.2,.6]);assert owners[0]=={(1,1),(1,2)}
    weights,_,_=family_weights(rows,[0,1,2],tracks,[1.,.7,1.],'cross_rx_support',[10,10,4])
    np.testing.assert_array_equal(weights,[1.,1.,1.])
