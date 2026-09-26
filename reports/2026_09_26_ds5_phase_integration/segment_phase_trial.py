"""Separate an offset reset from a possible identity change across a timing break."""
from pathlib import Path
import argparse,json,time
import numpy as np
from scipy.special import logsumexp
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
from cfo_scale_mixture import mixed_options,refine_bank
from shared_baseline_trial import load
from timing_trial import evaluate,quantile_indices
from segment_catalogue_trial import SID,OUT,HERE,SCALES,mixture
import catalogue_trial as T

def options_from_evidence(bank,train,joint,n=33):
    out=[]
    for i,cid in enumerate(bank['candidate_ids']):
        tr=train[i]+bank['logprior'][i];full=joint[i]+bank['logprior'][i]
        ix=quantile_indices(tr,n);jx=quantile_indices(full,n)
        out.append(dict(candidate_id=str(cid),train=float(logsumexp(tr)),held=float(logsumexp(full)-logsumexp(tr)),sample_held=joint[i,ix]-train[i,ix],projection=bank['projection'][i,ix],joint_projection=bank['projection'][i,jx]))
    return out

def predictive(options):
    tr=np.array([o['train'] for o in options]);he=np.array([o['held'] for o in options])
    return float(logsumexp(tr+he)-logsumexp(tr))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scale-only',action='store_true');args=parser.parse_args()
    started=time.monotonic();model=json.loads((HERE/'timing-calibration.json').read_text())['model'];store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:p=prepare_adaptive_tle_position_inputs(SID,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    results=[]
    for fold in (0,1):
        target,obs,old=load(SID,fold);times=np.array([o['time_s'] for o in target['observations']])+np.array(obs['phase_epoch_offsets_s']);receiver,_,axis=T.site_vectors(target['protocol']['site'])
        banks={name:dict(np.load(OUT/f'f{fold}-{name}.npz')) for name in ('whole','before','after')}
        bank=banks['whole'];pos,_,valid=propagate_candidate_states(p.catalogue,bank['indices'],p.start_utc_ns,times,bank['taus']);assert np.array_equal(valid,bank['indices']);dr=pos-receiver;projection=(dr/np.linalg.norm(dr,axis=-1)[...,None])@axis
        for name in banks:
            banks[name]['projection']=projection
            banks[name]=refine_bank(banks[name],model,.025)
        before,after=[banks[n] for n in ('before','after')]
        # The same identity/time must be physically visible in both episodes.
        # Finite-prior assertion from refine_bank above verifies this support.
        np.testing.assert_allclose(before['logprior'],after['logprior'])
        tr=mixture(before['train_residual'])+mixture(after['train_residual'])
        full=mixture(np.concatenate([before['train_residual'],before['held_residual']],axis=-1))+mixture(np.concatenate([after['train_residual'],after['held_residual']],axis=-1))
        continuous=mixed_options(banks['whole'],SCALES)[0]
        reset=options_from_evidence(after,tr,full)
        pre=mixed_options(before,SCALES)[0];post=mixed_options(after,SCALES)[0]
        right=mixed_options(refine_bank(old[1],model,.025),SCALES)[0]
        arms=[('continuous_identity_and_offset',continuous,0.),('same_identity_offset_reset',reset,0.),('independent_episode_identities',post,predictive(pre))]
        if args.scale_only:
            from segment_uncertainty import evidence_arms
            tr=evidence_arms(before['train_residual'],after['train_residual'])['shared_offset_separate_scales']
            full=evidence_arms(np.concatenate([before['train_residual'],before['held_residual']],axis=-1),np.concatenate([after['train_residual'],after['held_residual']],axis=-1))['shared_offset_separate_scales']
            arms=[('same_identity_shared_offset_separate_scales',options_from_evidence(after,tr,full),0.)]
        for arm,left,extra in arms:
            result=evaluate(left,right,np.array(obs['phase_rad']),np.array(obs['training_mask'],bool),np.array([o['f0'] for o in target['observations']]),np.array([o['f1'] for o in target['observations']]),np.array(obs['kappa']))
            result.update(fold=fold,arm=arm,pre_episode_held_log_predictive=extra,total_cfo_held=result['exact_cfo_held']+extra,total_cfo_phase_held=result['cfo_held_after_phase']+extra,left_candidates=len(left),right_candidates=len(right))
            results.append(result);print(fold,arm,'CFO baseline',result['total_cfo_held'],'phase gain',result['cfo_gain'],'top',result['top_before'],result['top_after'],flush=True)
            (OUT/('phase-scale-only-results.json' if args.scale_only else 'phase-results.json')).write_text(json.dumps(dict(protocol='Mode0 re-proposed whole/before/after catalogue banks; same CFO coverage; uniform signed baseline +/-2m; all qualified phase after supported break. Mode1 retains previous candidate bank. 33 quantiles, .025s tau; uncertainty mixture. Independent episode identity prior factorizes; no claimed identity truth. Scale-only follow-up is exploratory after reviewing the uncertainty ablation.',experiments=results,elapsed_s=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':main()
