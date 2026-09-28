"""Held-out fixed-site comparison for scan-fw-60d9d1e77c14da0a."""
import hashlib,importlib.util,json,os,sys,time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent;SID='scan-fw-60d9d1e77c14da0a'
for path in (REPORTS/'2026_09_26_reno_track_audit',REPORTS/'2026_09_26_ds5_empirical_prior'):
    sys.path.insert(0,str(path))
from compare_scan_clock import (ScannerTrackingInputStore,TleArchiveReader,prepare_adaptive_tle_position_inputs,
    build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory)
from empirical_prior import discrete_weights,age_bin


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);return module


BASE=load('heldout_ds5_baseline',REPORTS/'2026_09_26_ds5_probabilistic/run_ds5.py')
SHORT=load('heldout_shortlist',REPORTS/'2026_09_26_ds5_empirical_prior/run_ds5.py')
JOINT=load('heldout_joint_core',REPORTS/'2026_09_26_joint_mixture/core.py')
SOFT=load('heldout_soft_core',REPORTS/'2026_09_26_independent_soft/core.py')
CALPATH=REPORTS/'2026_09_26_ds5_empirical_prior/calibration.json'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');os.replace(tmp,path)


def published_legacy_rms(prepared,sites):
    """Reproduce the published capped-RMS objective, including evaluation-selected IDs."""
    banks,_=build_prediction_banks(prepared.catalogue,prepared.candidate_indices,prepared.start_utc_ns,prepared.tracks)
    output={}
    for site,loc in sites.items():
        chosen={}
        for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']))(0,0):
            mask=np.asarray(b.training_mask,bool);residual=b.measured_hz[None,None,:]-b.predictions_hz
            offset=residual[:,:,mask].mean(axis=2);centered=residual-offset[:,:,None]
            tr=np.sqrt(np.mean(centered[:,:,mask]**2,axis=2));te=np.sqrt(np.mean(centered[:,:,~mask]**2,axis=2))
            visible=np.asarray(b.visible)
            if visible.ndim==1:visible=visible[:,None]
            tr=np.where(visible,tr,np.inf);weight=len(np.unique(np.floor(b.times_s)))
            for i,cid in enumerate(b.candidate_ids):
                j=int(np.argmin(tr[i]))
                if not np.isfinite(tr[i,j]):continue
                row={'track_id':b.track_id,'candidate_id':str(cid),'training_rms_hz':float(tr[i,j]),
                    'heldout_rms_hz':float(te[i,j]),'tau_s':float(b.taus_s[j]),'weight_s':weight}
                key=lambda r:(r['heldout_rms_hz'],r['training_rms_hz'],int(r['candidate_id']))
                if b.track_id not in chosen or key(row)<key(chosen[b.track_id]):chosen[b.track_id]=row
        if len(chosen)!=len(prepared.tracks):raise RuntimeError(f'{site}: incomplete published baseline')
        denominator=sum(r['weight_s'] for r in chosen.values())
        output[site]={'capped_weighted_rmse_hz':float(np.sqrt(sum(r['weight_s']*min(800.,r['heldout_rms_hz'])**2 for r in chosen.values())/denominator)),
            'uncapped_weighted_rmse_hz':float(np.sqrt(sum(r['weight_s']*r['heldout_rms_hz']**2 for r in chosen.values())/denominator)),
            'tracks':list(chosen.values())}
    return output


