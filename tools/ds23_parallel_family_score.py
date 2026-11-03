"""Same family-predictive score, scheduling independent folds on eight cores."""

from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import numpy as np

from ds23_multifamily_proposals import prediction
from ds23_fast_family_prediction import fast_gaussian_predictive
import ds23_multifamily_proposals as original
from ds23_frequency_events import make_event_problem
from probe_ds23_frequency_events import cached
from ds23_pruned_training_moments import make_training_problem

_CONTEXT=None


def _initialize(context):
    global _CONTEXT
    _CONTEXT=context
    original.gaussian_predictive=fast_gaussian_predictive


def _fold(family):
    scan,node,mask,arm,powers,means,model,position,labels=_CONTEXT
    train=mask&(labels!=family);test=mask&(labels==family);reference=np.zeros(len(means))
    for _ in range(5):
        p=cached(make_training_problem(scan,node,train,arm,reference,powers,means,model))
        phase=np.clip(p.state(position)['phases'][p.labels],-15,15)
        change=float(max(abs(phase-p.reference)));reference=phase
    result=prediction(p,position,train,test,int(family),powers)
    return dict(norad=int(scan.norads[family]),family=int(family),points=int(test.sum()),
        phase_change_s=change,negative_twice_log_density=result['negative_twice_log_density'],
        RMS_hz=result['RMS_hz'],maximum_sigma_hz=float(result['marginal_sigma_hz'].max()))


def score_position(scan,node,mask,arm,powers,means,model,position):
    base=make_event_problem(scan,node,mask,arm,np.zeros(len(means)),powers,means,model,[])
    labels=np.asarray(base.labels)[base.flat_labels];families=np.unique(labels[mask])
    # Prewarm the shared read-only mode bank before independent fold threads.
    context=(scan,node,mask,arm,powers,means,model,position,labels)
    with ProcessPoolExecutor(max_workers=8,mp_context=get_context('fork'),initializer=_initialize,initargs=(context,)) as pool:
        rows=list(pool.map(_fold,families))
    if sum(r['points'] for r in rows)!=int(mask.sum()):raise ValueError('parallel folds changed original evidence coverage')
    return dict(score=float(sum(r['negative_twice_log_density'] for r in rows)),folds=rows,
        qualified=all(r['phase_change_s']<=.01 for r in rows),scored_original_curved_points=int(mask.sum()),
        no_held_family_in_calibration=True,
        approximation='local moment-matched Gaussian predictive composite score; fixed position, unseen Gamma noise')
