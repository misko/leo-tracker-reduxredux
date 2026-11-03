"""Combine measured native stages, original-hit scoring and host/ARM parity."""
import json
from features import HERE,sha
from summarize import frozen


def main():
    results={};reference_time=None
    for method in ('full','sqrt3','sqrt5','log9','guard5'):
        folder=HERE/f'arm-{method}-v2'
        score=frozen.score(folder,HERE/'arm-original.jsonl')
        (folder/'hit-audit.json').write_text(json.dumps(score,indent=2)+'\n')
        stage=json.loads((folder/'stage-summary.json').read_text())
        if reference_time is None:reference_time=stage['combined_cpu_seconds_per_dwell']
        hosts={}
        for ds in ('ds7','ds8','ds9'):
            for line in (HERE/f'host-{ds}-{method}-v2/rows.jsonl').read_text().splitlines():
                r=json.loads(line);c=r['context'];hosts[(c['session_id'],c['visit_index'])]={(w['receiver_id'],w['probe_index']):w for w in r['rows']}
        maximum={};checked=0;pruned=0
        for line in (folder/'raw.jsonl').read_text().splitlines():
            r=json.loads(line);ctx=r['context'];a=r['native'];b=hosts[(ctx['session_id'],ctx['visit_index'])][(a['receiver_id'],a['probe_index'])]
            assert a['coarse_mask']==b['coarse_mask'];pruned+=a['coarse_mask']!=2047
            assert len(a['candidates'])==len(b['candidates'])==8
            for x,y in zip(a['candidates'],b['candidates'],strict=True):
                assert x['epoch']==y['epoch'] and x['conditioned_fallback']==y['conditioned_fallback']
                for key,tol in [('acquired_cfo_hz',2e-6),('tracking_cfo_hz',2e-6),('exact_score',2e-9),('control_score',2e-9),('margin',2e-9)]:
                    delta=abs(x[key]-y[key]);maximum[key]=max(delta,maximum.get(key,0));assert delta<=tol,(method,key,delta)
                checked+=1
        results[method]=dict(stage=stage,counts=score['totals'],speedup=reference_time/stage['combined_cpu_seconds_per_dwell'],
            pruned_windows=pruned,host_arm_checked_candidates=checked,host_arm_maximum_deltas=maximum,
            native_sha256=sha(folder/'raw.jsonl'),stage_summary_sha256=sha(folder/'stage-summary.json'))
    (HERE/'arm-summary.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({m:dict(seconds=r['stage']['combined_cpu_seconds_per_dwell'],speedup=r['speedup'],hits=r['counts']['recovered_positive_hits'],original=r['counts']['reference_positive_hits'],pruned_windows=r['pruned_windows']) for m,r in results.items()},indent=2))


if __name__=='__main__':main()
