"""Bounded three-scan joint-model feasibility experiment, not production."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from core import block_average,profiles,sample,assess
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_26_ds5_empirical_prior'))
from empirical_prior import discrete_weights,age_bin
sys.path.insert(0,str(HERE.parent/'2026_09_26_reno_track_audit'))
from compare_scan_clock import (ScannerTrackingInputStore,TleArchiveReader,prepare_adaptive_tle_position_inputs,
    build_prediction_banks,RegionalTrackPredictionEvaluator,point_factory)

TARGETS={'scan-fw-3228d496423f0b3d','scan-fw-fadea8b51ac3a4f7','scan-fw-4b863c775f5972ce'}


def main(targets=None,output_path=None):
    targets=TARGETS if targets is None else set(targets)
    output_path=HERE/'results.json' if output_path is None else Path(output_path)
    source=HERE.parent/'2026_09_26_ds5_probabilistic/results.json'
    calpath=HERE.parent/'2026_09_26_ds5_empirical_prior/calibration.json'
    cal=json.loads(calpath.read_text());old=json.loads(source.read_text())
    total=np.arange(-1230,1231)/10;delta=np.arange(-1200,1201)/10;clock=np.arange(-3,3.1,.5)
    ix=np.rint((clock[:,None]+delta[None,:]-total[0])/.1).astype(int)
    cp=-.5*clock**2;cp-=logsumexp(cp);cache={};output=[]
    for prior in old['scans']:
        sid=prior['session_id']
        if sid not in targets:continue
        shortpath=HERE.parent/'2026_09_26_ds5_empirical_prior/shortlists'/f'{sid}.json'
        shortlist=json.loads(shortpath.read_text())
        store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
        try:p=prepare_adaptive_tle_position_inputs(sid,inputs=store,archive=TleArchiveReader(Path('/var/lib/leo/tle')))
        finally:store.close()
        assert p.evidence_sha256==prior['evidence_sha256']==shortlist['evidence_sha256']
        assert p.snapshot_digest==prior['snapshot_digest']==shortlist['snapshot_digest']
        assert shortlist['sites']==prior['sites'] and cal['latest_history_snapshot_ns']<p.start_utc_ns
        lookup={str(c):i for i,c in enumerate(p.catalogue.satellite_numbers)};epochs=p.catalogue.element_epoch_utc_ns()
        priors={};omitted={};options={s:{100.:{},200.:{}} for s in prior['sites']};original={s:{} for s in prior['sites']}
        mixed=0
        for track in p.tracks:
            mask=np.asarray(track.training_mask,bool)
            mixed+=len(set(np.floor(track.times_s[mask]))&set(np.floor(track.times_s[~mask])))
            allowed={s:{r['candidate_id'] for r in shortlist['candidates'][s][track.track_id]}|
                {prior['fixed_identities'][s][track.track_id]['candidate_id']} for s in prior['sites']}
            ids=sorted(set().union(*allowed.values()))
            banks,_=build_prediction_banks(p.catalogue,[lookup[c] for c in ids],p.start_utc_ns,[track],taus_s=total)
            for cid in ids:
                if cid in priors:continue
                age=(p.start_utc_ns-epochs[lookup[cid]])/3.6e12;key=age_bin(cal['model'],age)['lower_h']
                if key not in cache:cache[key]=discrete_weights(cal['model'],age,delta)
                priors[cid],omitted[cid]=cache[key]
            for site,loc in prior['sites'].items():
                tid=track.track_id;original[site][tid]=prior['fixed_identities'][site][tid]['candidate_id']
                for sigma in options[site]:options[site][sigma][tid]={}
                for b in RegionalTrackPredictionEvaluator(banks,point_factory(loc['latitude_deg'],loc['longitude_deg']),taus_s=total)(0,0):
                    for i,c in enumerate(b.candidate_ids):
                        cid=str(c)
                        if cid not in allowed[site] or not b.visible[i]:continue
                        residual=b.measured_hz[None,:]-b.predictions_hz[i]
                        tr=block_average(track.times_s,residual,mask);te=block_average(track.times_s,residual,~mask)
                        for sigma in options[site]:
                            f=profiles(tr,te,sigma)
                            options[site][sigma][tid][cid]={'train':f['train'][ix],'predict':f['predict'][ix],'n_test':f['n_test']}
                # Broad, normalized constant-only frequency model; no satellite Doppler.
                tr=block_average(track.times_s,track.measured_hz,mask)[None,:]
                te=block_average(track.times_s,track.measured_hz,~mask)[None,:]
                f=profiles(tr,te,3000.)
                for sigma in options[site]:
                    options[site][sigma][tid]['__null__']={'train':np.broadcast_to(f['train'],(len(clock),1)),
                        'predict':np.broadcast_to(f['predict'],(len(clock),1)),'n_test':f['n_test']}
        print(sid,'profiles complete',flush=True)
        results={}
        for site,by_sigma in options.items():
            results[site]={}
            for sigma,opts in by_sigma.items():
                chains=[]
                for chain in range(2):
                    initial=original[site] if chain==0 else {t:'__null__' for t in opts}
                    states=sample(opts,priors,cp,initial,seed=20260926+chain,burn=80,draws=160)
                    result=assess(opts,priors,states);chains.append((states,result))
                states=chains[0][0]+chains[1][0];joint=assess(opts,priors,states)
                frozen=assess(opts,priors,[(original[site],6)])
                # Same joint posterior conditional on no scan clock, independently sampled.
                zero_opts={t:{c:{'train':v['train'][6:7],'predict':v['predict'][6:7],'n_test':v['n_test']} for c,v in rr.items()} for t,rr in opts.items()}
                zs=sample(zero_opts,priors,np.array([0.]),original[site],seed=20260926,burn=80,draws=160)
                zero=assess(zero_opts,priors,zs)
                differences=[]
                for a,b in zip(chains[0][1]['tracks'],chains[1][1]['tracks']):
                    assert a['track_id']==b['track_id']
                    differences.append(.5*sum(abs(a['probabilities'].get(c,0)-b['probabilities'].get(c,0)) for c in set(a['probabilities'])|set(b['probabilities'])))
                results[site][str(sigma)]={'joint':joint,'frozen_no_clock':frozen,'joint_no_clock':zero,
                    'chain_nll':[r['composite_nll_per_test_block'] for _,r in chains],
                    'max_chain_assignment_total_variation':max(differences),
                    'mean_chain_assignment_total_variation':float(np.mean(differences)),
                    'clock_mean_s':float(np.mean([clock[c] for _,c in states])),
                    'clock_edge_fraction':float(np.mean([c in (0,len(clock)-1) for _,c in states]))}
                print(sid,site,sigma,'joint',round(joint['composite_nll_per_test_block'],3),
                    'null',round(joint['mean_null_probability'],3),'chainTV',round(max(differences),3),flush=True)
        output.append({'session_id':sid,'capture_start_utc':prior['capture_start_utc'],'track_count':len(p.tracks),
            'evidence_sha256':p.evidence_sha256,'snapshot_digest':p.snapshot_digest,
            'shortlist_sha256':hashlib.sha256(shortpath.read_bytes()).hexdigest(),
            'train_eval_shared_second_bins_count':mixed,'max_prior_mass_outside_support':max(omitted.values()),'results':results})
        artifact={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'calibration_sha256':hashlib.sha256(calpath.read_bytes()).hexdigest(),
            'core_sha256':hashlib.sha256((HERE/'core.py').read_bytes()).hexdigest(),
            'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'requested_sessions':sorted(targets),
            'protocol':'Fixed scans/sites, independent shortlist top3+original from prior training-only coarse search. '
                'One-second averages within each original partition; cross-partition/receiver dependence remains. '
                'Gaussian block noise100/200Hz, track constant integrated N(0,1MHz). '
                'Identity prior10% broad null (Gaussian3000Hz constant-only), remaining uniform among retained IDs. '
                'Satellite delta marginalized against signed historical prior conditioned on +/-120s, step0.1. '
                'Scan clock N(0,1s) truncated +/-3s step0.5, uncalibrated sensitivity not metadata-derived. '
                'Collapsed Gibbs2chains80burn160draws, original/null starts; zero-clock control1chain. '
                'Score sums per-track joint predictive log densities / test blocks; composite, not full joint test evidence. '
                'No production mutations, no geographic search, no calibrated association/location probabilities.', 'scans':output}
        temporary=output_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(artifact,indent=2)+'\n')
        temporary.replace(output_path)
    assert {s['session_id'] for s in output}==targets


if __name__=='__main__':main()
