"""Freeze a donor16 tolerance before donor17 temporal-gap evaluation."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from model import fit, wrap

HERE=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def export(index):
    path=HERE.parent/f'frame_evolution/input-{index:02d}.json'
    doc=json.loads(path.read_text())
    for p,h in doc['sources'].items():assert digest(p)==h,p
    groups=defaultdict(dict);owners=defaultdict(set)
    for row in doc['rows']:
        key=(row['norad'],row['rf_hz'])
        for point in row['points']:
            cid=point['candidate_id'];owners[cid].add(key)
            if cid in groups[key]:assert groups[key][cid]==point
            groups[key][cid]=point
    rows=[]
    for (norad,rf),points in sorted(groups.items()):
        unique=[p for cid,p in sorted(points.items()) if len(owners[cid])==1]
        result=fit([p['frame_time_s'] for p in unique], [p['phase_us'] for p in unique],
                   [p['training'] for p in unique],doc['frame_period_us'])
        rows.append(dict(norad=norad,rf_hz=rf,unique_points=len(unique),**result))
    return dict(index=index,rows=rows,period_us=doc['frame_period_us'],
                ambiguous_candidates=sum(len(v)>1 for v in owners.values()),
                sources={str(path):digest(path)})


def main():
    start=time.monotonic()
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'model.py',HERE/'PROTOCOL.md')}
    calibration=export(16)
    qualified=[r for r in calibration['rows'] if r['qualified']]
    assert qualified,'No qualified calibration clocks'
    threshold=float(np.median([np.quantile(np.abs(r['held_errors_us']),.95) for r in qualified]))
    calibration.update(threshold_us=threshold,sources={**calibration['sources'],**sources})
    cp=HERE/'calibration.json'
    with cp.open('x') as f:json.dump(calibration,f,indent=2,allow_nan=False)
    validation=export(17)
    summaries=[]
    for d in (calibration,validation):
        accepted=[r for r in d['rows'] if r['qualified']]
        eligible=sum(r['eligible'] for r in d['rows'])
        for row in accepted:
            e=np.array(row['held_errors_us'])
            row['hit_fraction']=float(np.mean(abs(e)<=threshold))
            row['shift_hit_fractions']=[float(np.mean(abs(wrap(e-d['period_us']*k/7,d['period_us']))<=threshold)) for k in (1,2,3)]
        summaries.append(dict(index=d['index'],groups=len(d['rows']),eligible=eligible,qualified=len(accepted),
                              median_hit_fraction=float(np.median([r['hit_fraction'] for r in accepted])) if accepted else None,
                              median_shift_hit_fractions=np.median([r['shift_hit_fractions'] for r in accepted],axis=0).tolist() if accepted else None,
                              gap_quantiles_s=np.quantile([g for r in accepted for g in r['gap_s']],[0,.5,1]).tolist() if accepted else None))
    a,b=summaries
    passed=bool(all(s['qualified']>=10 and s['qualified']>=.9*s['eligible'] for s in summaries)
                and threshold<calibration['period_us']*.01 and b['median_hit_fraction']>=.8
                and max(b['median_shift_hit_fractions'])<=.05)
    sources.update({str(cp):digest(cp),**validation['sources']})
    out=dict(threshold_us=threshold,summaries=summaries,validation=validation,passed=passed,
             sources=sources,causal_position_improvement_established=False,elapsed_s=time.monotonic()-start)
    with (HERE/'summary.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if k not in ('validation','sources')},indent=2))


if __name__=='__main__':main()
