"""Receipt-only summary; distinguish receiver retention from visit retention."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def summarize(rows):
    output={}
    for rate in (2500000,5000000):
        selected=[r for r in rows if r['rate_hz']==rate]
        if not selected:continue
        assessments=[a for r in selected for a in r['assessments']]
        summary={k:sum(a[k] for a in assessments) for k in (
            'reference_active','matched_reference','lost_reference','additional_or_mismatched')}
        cpu={m:sum(r['timings'][m]['process_cpu_ms'] for r in selected) for m in ('application','candidate')}
        summary.update(visits=len(selected),cpu_mean_ms={m:t/len(selected) for m,t in cpu.items()},
            cpu_speedup=cpu['application']/cpu['candidate'],
            candidate_wall_max_ms=max(r['timings']['candidate']['wall_ms'] for r in selected),
            lost_reference_visits=sum(any(a['reference_active'] for a in r['assessments']) and
                not any(a['matched_reference'] for a in r['assessments']) for r in selected))
        misses=[]
        for row in selected:
            for rx,a in enumerate(row['assessments']):
                if not a['lost_reference']:continue
                pairs=[p for p in row['application_pair_inventory'] if p['receiver']==rx]
                misses.append({'case_id':row['case_id'],'receiver':rx,
                    'candidate_active':a['candidate_active'],
                    'route':row['decisions'][rx]['route'],
                    'reference_probes':sorted({p[k]['probe_index'] for p in pairs for k in ('first','second')})})
        summary['misses']=misses
        output[str(rate)]=summary
    return output


if __name__=='__main__':
    document=json.loads((HERE/'results.hash_adapter.json').read_text())
    assert document['complete'] and document['source_stable']
    summary=summarize(document['rows'])
    with (HERE/'summary.json').open('x') as f:json.dump(summary,f,indent=2)
    print(json.dumps(summary,indent=2))
