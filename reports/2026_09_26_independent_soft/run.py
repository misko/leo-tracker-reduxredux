"""All-DS5 deterministic soft-assignment evaluation; fixed sites only."""
import argparse,hashlib,json,os,sys,time,traceback
from pathlib import Path
import numpy as np
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parent
sys.path.insert(0,str(REPORTS/'2026_09_26_ds5_empirical_prior'))
from empirical_prior import discrete_weights,age_bin
sys.path.insert(0,str(REPORTS/'2026_09_26_reno_track_audit'))
from compare_scan_clock import (ScannerTrackingInputStore,TleArchiveReader,prepare_adaptive_tle_position_inputs,
    build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory)
from core import block_average,profiles,exact_soft

SOURCE=REPORTS/'2026_09_26_ds5_probabilistic/results.json'
CALIBRATION=REPORTS/'2026_09_26_ds5_empirical_prior/calibration.json'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path,data):
    tmp=path.with_suffix('.json.tmp');tmp.write_text(json.dumps(data,indent=2)+'\n');os.replace(tmp,path)


def scan(prior,calibration,prior_cache):
    started=time.monotonic();sid=prior['session_id']
    shortpath=REPORTS/'2026_09_26_ds5_empirical_prior/shortlists'/f'{sid}.json';shortlist=json.loads(shortpath.read_text())
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
    finally:store.close()
    assert p.evidence_sha256==prior['evidence_sha256']==shortlist['evidence_sha256']
    assert p.snapshot_digest==prior['snapshot_digest']==shortlist['snapshot_digest']
    assert shortlist['sites']==prior['sites'] and calibration['latest_history_snapshot_ns']<p.start_utc_ns
    total=np.arange(-1230,1231)/10;delta=np.arange(-1200,1201)/10;clock=np.arange(-3,3.1,.5)
    ix=np.rint((clock[:,None]+delta[None,:]-total[0])/.1).astype(int)
    cp=-.5*clock**2;cp-=logsumexp(cp);zero_index=int(np.flatnonzero(clock==0)[0])
    lookup={str(c):i for i,c in enumerate(p.catalogue.satellite_numbers)};epochs=p.catalogue.element_epoch_utc_ns()
    priors={};omitted={};options={s:{100.:{},200.:{}} for s in prior['sites']}
    for track in p.tracks:
        tid=track.track_id;mask=np.asarray(track.training_mask,bool)
        allowed={s:{r['candidate_id'] for r in shortlist['candidates'][s][tid]}|
            {prior['fixed_identities'][s][tid]['candidate_id']} for s in prior['sites']}
        ids=sorted(set().union(*allowed.values()),key=int)
        for cid in ids:
            if cid in priors:continue
            age=(p.start_utc_ns-epochs[lookup[cid]])/3.6e12;key=age_bin(calibration['model'],age)['lower_h']
            if key not in prior_cache:prior_cache[key]=discrete_weights(calibration['model'],age,delta)
            priors[cid],omitted[cid]=prior_cache[key]
        banks,_=build_prediction_banks(p.catalogue,[lookup[c] for c in ids],p.start_utc_ns,[track],taus_s=total)
        for site,loc in prior['sites'].items():
            for sigma in options[site]:options[site][sigma][tid]={}
            for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=total)(0,0):
                for i,craw in enumerate(b.candidate_ids):
                    cid=str(craw)
                    if cid not in allowed[site] or not b.visible[i]:continue
                    residual=b.measured_hz[None,:]-b.predictions_hz[i]
                    tr=block_average(track.times_s,residual,mask);te=block_average(track.times_s,residual,~mask)
                    for sigma in options[site]:
                        f=profiles(tr,te,sigma)
                        options[site][sigma][tid][cid]={'train':f['train'][ix],'predict':f['predict'][ix],'n_test':f['n_test']}
            original=prior['fixed_identities'][site][tid]['candidate_id'];assert original in options[site][100.][tid]
            tr=block_average(track.times_s,track.measured_hz,mask)[None,:]
            te=block_average(track.times_s,track.measured_hz,~mask)[None,:];f=profiles(tr,te,3000.)
            for sigma in options[site]:
                options[site][sigma][tid]['__null__']={'train':np.broadcast_to(f['train'],(len(clock),1)),
                    'predict':np.broadcast_to(f['predict'],(len(clock),1)),'n_test':f['n_test']}
    results={}
    for site,by_sigma in options.items():
        results[site]={}
        for sigma,opts in by_sigma.items():
            no_null={t:{c:r for c,r in rr.items() if c!='__null__'} for t,rr in opts.items()}
            zero={t:{c:dict(r,train=r['train'][zero_index:zero_index+1],predict=r['predict'][zero_index:zero_index+1])
                for c,r in rr.items()} for t,rr in opts.items()}
            zero_no_null={t:{c:r for c,r in rr.items() if c!='__null__'} for t,rr in zero.items()}
            results[site][str(sigma)]={
                'soft_clock_null':exact_soft(opts,priors,cp,null_mass=.1),
                'soft_no_clock_null':exact_soft(zero,priors,np.array([0.]),null_mass=.1),
                'soft_clock_no_null':exact_soft(no_null,priors,cp),
                'soft_no_clock_no_null':exact_soft(zero_no_null,priors,np.array([0.]))}
    return {'session_id':sid,'capture_start_utc':prior['capture_start_utc'],'sample_rate_hz':prior['sample_rate_hz'],
        'track_count':len(p.tracks),'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
        'shortlist_sha256':digest(shortpath),'max_prior_mass_outside_support':max(omitted.values()),
        'results':results,'elapsed_s':time.monotonic()-started}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--shard',type=int,required=True);parser.add_argument('--shards',type=int,default=4)
    args=parser.parse_args();old=json.loads(SOURCE.read_text());cal=json.loads(CALIBRATION.read_text())
    scans=[s for i,s in enumerate(old['scans']) if i%args.shards==args.shard];path=HERE/f'results_shard_{args.shard}.json'
    protocol={'source_sha256':digest(SOURCE),'calibration_sha256':digest(CALIBRATION),'runner_sha256':digest(Path(__file__)),
        'core_sha256':digest(HERE/'core.py'),'requested_shards':args.shards,
        'primary':'soft_clock_null at 100 Hz; exact deterministic marginalization',
        'scope':'fixed independent sites; cached site-specific top3+original; no geographic search or cross-site proposals',
        'model':'independent per-track satellite timing from empirical TLE-age prior; identity marginalized; optional 10% null; optional shared N(0,1s) scan clock truncated +/-3s',
        'score':'sum of per-track conditional predictive log densities per held-out one-second block; full-scan conditional evidence also recorded'}
    if path.exists():out=json.loads(path.read_text());assert out['protocol']==protocol
    else:out={'protocol':protocol,'shard':args.shard,'shards':args.shards,'expected_sessions':[s['session_id'] for s in scans],'scans':[],'failures':[]}
    done={s['session_id'] for s in out['scans']}|{f['session_id'] for f in out['failures']};cache={}
    for s in scans:
        if s['session_id'] in done:continue
        try:r=scan(s,cal,cache);out['scans'].append(r);print('DONE',s['session_id'],round(r['elapsed_s'],1),flush=True)
        except Exception as exc:out['failures'].append({'session_id':s['session_id'],'error':repr(exc),'traceback':traceback.format_exc()});traceback.print_exc()
        atomic(path,out)


if __name__=='__main__':main()
