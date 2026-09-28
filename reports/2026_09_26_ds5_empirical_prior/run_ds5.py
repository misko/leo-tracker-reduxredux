"""Frozen empirical-prior DS5 diagnostic; no geographic search or external writes."""
import argparse,hashlib,json,os,sys,time,traceback
from pathlib import Path
import numpy as np
from scipy.stats import t

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_26_reno_track_audit'))
sys.path.insert(0,str(REPORTS/'2026_09_26_ds5_0850_diagnosis'))
from compare_scan_clock import (ScannerTrackingInputStore,TleArchiveReader,prepare_adaptive_tle_position_inputs,
    build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory)
from probabilistic_core import fit_profiles,prior_weights,scale_at
from joint_selection import select_joint
from empirical_prior import discrete_weights,age_bin
from timing_model import evaluate

MANIFEST=Path('/home/mouse9911/gits/leo-adaptive-position-deploy/reports/2026_09_26_ds5_since_local_midnight/manifest.json')
DEVELOPMENT={'scan-fw-dc1153010e57ac76','scan-fw-d86e8f23c0624bac'}
COARSE=np.arange(-60.,61.,15.)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path,data):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');os.replace(tmp,path)


def shortlist(p,sites,original):
    path=HERE/'shortlists'/f'{p.session_id}.json' if hasattr(p,'session_id') else None
    # Caller supplies session-specific caching; this function is numerical orchestration only.
    best={s:{track.track_id:[] for track in p.tracks} for s in sites}
    for start in range(0,len(p.candidate_indices),256):
        banks,_=build_prediction_banks(p.catalogue,p.candidate_indices[start:start+256],p.start_utc_ns,p.tracks,taus_s=COARSE)
        for site,loc in sites.items():
            for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=COARSE)(0,0):
                mask=np.asarray(b.training_mask,bool)
                residual=b.measured_hz[mask][None,None,:]-b.predictions_hz[:,:,mask]
                residual-=residual.mean(axis=2,keepdims=True)
                rms=np.sqrt(np.mean(residual**2,axis=2));j=np.argmin(rms,axis=1)
                visible=np.asarray(b.visible).reshape(-1)
                scores=np.where(visible,rms[np.arange(len(j)),j],np.inf)
                for i in np.argsort(scores)[:3]:
                    if not np.isfinite(scores[i]):continue
                    best[site][b.track_id].append({'candidate_id':str(b.candidate_ids[i]),'training_rms_hz':float(scores[i]),'coarse_tau_s':float(COARSE[j[i]])})
                best[site][b.track_id]=sorted(best[site][b.track_id],key=lambda r:(r['training_rms_hz'],int(r['candidate_id'])))[:3]
    return best


