"""Score sealed method runs and retain per-rate runtime/recovery tables."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics

import numpy as np
from scoring import score


def key(row):
    return (row['context']['session_id'],row['context']['visit_index'])


def cost(rows):
    by_visit=defaultdict(list)
    for row in rows:by_visit[key(row)].append(row)
    return {'unique_visits':len(by_visit),'timed_calls':len(rows),
        'mean_visit_median_cpu_ms':1000*statistics.mean(statistics.median(r['timing']['cpu_s'] for r in v) for v in by_visit.values()),
        'mean_visit_median_wall_ms':1000*statistics.mean(statistics.median(r['timing']['wall_s'] for r in v) for v in by_visit.values()),
        'p95_call_wall_ms':1000*float(np.percentile([r['timing']['wall_s'] for r in rows],95)),
        'max_call_wall_ms':1000*max(r['timing']['wall_s'] for r in rows),
        'total_cpu_s':sum(r['timing']['cpu_s'] for r in rows),
        'total_wall_s':sum(r['timing']['wall_s'] for r in rows)}


def summarize(paths):
    rows=[];runs=[]
    for path in paths:
        run=json.loads((path/'run.json').read_text())
        if not run.get('complete') or not run.get('sources_unchanged') or run.get('failed_calls'):
            raise ValueError(f'incomplete/invalid run: {path}')
        loaded=[json.loads(line) for line in (path/'rows.jsonl').read_text().splitlines()]
        if len(loaded)!=run['planned_calls'] or any(r['status']!='ok' for r in loaded):
            raise ValueError('row completion')
        rows.extend(loaded);runs.append({'directory':str(path),'receipt':run,
            'rows_sha256':hashlib.sha256((path/'rows.jsonl').read_bytes()).hexdigest()})
    groups=defaultdict(list)
    for row in rows:groups[row['method']].append(row)
    reference=groups['original'];reference_zero=[r for r in reference if r['repeat']==0]
    output={'scope':'DS7 bounded development; unique-visit science from repeat 0; both repeats timed',
            'runs':runs,'methods':{}}
    for name,method_rows in groups.items():
        unique=[r for r in method_rows if r['repeat']==0]
        science=score(reference_zero,unique)
        repeated=defaultdict(list)
        for row in method_rows:repeated[key(row)].append(row)
        if any(len(v)!=2 or {r['repeat'] for r in v}!={0,1} for v in repeated.values()):
            raise ValueError('expected two complete chronological repeats')
        repeatability=all(v[0]['result']==v[1]['result'] for v in repeated.values())
        rates={}
        for rate in sorted({r['context']['rate_hz'] for r in reference}):
            chosen=[r for r in method_rows if r['context']['rate_hz']==rate]
            ref=[r for r in reference if r['context']['rate_hz']==rate]
            rates[str(rate)]={'cost':cost(chosen),'science':score(
                [r for r in ref if r['repeat']==0],[r for r in chosen if r['repeat']==0])}
        output['methods'][name]={'cost':cost(method_rows),'science':science,
            'repeatability_exact':repeatability,'by_rate':rates,
            'route_counts_unique':dict(Counter(r['diagnostics'].get('route') for r in unique)),
            'resource_cores':4 if name=='parallel4' else 1}
    base=output['methods']['original']['cost']
    for result in output['methods'].values():
        result['cpu_speedup']=base['mean_visit_median_cpu_ms']/result['cost']['mean_visit_median_cpu_ms']
        result['wall_speedup']=base['mean_visit_median_wall_ms']/result['cost']['mean_visit_median_wall_ms']
        for rate,entry in result['by_rate'].items():
            reference_cost=output['methods']['original']['by_rate'][rate]['cost']
            entry['cpu_speedup']=reference_cost['mean_visit_median_cpu_ms']/entry['cost']['mean_visit_median_cpu_ms']
            entry['wall_speedup']=reference_cost['mean_visit_median_wall_ms']/entry['cost']['mean_visit_median_wall_ms']
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('runs',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=summarize(a.runs)
    with a.output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    for name,m in result['methods'].items():
        print(name,round(m['cost']['mean_visit_median_wall_ms'],2),round(m['cpu_speedup'],3),
              m['science']['recovery'],m['route_counts_unique'])
