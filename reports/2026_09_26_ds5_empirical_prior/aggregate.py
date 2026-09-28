"""Independent DS5 accounting and paired fixed-site model comparisons."""
import argparse,hashlib,json,statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
DEVELOPMENT={'scan-fw-dc1153010e57ac76','scan-fw-d86e8f23c0624bac'}


def summarize(scans,inventory):
    inputs={r['session_id']:r for r in inventory['captures']};seen=set();buckets={};paired={};cases=[]
    for scan in scans:
        sid=scan['session_id']
        if sid in seen:raise ValueError('duplicate session')
        seen.add(sid);inp=inputs[sid]
        if scan['evidence_sha256']!=inp['evidence_sha256']:raise ValueError('evidence mismatch')
        by_mode={e['mode']:e for e in scan['experiments']}
        if len(by_mode)!=len(scan['experiments']):raise ValueError('duplicate model')
        for prior in ('sacramento','reno'):
            error=inp['original_location_errors_m'][prior]/1000
            scopes=['all42',f'rate_{inp["sample_rate_hz"]}']
            if sid not in DEVELOPMENT:scopes.append('excluding_two_development')
            if error>=100:scopes.append('original_error_ge100km')
            if error<25:scopes.append('original_error_lt25km')
            gaps={}
            for mode,e in by_mode.items():
                ref=e['sites']['reference'];est=e['sites'][prior]
                if ref['test_observations']!=est['test_observations']:raise ValueError('different observation denominator')
                gap=ref['negative_log_score_per_test_observation']-est['negative_log_score_per_test_observation'];gaps[mode]=gap
                for scope in scopes:buckets.setdefault((scope,mode,prior),[]).append((gap,ref,est))
            for a,b in [('empirical_frozen','old_frozen'),('empirical_joint','old_joint'),('old_joint','old_frozen'),
                        ('empirical_joint','empirical_frozen'),('empirical_joint_scan_clock','empirical_joint'),('old_frozen','old_frozen_60')]:
                if a in gaps and b in gaps:
                    for scope in scopes:paired.setdefault((scope,a,b,prior),[]).append(gaps[a]-gaps[b])
            if error>=100:cases.append({'session_id':sid,'capture_start_utc':scan['capture_start_utc'],'prior':prior,'original_error_km':error,'score_gaps':gaps})
    stats=[]
    for (scope,mode,prior),rows in sorted(buckets.items()):
        gaps=[r[0] for r in rows];n=sum(r[1]['test_observations'] for r in rows)
        stats.append({'scope':scope,'mode':mode,'prior':prior,'scans':len(rows),'reference_wins':sum(g<-1e-10 for g in gaps),
            'prior_wins':sum(g>1e-10 for g in gaps),'mean_gap':statistics.mean(gaps),'median_gap':statistics.median(gaps),
            'observation_weighted_gap':sum(r[0]*r[1]['test_observations'] for r in rows)/n,
            'reference_mean_nll':statistics.mean(r[1]['negative_log_score_per_test_observation'] for r in rows),
            'prior_mean_nll':statistics.mean(r[2]['negative_log_score_per_test_observation'] for r in rows),
            'reference_mean_rms_hz':statistics.mean(r[1]['uncapped_posterior_expected_weighted_rms_hz'] for r in rows),
            'prior_mean_rms_hz':statistics.mean(r[2]['uncapped_posterior_expected_weighted_rms_hz'] for r in rows),
            'reference_boundary_over_1pct':sum(r[1]['max_satellite_boundary_mass']>.01 for r in rows),
            'prior_boundary_over_1pct':sum(r[2]['max_satellite_boundary_mass']>.01 for r in rows)})
    comparisons=[{'scope':scope,'model':a,'baseline':b,'prior':prior,'scans':len(v),'mean_gap_change':statistics.mean(v),
                  'median_gap_change':statistics.median(v),'reference_separation_increased':sum(x<0 for x in v)}
                 for (scope,a,b,prior),v in sorted(paired.items())]
    return {'expected_scans':len(inputs),'completed_scans':len(seen),'missing_sessions':sorted(set(inputs)-seen),
            'summaries':stats,'paired_comparisons':comparisons,'large_error_cases':cases}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--allow-partial',action='store_true');args=parser.parse_args()
    files=sorted(HERE.glob('results_shard_*.json'));payloads=[json.loads(p.read_text()) for p in files]
    assert payloads and all(p['protocol']==payloads[0]['protocol'] for p in payloads)
    inventory=json.loads((HERE.parent/'2026_09_26_ds5_probabilistic/input_audit.json').read_text())
    scans=[s for p in payloads for s in p['scans']];scans.sort(key=lambda s:(s['capture_start_utc'],s['session_id']))
    failures=[f for p in payloads for f in p['failures']];out=summarize(scans,inventory)
    if not args.allow_partial:assert not failures and not out['missing_sessions']
    out.update({'failures':failures,'scope':'retrospective fixed-site comparisons; negative gaps favor reference; not geographic fixes',
                'shard_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})
    (HERE/'aggregate.json').write_text(json.dumps(out,indent=2)+'\n')
    (HERE/'results.json').write_text(json.dumps({'protocol':payloads[0]['protocol'],'scans':scans,'failures':failures},indent=2)+'\n')
    print(json.dumps({'completed':out['completed_scans'],'missing':out['missing_sessions'],'failures':failures},indent=2))
    for r in out['summaries']:
        if r['scope']=='excluding_two_development':print(r['mode'],r['prior'],r['reference_wins'],r['scans'],round(r['mean_gap'],5))


if __name__=='__main__':main()
