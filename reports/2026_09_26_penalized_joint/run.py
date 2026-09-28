"""Fixed-site DS5 identity-prior experiment; no geographic search."""
import argparse,hashlib,json,math,os,sys,time,traceback
from pathlib import Path
import numpy as np
from scipy.stats import t

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_26_ds5_empirical_prior'))
from empirical_prior import discrete_weights,age_bin
from timing_model import evaluate
sys.path.insert(0,str(REPORTS/'2026_09_26_reno_track_audit'))
from compare_scan_clock import (ScannerTrackingInputStore,TleArchiveReader,prepare_adaptive_tle_position_inputs,
    build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory)
from probabilistic_core import fit_profiles
from joint_selection import select_joint

PENALTIES=(0.,math.log(12.),5.)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path,data):
    tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');os.replace(tmp,path)


def scan(sid,prior,calibration,prior_cache):
    started=time.monotonic();shortpath=REPORTS/'2026_09_26_ds5_empirical_prior/shortlists'/f'{sid}.json'
    shortlist=json.loads(shortpath.read_text());store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert p.evidence_sha256==prior['evidence_sha256']==shortlist['evidence_sha256']
    assert p.snapshot_digest==prior['snapshot_digest']==shortlist['snapshot_digest']
    assert shortlist['sites']==prior['sites'] and calibration['latest_history_snapshot_ns']<p.start_utc_ns
    total=np.arange(-1230,1231)/10;delta=np.arange(-1200,1201)/10;center=np.arange(30,len(total)-30)
    lookup={str(n):i for i,n in enumerate(p.catalogue.satellite_numbers)};epochs=p.catalogue.element_epoch_utc_ns()
    frozen=next(e for e in prior['experiments'] if e['mode']=='empirical_frozen')
    frozen_ids={site:{r['track_id']:r['satellite_id'] for r in frozen['sites'][site]['tracks']}
        for site in prior['sites']}
    priors={};omitted={};options={s:{} for s in prior['sites']};original={s:{} for s in prior['sites']}
    for track in p.tracks:
        allowed={s:{r['candidate_id'] for r in shortlist['candidates'][s][track.track_id]}|
            {frozen_ids[s][track.track_id]} for s in prior['sites']}
        ids=sorted(set().union(*allowed.values()),key=int)
        for cid in ids:
            if cid in priors:continue
            age=(p.start_utc_ns-epochs[lookup[cid]])/3.6e12;key=age_bin(calibration['model'],age)['lower_h']
            if key not in prior_cache:prior_cache[key]=discrete_weights(calibration['model'],age,delta)
            priors[cid],omitted[cid]=prior_cache[key]
        banks,_=build_prediction_banks(p.catalogue,[lookup[c] for c in ids],p.start_utc_ns,[track],taus_s=total)
        for site,loc in prior['sites'].items():
            found={};original[site][track.track_id]=frozen_ids[site][track.track_id]
            for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=total)(0,0):
                for i,craw in enumerate(b.candidate_ids):
                    cid=str(craw)
                    if cid not in allowed[site] or not b.visible[i]:continue
                    prof=fit_profiles(b.measured_hz,b.predictions_hz[i],b.training_mask,100.)
                    found[cid]=dict(track_id=track.track_id,satellite_id=cid,
                        weight_s=len(np.unique(np.floor(track.times_s))),**prof)
            assert original[site][track.track_id] in found
            options[site][track.track_id]=found
    experiments=[];receipts={}
    for penalty in PENALTIES:
        sites={};receipts[str(penalty)]={}
        for site in prior['sites']:
            sliced={tid:{cid:dict(r,train=r['train'][center]) for cid,r in rr.items()} for tid,rr in options[site].items()}
            chosen,receipt=select_joint(sliced,original[site],priors,penalty,max_passes=20)
            assert chosen['converged'] and all(r['converged'] for r in receipt['runs'])
            rows=[options[site][tid][cid] for tid,cid in chosen['ids'].items()]
            fit=evaluate(rows,total,delta,np.array([0.]),None,priors)
            fit['identity_changes_from_original']=chosen['changes']
            fit['max_empirical_prior_mass_outside_120s']=max(omitted[c] for c in chosen['ids'].values())
            sites[site]=fit
            receipts[str(penalty)][site]={'selected':chosen,'starts':receipt['starts'],
                'all_starts_converged':all(r['converged'] for r in receipt['runs'])}
        experiments.append({'change_penalty_nats':penalty,'sites':sites})
    # Penalty zero must reproduce the completed deterministic empirical-joint result.
    expected=next(e for e in prior['experiments'] if e['mode']=='empirical_joint')
    parity=max(abs(experiments[0]['sites'][s]['negative_log_score_per_test_observation']-
        expected['sites'][s]['negative_log_score_per_test_observation']) for s in prior['sites'])
    assert parity<1e-9,parity
    return {'session_id':sid,'capture_start_utc':prior['capture_start_utc'],'sample_rate_hz':prior['sample_rate_hz'],
        'track_count':len(p.tracks),'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
        'shortlist_sha256':digest(shortpath),'experiments':experiments,'selection':receipts,
        'zero_penalty_parity_max_nll_difference':parity,'elapsed_s':time.monotonic()-started}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shard',type=int,required=True);parser.add_argument('--shards',type=int,default=4)
    args=parser.parse_args();priorpath=REPORTS/'2026_09_26_ds5_empirical_prior/results.json';old=json.loads(priorpath.read_text())
    calpath=REPORTS/'2026_09_26_ds5_empirical_prior/calibration.json';cal=json.loads(calpath.read_text())
    scans=[s for i,s in enumerate(old['scans']) if i%args.shards==args.shard];path=HERE/f'results_v2_shard_{args.shard}.json'
    protocol={'prior_results_sha256':digest(priorpath),'calibration_sha256':digest(calpath),'source_sha256':digest(Path(__file__)),
        'selection_core_sha256':digest(HERE/'joint_selection.py'),'timing_core_sha256':digest(REPORTS/'2026_09_26_ds5_empirical_prior/timing_model.py'),
        'penalties_nats':PENALTIES,'primary_penalty_interpretation':'log(12): prior odds 12:1 for original ID versus any one alternative',
        'scope':'fixed independent sites; cached site-specific top3+original; no geographic search or cross-site proposals',
        'selection':'multi-start coordinate ascent of empirical-prior shared-satellite timing training evidence minus change penalty',
        'scoring':'conditional empirical-prior predictive NLL with selected IDs; penalty affects training selection only, not evaluation score'}
    if path.exists():out=json.loads(path.read_text());assert out['protocol']==protocol
    else:out={'protocol':protocol,'shard':args.shard,'shards':args.shards,'expected_sessions':[s['session_id'] for s in scans],'scans':[],'failures':[]}
    done={s['session_id'] for s in out['scans']}|{f['session_id'] for f in out['failures']};cache={}
    for s in scans:
        if s['session_id'] in done:continue
        try:r=scan(s['session_id'],s,cal,cache);out['scans'].append(r);print('DONE',s['session_id'],round(r['elapsed_s'],1),flush=True)
        except Exception as exc:out['failures'].append({'session_id':s['session_id'],'error':repr(exc),'traceback':traceback.format_exc()});traceback.print_exc()
        atomic(path,out)


if __name__=='__main__':main()
