"""Accounting and fixed-site summaries for penalized deterministic assignments."""
import json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent


def summarize(scans,inventory):
    inputs={r['session_id']:r for r in inventory['captures']};seen=set();buckets={};changes={}
    for scan in scans:
        sid=scan['session_id']
        if sid in seen:raise ValueError('duplicate scan')
        seen.add(sid);inp=inputs[sid]
        if scan['evidence_sha256']!=inp['evidence_sha256'] or scan['track_count']!=inp['track_count']:raise ValueError('input mismatch')
        for exp in scan['experiments']:
            penalty=exp['change_penalty_nats'];sites=exp['sites']
            denominators={s:sites[s]['test_observations'] for s in sites}
            if len(set(denominators.values()))!=1:raise ValueError('different evaluation denominator')
            scopes=['all42',f'rate_{inp["sample_rate_hz"]}']
            if sid not in {'scan-fw-d86e8f23c0624bac','scan-fw-dc1153010e57ac76'}:scopes.append('excluding_two_development')
            for site in ('sacramento','reno'):
                site_scopes=list(scopes)
                if inp['original_location_errors_m'][site]>=100000:site_scopes.append(f'{site}_error_ge100km')
                gap=sites['reference']['negative_log_score_per_test_observation']-sites[site]['negative_log_score_per_test_observation']
                for scope in set(site_scopes):buckets.setdefault((scope,penalty,site),[]).append(gap)
            for site in sites:changes.setdefault((penalty,site),[]).append(sites[site]['identity_changes_from_original'])
    rows=[]
    for (scope,penalty,site),gaps in sorted(buckets.items()):
        rows.append({'scope':scope,'change_penalty_nats':penalty,'site':site,'scans':len(gaps),
            'reference_wins':sum(g<-1e-10 for g in gaps),'mean_gap':statistics.mean(gaps),'median_gap':statistics.median(gaps)})
    change_rows=[{'change_penalty_nats':p,'site':s,'mean_changes':statistics.mean(v),'median_changes':statistics.median(v),
        'total_changes':sum(v)} for (p,s),v in sorted(changes.items())]
    return {'completed':len(seen),'missing':sorted(set(inputs)-seen),'summaries':rows,'identity_changes':change_rows}


def main():
    payloads=[json.loads(p.read_text()) for p in sorted(HERE.glob('results_v2_shard_*.json'))]
    assert len(payloads)==4 and all(p['protocol']==payloads[0]['protocol'] for p in payloads)
    assert not any(p['failures'] for p in payloads)
    scans=sorted([s for p in payloads for s in p['scans']],key=lambda s:s['capture_start_utc'])
    inventory=json.loads((HERE.parent/'2026_09_26_ds5_probabilistic/input_audit.json').read_text())
    out=summarize(scans,inventory);assert out['completed']==42 and not out['missing']
    out['protocol']=payloads[0]['protocol'];(HERE/'aggregate.json').write_text(json.dumps(out,indent=2)+'\n')
    (HERE/'results.json').write_text(json.dumps({'protocol':payloads[0]['protocol'],'scans':scans},indent=2)+'\n')
    for r in out['summaries']:
        if r['scope']=='all42':print(r)


if __name__=='__main__':main()