def scan(capture,old,calibration,history,prior_cache):
    started=time.monotonic();sid=capture['session_id'];store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert p.evidence_sha256==old['evidence_sha256'] and p.snapshot_digest==old['snapshot_digest']
    assert calibration['latest_history_snapshot_ns']<p.start_utc_ns
    sites=old['sites'];original=old['fixed_identities'];coarse_path=HERE/'shortlists'/f'{sid}.json'
    if coarse_path.exists():
        cached=json.loads(coarse_path.read_text())
        assert cached['evidence_sha256']==p.evidence_sha256 and cached['snapshot_digest']==p.snapshot_digest
        assert cached['sites']==sites and cached['coarse_grid_s']==COARSE.tolist()
        candidates=cached['candidates']
    else:
        candidates=shortlist(p,sites,original)
        atomic(coarse_path,{'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,'sites':sites,
            'coarse_grid_s':COARSE.tolist(),'candidates':candidates})
    coarse_elapsed=time.monotonic()-started
    print(sid,'coarse complete',round(coarse_elapsed,1),'s',flush=True)
    total=np.round(np.arange(-1230,1231)/10,1);delta=np.round(np.arange(-1200,1201)/10,1)
    narrow=np.round(np.arange(-600,601)/10,1);center=np.arange(30,len(total)-30)
    lookup={str(n):i for i,n in enumerate(p.catalogue.satellite_numbers)};epochs=p.catalogue.element_epoch_utc_ns()
    ages={};omitted={};newpriors={};oldpriors={};narrowpriors={};options={s:{} for s in sites}
    for track in p.tracks:
        allowed={s:{r['candidate_id'] for r in candidates[s][track.track_id]}|{original[s][track.track_id]['candidate_id']} for s in sites}
        ids=sorted(set().union(*allowed.values()),key=int)
        for cid in ids:
            if cid in ages:continue
            age=(p.start_utc_ns-epochs[lookup[cid]])/3.6e12;ages[cid]=age
            b=age_bin(calibration['model'],age);key=b['lower_h']
            if key not in prior_cache:prior_cache[key]=discrete_weights(calibration['model'],age,delta)
            newpriors[cid],omitted[cid]=prior_cache[key]
            scale=scale_at(age,history['bins']);oldpriors[cid]=prior_weights(delta,scale)
            narrowpriors[cid]=prior_weights(narrow,scale)
        banks,_=build_prediction_banks(p.catalogue,[lookup[c] for c in ids],p.start_utc_ns,[track],taus_s=total)
        for site,loc in sites.items():
            found={}
            for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=total)(0,0):
                for i,cidraw in enumerate(b.candidate_ids):
                    cid=str(cidraw)
                    if cid not in allowed[site] or not b.visible[i]:continue
                    prof=fit_profiles(b.measured_hz,b.predictions_hz[i],b.training_mask,100.)
                    found[cid]=dict(track_id=track.track_id,satellite_id=cid,
                        weight_s=len(np.unique(np.floor(track.times_s))),**prof)
            assert original[site][track.track_id]['candidate_id'] in found
            options[site][track.track_id]=found
    fine_elapsed=time.monotonic()-started-coarse_elapsed
    chosen={};receipts={}
    for site in sites:
        # Identity optimization sees only the no-scan-clock satellite support.
        sliced={tid:{cid:dict(row,train=row['train'][center]) for cid,row in rr.items()} for tid,rr in options[site].items()}
        frozen={tid:r['candidate_id'] for tid,r in original[site].items()}
        chosen[site]={'frozen':frozen};receipts[site]={}
        for name,priors in [('old',oldpriors),('empirical',newpriors)]:
            selection,receipt=select_joint(sliced,frozen,priors,max_passes=20)
            assert selection['converged']
            chosen[site][name]=selection['ids'];receipts[site][name]={'selected':selection,'starts':receipt['starts'],
                'all_starts_converged':all(r['converged'] for r in receipt['runs']),
                'training_scores_by_start':[r['training_score'] for r in receipt['runs']]}
    experiments=[]
    for mode,identity,priors,dg,clock in [
        ('old_frozen_60','frozen',narrowpriors,narrow,np.array([0.])),
        ('old_frozen','frozen',oldpriors,delta,np.array([0.])),
        ('empirical_frozen','frozen',newpriors,delta,np.array([0.])),
        ('old_joint','old',oldpriors,delta,np.array([0.])),
        ('empirical_joint','empirical',newpriors,delta,np.array([0.])),
        ('empirical_joint_scan_clock','empirical',newpriors,delta,np.round(np.arange(-30,31)/10,1))]:
        fit={}
        for site in sites:
            ids=chosen[site][identity];rr=[options[site][tid][cid] for tid,cid in ids.items()]
            fit[site]=evaluate(rr,total,dg,clock,1. if len(clock)>1 else None,priors)
            fit[site]['identity_changes_from_frozen']=sum(cid!=chosen[site]['frozen'][tid] for tid,cid in ids.items())
            fit[site]['max_empirical_prior_mass_outside_120s']=max(omitted[cid] for cid in ids.values())
        experiments.append({'mode':mode,'noise_scale_hz':100.,'sites':fit})
    old_arm=next(e for e in old['experiments'] if e['mode']=='age_satellite' and e['noise_scale_hz']==100)
    parity=max(abs(experiments[0]['sites'][s]['negative_log_score_per_test_observation']-old_arm['sites'][s]['negative_log_score_per_test_observation']) for s in sites)
    assert parity<1e-7,parity
    return {'session_id':sid,'capture_start_utc':capture['capture_start_utc'],'sample_rate_hz':capture['sample_rate_hz'],
        'development_case':sid in DEVELOPMENT,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
        'document_sha256':old['document_sha256'],'sites':sites,'track_count':len(p.tracks),'candidate_count':len(p.candidate_indices),
        'age_hours':ages,'empirical_prior_mass_outside_120s':omitted,'joint_selection':receipts,
        'experiments':experiments,'baseline_parity_max_nll_difference':parity,
        'coarse_elapsed_s':coarse_elapsed,'fine_elapsed_s':fine_elapsed,'elapsed_s':time.monotonic()-started}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shard',type=int,default=0);parser.add_argument('--shards',type=int,default=2)
    parser.add_argument('--limit',type=int);args=parser.parse_args()
    manifest=json.loads(MANIFEST.read_text());old_path=REPORTS/'2026_09_26_ds5_probabilistic/results.json'
    old=json.loads(old_path.read_text());previous={s['session_id']:s for s in old['scans']}
    cal_path=HERE/'calibration.json';cal=json.loads(cal_path.read_text())
    history=json.loads((REPORTS/'2026_09_26_reno_track_audit/probabilistic_history.json').read_text())
    assert digest(MANIFEST)==old['protocol']['manifest_sha256']
    captures=[c for i,c in enumerate(manifest['captures']) if c['admission_status']=='included' and i%args.shards==args.shard]
    (HERE/'shortlists').mkdir(exist_ok=True)
    path=HERE/f'results_shard_{args.shard}.json'
    protocol={'manifest_sha256':digest(MANIFEST),'previous_results_sha256':digest(old_path),'calibration_sha256':digest(cal_path),
        'source_sha256':digest(Path(__file__)),'timing_core_sha256':digest(HERE/'timing_model.py'),
        'joint_core_sha256':digest(REPORTS/'2026_09_26_ds5_0850_diagnosis/joint_selection.py'),
        'scope':'retrospective fixed sites; original masks reused; no new geographic search or cross-site candidates/corrections',
        'prior_fit':'historical training satellite groups only; frozen before validation and DS5',
        'candidate_selection':'all tracks, all catalogue: training-only OLS coarse -60..60 step15 top3/site/track plus previous training-zero winner; no test access',
        'joint_selection':'multi-start coordinate ascent of training integrated shared-timing evidence; approximate, not identity marginalization',
        'grid_s':[-120,120,.1],'support':'continuous priors conditioned on numerical support; omitted prior mass explicitly reported',
        'clock':'sigma1s truncated +/-3s; sensitivity with identities frozen from no-clock joint selection',
        'noise_scale_hz':100,'cfos':'training-profiled, not integrated','observation_independence':'approximation; no new heldout radio validation',
        'development_cases':sorted(DEVELOPMENT)}
    if path.exists():
        output=json.loads(path.read_text());assert output['protocol']==protocol
    else:output={'protocol':protocol,'shard':args.shard,'shards':args.shards,'expected_sessions':[c['session_id'] for c in captures],'scans':[],'failures':[]}
    done={s['session_id'] for s in output['scans']}|{s['session_id'] for s in output['failures']}
    todo=[c for c in captures if c['session_id'] not in done]
    if args.limit is not None:todo=todo[:args.limit]
    cache={}
    for c in todo:
        try:
            result=scan(c,previous[c['session_id']],cal,history,cache);output['scans'].append(result)
            print('DONE',c['session_id'],round(result['elapsed_s'],1),'s',flush=True)
        except Exception as exc:
            output['failures'].append({'session_id':c['session_id'],'error':repr(exc),'traceback':traceback.format_exc()});traceback.print_exc()
        atomic(path,output)


if __name__=='__main__':main()