def main():
    started=time.monotonic();cal=json.loads(CALPATH.read_text())
    from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2
    root=Path('/srv/bulk/leo');manifest=AdaptiveTlePositionStoreV2(root).status(SID).manifest
    document=manifest.document.model_dump(mode='json');sites=BASE.sites_from_document(document)
    store=ScannerTrackingInputStore(root)
    try:p=prepare_adaptive_tle_position_inputs(SID,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert p.evidence_sha256==document['evidence_sha256'] and cal['latest_history_snapshot_ns']<p.start_utc_ns
    published_baseline=published_legacy_rms(p,sites)
    for name in ('sacramento','reno'):
        expected=next(r['selected']['capped_weighted_rmse_hz'] for r in document['priors'] if r['name']==name)
        assert abs(published_baseline[name]['capped_weighted_rmse_hz']-expected)<1e-6
    original=BASE.select_zero_timing(p,sites)
    shortpath=HERE/'shortlist.json'
    if shortpath.exists():
        saved=json.loads(shortpath.read_text());assert saved['evidence_sha256']==p.evidence_sha256 and saved['snapshot_digest']==p.snapshot_digest
        assert saved['sites']==sites and saved['coarse_grid_s']==SHORT.COARSE.tolist();candidates=saved['candidates']
    else:
        candidates=SHORT.shortlist(p,sites,original)
        atomic(shortpath,{'session_id':SID,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
            'sites':sites,'coarse_grid_s':SHORT.COARSE.tolist(),'candidates':candidates})
    print('SHORTLIST_COMPLETE',round(time.monotonic()-started,1),flush=True)
    total=np.arange(-1230,1231)/10;delta=np.arange(-1200,1201)/10
    ix=np.rint((delta-total[0])/.1).astype(int)[None,:]
    lookup={str(c):i for i,c in enumerate(p.catalogue.satellite_numbers)};epochs=p.catalogue.element_epoch_utc_ns()
    priors={};omitted={};cache={};options={s:{} for s in sites}
    for track in p.tracks:
        tid=track.track_id;mask=np.asarray(track.training_mask,bool)
        allowed={s:{r['candidate_id'] for r in candidates[s][tid]}|{original[s][tid]['candidate_id']} for s in sites}
        ids=sorted(set().union(*allowed.values()),key=int)
        for cid in ids:
            if cid in priors:continue
            age=(p.start_utc_ns-epochs[lookup[cid]])/3.6e12;key=age_bin(cal['model'],age)['lower_h']
            if key not in cache:cache[key]=discrete_weights(cal['model'],age,delta)
            priors[cid],omitted[cid]=cache[key]
        banks,_=build_prediction_banks(p.catalogue,[lookup[c] for c in ids],p.start_utc_ns,[track],taus_s=total)
        for site,loc in sites.items():
            found={}
            for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=total)(0,0):
                for i,craw in enumerate(b.candidate_ids):
                    cid=str(craw)
                    if cid not in allowed[site] or not b.visible[i]:continue
                    residual=b.measured_hz[None,:]-b.predictions_hz[i]
                    tr=SOFT.block_average(track.times_s,residual,mask);te=SOFT.block_average(track.times_s,residual,~mask)
                    f=SOFT.profiles(tr,te,100.)
                    found[cid]={'train':f['train'][ix],'predict':f['predict'][ix],'n_test':f['n_test']}
            assert original[site][tid]['candidate_id'] in found and found
            options[site][tid]=found
    results={}
    for site,opts in options.items():
        frozen={tid:original[site][tid]['candidate_id'] for tid in opts}
        baseline=JOINT.assess(opts,priors,[(frozen,0)])
        soft=SOFT.exact_soft(opts,priors,np.array([0.]))
        results[site]={'baseline_frozen':baseline,'soft':soft}
    summary={}
    for model in ('baseline_frozen','soft'):
        scores={s:results[s][model]['composite_nll_per_test_block'] for s in sites}
        summary[model]={'scores':scores,'winner':min(scores,key=scores.get),
            'reference_minus_sacramento':scores['reference']-scores['sacramento'],
            'reference_minus_reno':scores['reference']-scores['reno']}
    output={'session_id':SID,'capture_start_utc_ns':p.start_utc_ns,'track_count':len(p.tracks),
        'document_sha256':manifest.document_sha256,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
        'sites':sites,'location_errors_m':{x:next(r['selected']['horizontal_error_m'] for r in document['priors'] if r['name']==x) for x in ('sacramento','reno')},
        'published_selected':{r['name']:r['selected'] for r in document['priors']},
        'published_legacy_rms':published_baseline,'summary':summary,'results':results,
        'max_prior_mass_outside_support':max(omitted.values()),'elapsed_s':time.monotonic()-started,
        'protocol':{'noise_hz':100.,'clock_s':0.,'candidate_selection':'each site independently; full-catalogue zero-time frozen baseline plus training-only coarse top3+original for soft model',
            'timing':'empirical TLE-age prior, +/-120 seconds at 0.1-second resolution; independent per track in soft arm; shared by frozen satellite ID in baseline',
            'scoring':'held-out one-second block conditional predictive NLL; lower is better; original masks reused',
            'published_baseline_warning':'capped RMS reproduces the deployed randomized-evaluation-rms-v1 identity selection and therefore uses evaluation values to select IDs; shown separately and not directly comparable to training-only predictive NLL',
            'no_leakage':'evaluation values do not affect identities, shortlist, timing posterior, or soft assignment probabilities; no candidates shared across sites',
            'calibration_sha256':digest(CALPATH),'baseline_source_sha256':digest(REPORTS/'2026_09_26_ds5_probabilistic/run_ds5.py'),
            'shortlist_source_sha256':digest(REPORTS/'2026_09_26_ds5_empirical_prior/run_ds5.py'),
            'soft_core_sha256':digest(REPORTS/'2026_09_26_independent_soft/core.py'),'runner_sha256':digest(Path(__file__))}}
    atomic(HERE/'results.json',output);print(json.dumps(summary,indent=2));print('DONE',round(output['elapsed_s'],1),flush=True)


if __name__=='__main__':main()
