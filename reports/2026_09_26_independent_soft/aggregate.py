"""Verified accounting and summaries for exact soft assignment."""
import json,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
DEVELOPMENT={'scan-fw-d86e8f23c0624bac','scan-fw-dc1153010e57ac76'}


def summarize(scans,inventory):
    inputs={r['session_id']:r for r in inventory['captures']};seen=set();buckets={};best={};diagnostics={}
    for scan in scans:
        sid=scan['session_id']
        if sid in seen:raise ValueError('duplicate scan')
        seen.add(sid);inp=inputs[sid]
        if scan['evidence_sha256']!=inp['evidence_sha256'] or scan['track_count']!=inp['track_count']:raise ValueError('input mismatch')
        for noise,by_site in ((n,{s:scan['results'][s][str(n)] for s in scan['results']}) for n in (100.0,200.0)):
            for model in next(iter(by_site.values())):
                fits={s:by_site[s][model] for s in by_site}
                denominators={s:sum(t['test_blocks'] for t in f['tracks']) for s,f in fits.items()}
                tracksets={s:{t['track_id'] for t in f['tracks']} for s,f in fits.items()}
                if len(set(denominators.values()))!=1 or len({frozenset(v) for v in tracksets.values()})!=1:raise ValueError('evaluation mismatch')
                winner=min(fits,key=lambda s:fits[s]['composite_nll_per_test_block'])
                common=['all42',f'rate_{inp["sample_rate_hz"]}']
                if sid not in DEVELOPMENT:common.append('excluding_two_development')
                for site in ('sacramento','reno'):
                    scopes=list(common)
                    if inp['original_location_errors_m'][site]>=100000:scopes.append(f'{site}_error_ge100km')
                    gap=fits['reference']['composite_nll_per_test_block']-fits[site]['composite_nll_per_test_block']
                    for scope in scopes:buckets.setdefault((scope,noise,model,site),[]).append(gap)
                best.setdefault((noise,model),[]).append(winner)
                for site,fit in fits.items():
                    diagnostics.setdefault((noise,model,site),[]).append((fit['mean_null_probability'],
                        fit['ambiguous_tracks_maxprob_below_0_8']/scan['track_count']))
    rows=[]
    for (scope,noise,model,site),gaps in sorted(buckets.items()):
        rows.append({'scope':scope,'noise_hz':noise,'model':model,'site':site,'scans':len(gaps),
            'reference_wins':sum(g<-1e-10 for g in gaps),'mean_gap':statistics.mean(gaps),'median_gap':statistics.median(gaps)})
    best_rows=[]
    for (noise,model),winners in sorted(best.items()):
        best_rows.append({'noise_hz':noise,'model':model,'scans':len(winners),
            'winner_counts':{s:winners.count(s) for s in ('reference','sacramento','reno')}})
    diag_rows=[]
    for (noise,model,site),values in sorted(diagnostics.items()):
        diag_rows.append({'noise_hz':noise,'model':model,'site':site,
            'mean_null_probability':statistics.mean(v[0] for v in values),
            'mean_ambiguous_track_fraction':statistics.mean(v[1] for v in values)})
    return {'completed':len(seen),'missing':sorted(set(inputs)-seen),'summaries':rows,
        'best_location_counts':best_rows,'diagnostics':diag_rows}


def main():
    payloads=[json.loads(p.read_text()) for p in sorted(HERE.glob('results_shard_*.json'))]
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

