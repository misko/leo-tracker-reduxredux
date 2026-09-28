"""Independent aggregation of DS5 fixed-site diagnostic results (standard library)."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

DEVELOPMENT='scan-fw-d86e8f23c0624bac'


def summarize(values):
    if not values:
        return {'n':0}
    return {'n':len(values),'mean':statistics.mean(values),'median':statistics.median(values),
            'min':min(values),'max':max(values)}


def aggregate(results, manifest, inventory):
    expected={r['session_id']:r for r in manifest['captures'] if r['admission_status']=='included'}
    inputs={r['session_id']:r for r in inventory['captures']}
    scans=results['scans'];seen=[r['session_id'] for r in scans]
    if len(seen)!=len(set(seen)):
        raise ValueError('duplicate scan results')
    if not set(seen)<=set(expected):
        raise ValueError('result outside frozen DS5 inventory')
    buckets={};outliers=[];changes={}
    for scan in scans:
        sid=scan['session_id'];capture=expected[sid];base=inputs[sid]
        if scan['evidence_sha256']!=base['evidence_sha256']:
            raise ValueError('input evidence digest mismatch')
        experiments=scan['experiments'];keys=[(e['noise_scale_hz'],e['mode']) for e in experiments]
        if len(keys)!=len(set(keys)):
            raise ValueError('duplicate model/scale in scan')
        by_mode={e['mode']:e for e in experiments if e['noise_scale_hz']==100}
        for baseline in ('zero','free_per_track','flat_satellite'):
            if baseline not in by_mode or 'age_satellite' not in by_mode:
                continue
            for prior in ('sacramento','reno'):
                def gap(mode):
                    sites=by_mode[mode]['sites']
                    return sites['reference']['negative_log_score_per_test_observation']-sites[prior]['negative_log_score_per_test_observation']
                value=gap('age_satellite')-gap(baseline)
                scopes=['all42']
                if sid!=DEVELOPMENT:scopes.append('excluding_development')
                if base['original_location_errors_m'][prior]>=100000:scopes.append('original_error_ge100km')
                for scope in scopes:changes.setdefault((scope,baseline,prior),[]).append(value)
        for e in experiments:
            ref=e['sites']['reference']
            for prior in ('sacramento','reno'):
                selected=e['sites'][prior]
                if selected['test_observations']!=ref['test_observations']:
                    raise ValueError('site evidence denominator mismatch')
                gap=ref['negative_log_score_per_test_observation']-selected['negative_log_score_per_test_observation']
                n=ref['test_observations']
                error=base['original_location_errors_m'][prior]/1000
                error_bin='lt25km' if error<25 else '25to100km' if error<100 else 'ge100km'
                scopes=['all42',f'rate_{capture["sample_rate_hz"]}',f'original_error_{error_bin}']
                if sid!=DEVELOPMENT:scopes.append('excluding_development')
                for scope in scopes:
                    key=(scope,e['noise_scale_hz'],e['mode'],prior)
                    buckets.setdefault(key,[]).append((sid,gap,n,ref,selected,error))
                if e['noise_scale_hz']==100 and e['mode']=='age_satellite':
                    outliers.append({'session_id':sid,'prior':prior,'original_location_error_km':error,
                        'reference_minus_prior_nll':gap,'reference_boundary_mass':ref['max_satellite_boundary_mass'],
                        'prior_boundary_mass':selected['max_satellite_boundary_mass']})
    summary=[]
    for (scope,noise,mode,prior),rows in sorted(buckets.items()):
        gaps=[r[1] for r in rows];n=sum(r[2] for r in rows)
        summary.append({'scope':scope,'noise_scale_hz':noise,'mode':mode,'prior':prior,
            'scan_count':len(rows),'reference_wins':sum(g<-1e-10 for g in gaps),
            'prior_wins':sum(g>1e-10 for g in gaps),'ties':sum(abs(g)<=1e-10 for g in gaps),
            'equal_scan_gap':summarize(gaps),'observation_weighted_gap':sum(r[1]*r[2] for r in rows)/n,
            'reference_mean_nll':statistics.mean(r[3]['negative_log_score_per_test_observation'] for r in rows),
            'prior_mean_nll':statistics.mean(r[4]['negative_log_score_per_test_observation'] for r in rows),
            'reference_mean_rms_hz':statistics.mean(r[3]['uncapped_posterior_expected_weighted_rms_hz'] for r in rows),
            'prior_mean_rms_hz':statistics.mean(r[4]['uncapped_posterior_expected_weighted_rms_hz'] for r in rows),
            'original_location_error_km':summarize([r[5] for r in rows]),
            'reference_boundary_over_1pct':sum(r[3]['max_satellite_boundary_mass']>.01 for r in rows),
            'prior_boundary_over_1pct':sum(r[4]['max_satellite_boundary_mass']>.01 for r in rows)})
    return {'scope':'retrospective fixed-site scores; no new localization errors; negative gap favors reference',
        'expected_scans':len(expected),'completed_scans':len(scans),'missing_sessions':sorted(set(expected)-set(seen)),
        'development_session':DEVELOPMENT,'summaries':summary,
        'model_change_summary':[{'scope':scope,'baseline':baseline,'prior':prior,
            'age_minus_baseline_gap_change':summarize(values),'reference_separation_increased':sum(v<0 for v in values)}
            for (scope,baseline,prior),values in sorted(changes.items())],
        'age_model_largest_reference_losses':sorted(outliers,key=lambda r:r['reference_minus_prior_nll'],reverse=True)[:12]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('results');args=parser.parse_args()
    here=Path(__file__).resolve().parent;source=Path(args.results)
    manifest=Path('/home/mouse9911/gits/leo-adaptive-position-deploy/reports/2026_09_26_ds5_since_local_midnight/manifest.json')
    inventory=json.loads((here/'input_audit.json').read_text())
    assert hashlib.sha256(manifest.read_bytes()).hexdigest()==inventory['manifest_sha256']
    out=aggregate(json.loads(source.read_text()),json.loads(manifest.read_text()),inventory)
    out['results_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    (here/'aggregate_audit.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='summaries'},indent=2))


if __name__=='__main__':main()
