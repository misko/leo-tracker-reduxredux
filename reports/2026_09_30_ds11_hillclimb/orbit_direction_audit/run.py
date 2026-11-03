"""Training-only shape and scale audit of previously exported causal revisions."""
import collections
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
REPORTS=ROOT/'reports'


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shape(times,direction,residual):
    t=np.asarray(times);d=np.asarray(direction);r=np.asarray(residual)
    assert len(t)==len(d)==len(r) and len(t)>=2
    t=t-np.mean(t);d=d-np.mean(d);r=r-np.mean(r)
    drms=float(np.sqrt(np.mean(d*d)))
    result=dict(direction_rms_hz=drms,residual_rms_hz=float(np.sqrt(np.mean(r*r))),
                residual_median_absolute_centered_hz=float(np.median(abs(r-np.median(r)))))
    if drms<=1e-6 or np.dot(t,t)==0:
        return dict(result,linear_fraction=None,projection_beta=None)
    line=t*np.dot(t,d)/np.dot(t,t)
    return dict(result,linear_fraction=float(np.dot(line,line)/np.dot(d,d)),
                projection_beta=float(np.dot(r,d)/np.dot(d,d)))


def main():
    path=REPORTS/'2026_09_29_orbit_revision_transfer/directions.json'
    directions=read(path);sources={str(path):digest(path),str(Path(__file__)):digest(Path(__file__)),
                                 str(HERE/'test_run.py'):digest(HERE/'test_run.py')}
    for name,h in directions['hashes'].items():
        p=Path(name);p=p if p.is_absolute() else ROOT/p
        assert digest(p)==h,name
        sources[str(p)]=h
    cases={};start_ranges=collections.defaultdict(list)
    for unit in sorted({r['unit_id'] for r in directions['rows']}):
        p=REPORTS/'2026_09_29_donor_residual_transfer/runs'/unit/'result.json'
        assert str(p) in sources
        for r in read(p)['cases']:
            key=(unit,r['session_id'],r['track_id']);assert key not in cases;cases[key]=r
            start_ranges[unit.split('_')[0]].append(r['start_utc_ns'])
    results=[];groups=collections.defaultdict(list)
    for row in directions['rows']:
        key=(row['unit_id'],row['session_id'],row['track_id']);case=cases[key]
        assert row['number']==case['number'] and row['mask']==case['mask']
        np.testing.assert_allclose(row['residual'],case['residual'],rtol=0,atol=1e-6)
        mask=np.asarray(row['mask'],bool)
        s=shape(np.asarray(case['times'])[mask],np.asarray(row['delta'])[mask],np.asarray(row['residual'])[mask])
        result=dict(unit_id=row['unit_id'],session_id=row['session_id'],track_id=row['track_id'],
                    number=row['number'],rf_hz=case['rf_hz'],changed=row['changed'],status=row['status'],**s)
        results.append(result)
        groups[(row['unit_id'].split('_')[0],row['session_id'],row['number'],case['rf_hz'])].append(result)
    pooled=[]
    for (dataset,session,number,rf),rows in groups.items():
        valid=[r for r in rows if r['linear_fraction'] is not None]
        pooled.append(dict(dataset=dataset,session_id=session,number=number,rf_hz=rf,tracks=len(rows),
                           direction_rms_hz=float(np.median([r['direction_rms_hz'] for r in rows])),
                           residual_scale_hz=float(np.median([r['residual_median_absolute_centered_hz'] for r in rows])),
                           linear_fraction=float(np.median([r['linear_fraction'] for r in valid])) if valid else None))
    summary={}
    for dataset in sorted(start_ranges):
        all_rows=[r for r in pooled if r['dataset']==dataset]
        valid=[r for r in all_rows if r['linear_fraction'] is not None]
        summary[dataset]=dict(source_occasions=len(all_rows),nonzero_direction_occasions=len(valid),
                              median_linear_fraction=float(np.median([r['linear_fraction'] for r in valid])),
                              fraction_at_least_99_percent_linear=sum(r['linear_fraction']>=.99 for r in valid)/len(valid),
                              direction_size_vs_residual_scale_spearman=float(spearmanr([r['direction_rms_hz'] for r in valid],[r['residual_scale_hz'] for r in valid]).statistic),
                              capture_min_utc_ns=min(start_ranges[dataset]),capture_max_utc_ns=max(start_ranges[dataset]))
    chronology=max(start_ranges['DS7']+start_ranges['DS8'])<min(start_ranges['DS9'])
    output=dict(schema='causal-revision-training-shape-audit/v1',rows=results,source_occasions=pooled,
                summary=summary,ds7_ds8_captures_precede_ds9=chronology,held_values_used=False,
                position_fits=0,reference_used=False,calibrates_orbit_covariance=False,sources=sources)
    with (HERE/'outcome.json').open('x') as stream:json.dump(output,stream,indent=2,allow_nan=False)
    print(json.dumps(dict(summary=summary,ds7_ds8_captures_precede_ds9=chronology),indent=2))


if __name__=='__main__':main()
