"""Re-propose catalogue identities on both sides of an acquisition timing break."""
from pathlib import Path
from types import SimpleNamespace
import json,time
import numpy as np
from scipy.special import logsumexp
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
import catalogue_trial as T
from timing_trial import prior_weights

HERE=Path(__file__).resolve().parent
OUT=HERE/'segment-catalogue'
SID='scan-fw-888fc1e1e005ded3'
SCALES=[3.125,6.25,12.5,25,50,100,200,400,800,1600]

def mixture(values):
    return logsumexp(np.stack([T.constant_log_evidence(values,s) for s in SCALES]),axis=0)-np.log(len(SCALES))

def block_residuals(raw,times,mask,episodes):
    # Episode-aware grouping on BOTH sides of every comparison: no sample is
    # omitted, and an episode boundary inside one second cannot change coverage.
    parts=[];metadata=[]
    for episode in np.unique(episodes):
        keep=mask&(episodes==episode)
        if not keep.any():continue
        parts.append(T.average_blocks(raw,times,keep))
        metadata.extend((int(episode),int(b)) for b in np.unique(np.floor(times[keep]).astype(int)))
    return np.concatenate(parts,axis=-1),metadata

def components(tr,te,meta_tr,meta_te):
    yield 'whole',tr,te
    for episode in (0,1):
        yield ['before','after'][episode],tr[...,np.array([r[0]==episode for r in meta_tr])],te[...,np.array([r[0]==episode for r in meta_te])]

def main():
    OUT.mkdir(exist_ok=True);started=time.monotonic()
    audit=json.loads((HERE/'phase-episodes/support-audit.json').read_text())
    breaks=[r['time_s'] for t in audit['tracks'] if t['session_id']==SID and t['mode']==0 for r in t['supported_breaks']];assert len(breaks)==1
    boundary=breaks[0];members=json.loads((HERE/'timing-trial'/f'{SID}-f1-q65-b161-membership.json').read_text())['tracks'];m=members[0]
    times=np.array(m['times_s']);measured=np.array(m['measured_hz']);episodes=(times>=boundary).astype(int)
    priors=[json.loads((HERE/'timing-trial'/f'{SID}-f{f}-q33.json').read_text()) for f in (0,1)];site=priors[0]['protocol']['site'];cal=json.loads((HERE/'timing-calibration.json').read_text())
    masks=[]
    for fold in (0,1):
        T.FOLD=fold;pt=np.array([r['time_s'] for r in priors[fold]['observations']]);T.PARTITION_OVERRIDES[SID]={int(b):bool(v) for b,v in zip(T.visit_bins(SID,pt),priors[fold]['phase_training_mask'])};masks.append(T.partition(SID,times))
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:p=prepare_adaptive_tle_position_inputs(SID,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert p.evidence_sha256==priors[0]['evidence_sha256'] and p.snapshot_digest==priors[0]['snapshot_digest']
    receiver,up,axis=T.site_vectors(site);epochs=p.catalogue.element_epoch_utc_ns();coarse=np.arange(-120,121,5.)
    protocol=dict(session_id=SID,break_s=boundary,mode=0,selection='Train-only full catalogue coarse 5s timing search; union top16 under mixed-scale evidence for whole/before/after, separately per fold; then direct .2s banks',candidate_count=len(p.candidate_indices),scales_hz=SCALES,coverage='Every original acquisition retained; identical (episode, second, fold) CFO blocks in all arms',meaning='Retrospective catalogue proposal and predictive test; timing break does not imply identity change; coarse search completeness not proven',evidence_sha256=p.evidence_sha256,snapshot_digest=p.snapshot_digest)
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    cache={}
    def lp(index,grid,is_coarse):
        age=(p.start_utc_ns-epochs[index])/3.6e12
        key=(float(age),is_coarse)
        if key not in cache:cache[key]=prior_weights(cal,age,grid,is_coarse)
        return cache[key]
    def propagate(indices,grid):
        pos,vel,valid=propagate_candidate_states(p.catalogue,indices,p.start_utc_ns,times,grid)
        dr=pos-receiver;unit=dr/np.linalg.norm(dr,axis=-1)[...,None]
        raw=measured+11.2e9/(299792458./1000)*np.sum(unit*vel,axis=-1)
        return valid,raw,unit@up
    pools=[[] for _ in (0,1)]
    for begin in range(0,len(p.candidate_indices),128):
        indices=p.candidate_indices[begin:begin+128];valid,raw,elevation=propagate(indices,coarse);prior=np.array([lp(i,coarse,True) for i in valid])
        for fold,mask in enumerate(masks):
            tr,mt=block_residuals(raw,times,mask,episodes);te,mh=block_residuals(raw,times,~mask,episodes)
            scores=[]
            for name,a,b in components(tr,te,mt,mh):
                used=mask if name=='whole' else mask&(episodes==({'before':0,'after':1}[name]))
                visible=np.max(elevation[...,used],axis=-1)>0
                scores.append(logsumexp(np.where(visible,mixture(a)+prior,-np.inf),axis=-1))
            pools[fold].extend(dict(index=int(i),scores=[float(s[j]) for s in scores]) for j,i in enumerate(valid))
        if begin%2048==0:print('coarse',begin,'/',len(p.candidate_indices),'elapsed',round(time.monotonic()-started,1),flush=True)
    (OUT/'coarse.json').write_text(json.dumps(dict(protocol=protocol,folds=pools),indent=2)+'\n')
    fine=np.arange(-600,601)/5;cache.clear();summaries=[]
    for fold,mask in enumerate(masks):
        selected=sorted(set().union(*[{r['index'] for r in sorted(pools[fold],key=lambda r:-r['scores'][j])[:16]} for j in range(3)]))
        # Ensure the former full-track proposal candidates remain available.
        original=dict(np.load(HERE/'timing-trial'/f'{SID}-f{fold}-{m["track_id"][7:19]}.npz'))
        selected=sorted(set(selected)|set(map(int,original['indices'])))
        valid,raw,elevation=propagate(selected,fine);prior=np.array([lp(i,fine,False) for i in valid])
        tr,mt=block_residuals(raw,times,mask,episodes);te,mh=block_residuals(raw,times,~mask,episodes)
        for name,a,b in components(tr,te,mt,mh):
            used=mask if name=='whole' else mask&(episodes==({'before':0,'after':1}[name]))
            visible=np.max(elevation[...,used],axis=-1)>0;weights=np.where(visible,prior,-np.inf)
            bank=dict(indices=valid,candidate_ids=np.asarray(p.catalogue.satellite_numbers)[valid],taus=fine,logprior=weights,train_residual=a,held_residual=b)
            np.savez_compressed(OUT/f'f{fold}-{name}.npz',**bank)
            train=logsumexp(mixture(a)+weights,axis=-1);full=logsumexp(mixture(np.concatenate([a,b],axis=-1))+weights,axis=-1);prob=np.exp(train-logsumexp(train));order=np.argsort(-prob)
            row=dict(fold=fold,episode=name,train_blocks=a.shape[-1],held_blocks=b.shape[-1],candidates=len(valid),held_log_predictive=float(logsumexp(full)-logsumexp(train)),top=[dict(candidate_id=str(bank['candidate_ids'][i]),probability=float(prob[i])) for i in order[:8]])
            summaries.append(row);print(row,flush=True)
        (OUT/'summary.json').write_text(json.dumps(dict(protocol=protocol,results=summaries,block_metadata=dict(fold=fold,train=mt,held=mh),elapsed_s=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':main()
