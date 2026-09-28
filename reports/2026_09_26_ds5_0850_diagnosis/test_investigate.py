import numpy as np
from investigate import coarse_score,group_audit
from scipy.special import logsumexp
from probabilistic_core import prior_weights
from joint_selection import select_joint


def test_shortlist_uses_only_training_observations():
    y=np.array([1.,2.,3.,4.]);p=np.arange(24.).reshape(2,3,4);mask=np.array([True,True,False,False])
    a=coarse_score(y,p,mask);y[~mask]+=1000;p[:,:,~mask]-=1000
    assert np.array_equal(a,coarse_score(y,p,mask))


def test_group_contributions_use_shared_latent_once():
    taus=np.array([-1.,0.,1.]);row={'satellite_id':'s','track_id':'a','train':np.array([-2.,0.,-1.]),'test':np.array([-3.,-1.,-2.]),'n_test':2}
    out=group_audit([row,row],taus,{'s':1})
    lp=prior_weights(taus,1)+2*row['train'];expected=logsumexp(lp+2*row['test'])-logsumexp(lp)
    assert abs(out[0]['conditional_predictive_log_score']-expected)<1e-12


def test_joint_identity_selection_accounts_for_existing_satellite_tracks_and_ignores_test():
    priors={cid:np.log(np.array([.5,.5])) for cid in ('1','2')}
    options={'fixed':{'1':{'train':np.array([0.,-100.])}},
             'variable':{'1':{'train':np.array([-100.,0.]),'test':np.array([999.,999.])},
                         '2':{'train':np.array([-1.,-1.]),'test':np.array([-999.,-999.])}}}
    initial={'fixed':'1','variable':'1'}
    best,_=select_joint(options,initial,priors)
    assert best['ids']=={'fixed':'1','variable':'2'}
    options['variable']['2']['test'][:]=1e9
    after,_=select_joint(options,initial,priors)
    assert after==best
