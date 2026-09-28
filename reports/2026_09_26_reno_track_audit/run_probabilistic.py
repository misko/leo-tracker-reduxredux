"""Bounded offline orchestration: archive calibration and frozen-site experiment."""
import hashlib
import json
import argparse
from pathlib import Path
import numpy as np
from scipy.stats import t as student_t
from compare_scan_clock import (TleArchiveReader,ScannerTrackingInputStore,
    prepare_adaptive_tle_position_inputs,AdaptiveTlePositionStoreV2,
    build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory)
from leo.sky.propagation import parse_element_sets,propagate_grid
from leo.sky.sampling import SamplingGrid
from probabilistic_core import calibrate_scales,scale_at,fit_profiles,evaluate

HERE=Path(__file__).resolve().parent
HOUR=3_600_000_000_000


def history(archive,start):
    cache={};pairs={};snapshots={}
    def get(when):
        ref=archive.select_latest_before(int(when),provider='space-track')
        if ref.digest not in cache:
            cache[ref.digest]=parse_element_sets(archive.read(ref))
            snapshots[ref.digest]={'collected_utc_ns':ref.collected_utc_ns,'digest':ref.digest}
        return ref,cache[ref.digest]
    # All snapshots end at least 48 hours before target scan. No target RF used.
    for days in range(2,27,2):
        newer,new=get(start-days*24*HOUR)
        ids=[i for i,n in enumerate(new.names) if n.startswith('STARLINK') and
             int(hashlib.sha256(str(new.satellite_numbers[i]).encode()).hexdigest()[:8],16)%37==0][:256]
        now=newer.collected_utc_ns
        grid=SamplingGrid((now-1_000_000_000,now,now+1_000_000_000),1,1.)
        pn=propagate_grid(new,grid,indices=ids);ne=new.element_epoch_utc_ns()
        for lag in (6,24,48,72):
            older,old=get(now-lag*HOUR); lookup={s:i for i,s in enumerate(old.satellite_numbers)}
            matched=[(j,i,lookup[new.satellite_numbers[i]]) for j,i in enumerate(ids) if new.satellite_numbers[i] in lookup]
            po=propagate_grid(old,grid,indices=[k for _,_,k in matched]);oe=old.element_epoch_utc_ns()
            for l,(j,i,k) in enumerate(matched):
                age=(now-oe[k])/HOUR;fresh=(now-ne[i])/HOUR;sat=new.satellite_numbers[i]
                if not (0<=fresh<=24 and 0<age<=120 and oe[k]<ne[i] and pn.usable[j] and po.usable[l]):continue
                key=(sat,oe[k],ne[i])
                if key in pairs:continue
                v=po.velocity_teme_km_s[l,1];dx=pn.position_teme_km[j,1]-po.position_teme_km[l,1]
                tau=float(dx@v/(v@v))
                orth=float(np.linalg.norm(dx-tau*v))
                pairs[key]={'satellite_id':sat,'age_hours':age,'comparison_element_age_hours':fresh,
                    'equivalent_tau_s':tau,'orthogonal_position_difference_km':orth,
                    'old_epoch_ns':oe[k],'new_epoch_ns':ne[i],
                    'old_snapshot':older.digest,'new_snapshot':newer.digest,
                    'validation_group':int(hashlib.sha256(('split:'+str(sat)).encode()).hexdigest()[:8],16)%5==0}
        print(f'archive anchor {days} days earlier: {len(pairs)} distinct pairs',flush=True)
    rows=list(pairs.values());train=[r for r in rows if not r['validation_group']];test=[r for r in rows if r['validation_group']]
    bins=calibrate_scales(train)
    coverage=[]
    for b in bins:
        rr=[r for r in test if r['age_hours']>=b['lower_h'] and (b['upper_h'] is None or r['age_hours']<b['upper_h'])]
        bound=float(student_t.ppf(.95,4)*b['scale_s'])
        coverage.append({'lower_h':b['lower_h'],'upper_h':b['upper_h'],'n':len(rr),'central_90_bound_s':bound,
            'observed_coverage':sum(abs(r['equivalent_tau_s'])<=bound for r in rr)/len(rr) if rr else None})
    return {'protocol':'orbit-space first-order equivalent timing from old to newer TLE; newer is not truth; zero-centered t4; no receiver geometry; deterministic satellite-group split',
        'cutoff_utc_ns':start-48*HOUR,'snapshots':list(snapshots.values()),'training_pairs':len(train),
        'validation_pairs':len(test),'training_satellites':len({r['satellite_id'] for r in train}),
        'validation_satellites':len({r['satellite_id'] for r in test}),
        'bins':bins,'validation_coverage':coverage,'pairs':rows}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--step',type=float,default=.1)
    parser.add_argument('--bound',type=float,default=30.);parser.add_argument('--checks-only',action='store_true')
    parser.add_argument('--suffix',default='');args=parser.parse_args()
    old=json.loads((HERE/'zero_clock_results.json').read_text());sid=old['session_id']
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try:p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=archive)
    finally:store.close()
    assert p.evidence_sha256==old['evidence_sha256'] and p.snapshot_digest==old['snapshot_digest']
    doc=AdaptiveTlePositionStoreV2(Path('/srv/bulk/leo')).status(sid).manifest.document.model_dump(mode='json')
    history_path=HERE/'probabilistic_history.json'
    if history_path.exists():
        h=json.loads(history_path.read_text());assert h['cutoff_utc_ns']==p.start_utc_ns-48*HOUR
    else:
        h=history(archive,p.start_utc_ns);history_path.write_text(json.dumps(h,indent=2)+'\n')
    sites={'reference':doc['diagnostics']['reference_evaluation_only'],
        'reno':next(x['selected'] for x in doc['priors'] if x['name']=='reno')}
    selected={s:{r['track_id']:r['candidate_id'] for r in old['sites'][s]['scans'][0]['tracks']} for s in sites}
    total=np.round(np.arange(round(-(args.bound+3)/args.step),round((args.bound+3)/args.step)+1)*args.step,6)
    delta=np.round(np.arange(round(-args.bound/args.step),round(args.bound/args.step)+1)*args.step,6)
    raw={s:[] for s in sites};epochs=p.catalogue.element_epoch_utc_ns()
    lookup={str(n):i for i,n in enumerate(p.catalogue.satellite_numbers)}
    ages={}
    for num,track in enumerate(p.tracks):
        for site,location in sites.items():
            cid=selected[site][track.track_id];idx=lookup[cid]
            ages[cid]=(p.start_utc_ns-epochs[idx])/HOUR
            banks,_=build_prediction_banks(p.catalogue,[idx],p.start_utc_ns,[track],taus_s=total)
            b=next(iter(RegionalTrackPredictionEvaluator(banks,point_factory(location['latitude_deg'],location['longitude_deg']),taus_s=total)(0,0)))
            assert len(b.candidate_ids)==1 and b.visible[0]
            raw[site].append({'track_id':track.track_id,'satellite_id':cid,'measured':b.measured_hz,
                'prediction':b.predictions_hz[0],'mask':b.training_mask,
                'weight_s':len(np.unique(np.floor(track.times_s)))})
        if num%10==0:print(f'prediction tracks {num+1}/{len(p.tracks)}',flush=True)
    experiments=[]
    # Residual scales are prespecified sensitivities, not calibrated or selected using the target.
    for noise in ((100.,) if args.checks_only else (50.,100.,200.)):
        profiles={s:[dict(track_id=r['track_id'],satellite_id=r['satellite_id'],weight_s=r['weight_s'],
                    **fit_profiles(r['measured'],r['prediction'],r['mask'],noise)) for r in rr] for s,rr in raw.items()}
        arms=[('zero',1),('free_per_track',1),('flat_satellite',1),('age_per_track',1),
              ('age_satellite',1),('age_satellite_scan',1),('age_satellite',.5),('age_satellite',2),
              ('age_satellite_young_sensitivity',1)]
        if args.checks_only:arms=[('age_satellite',1),('age_satellite_scan',1),('age_satellite_young_sensitivity',1)]
        for mode,mult in arms:
            scales={cid:scale_at(age,h['bins'])*mult for cid,age in ages.items()}
            if mode=='age_satellite_young_sensitivity':
                scales={cid:(.25 if ages[cid]<12 else value) for cid,value in scales.items()}
            clock=np.round(np.arange(-30,31)/10,1) if mode=='age_satellite_scan' else np.array([0.])
            dg=np.array([0.]) if mode=='zero' else delta
            fit={s:evaluate(rr,total,dg,clock,1. if mode=='age_satellite_scan' else None,scales,
                per_track=mode in ('free_per_track','age_per_track'),flat=mode in ('zero','free_per_track','flat_satellite')) for s,rr in profiles.items()}
            experiments.append({'noise_scale_hz':noise,'mode':mode,'prior_scale_multiplier':mult,'sites':fit,
                'reference_minus_reno_nll_per_observation':fit['reference']['negative_log_score_per_test_observation']-fit['reno']['negative_log_score_per_test_observation']})
            print(noise,mode,mult,'reference-minus-Reno nll',experiments[-1]['reference_minus_reno_nll_per_observation'],flush=True)
    result={'session_id':sid,'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
        'protocol':{'scope':'fixed locations and zero-offset training-selected IDs; no geographic search, no cross-prior sharing; conditional on identities',
            'training':'original training mask; training-only robust CFO profile, not CFO integration',
            'scoring':'normalized t4 residual density, timing marginalized; conditional independent observations approximation; original reused test mask',
            'age_prior':'historical orbit-space equivalent epoch proxy, not a calibrated Doppler-time prior',
            'grid_s':[-args.bound-3,args.bound+3,args.step],'satellite_support_s':[-args.bound,args.bound],
            'young_sensitivity':'age<12h t4 scale 0.25s is an explicit UNCALIBRATED hypothesis; main arm retains pooled historical fallback',
            'optional_clock':'normal sigma=1 s truncated at +/-3 s, sensitivity assumption not clock calibration',
            'noise_scale_hz':[50,100,200],'no_drift':True,
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'core_sha256':hashlib.sha256((HERE/'probabilistic_core.py').read_bytes()).hexdigest()},
        'age_prior_bins':h['bins'],'age_hours':ages,
        'prior_mass_outside_support':{cid:float(2*student_t.sf(args.bound/scale_at(age,h['bins']),4)) for cid,age in ages.items()},
        'experiments':experiments}
    (HERE/f'probabilistic_results{args.suffix}.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
