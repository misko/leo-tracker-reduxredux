"""Offline interval reporting sensitivity. No estimator or RF calls.

Frozen v1 linearly interpolated cumulative mass at grid centers, shifting a
concentrated distribution downward. Preserve it. This audit reports both the
literal discrete-mass quantile and a bin-density interpretation of each saved
grid weight, with bins bounded by adjacent midpoints and the search limits.
Neither interpretation establishes physical RF uncertainty calibration.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE=Path(__file__).resolve().parent


def quantiles(grid,weights,probabilities=(.025,.5,.975),interpretation='bin_density'):
    grid=np.asarray(grid,float); weights=np.asarray(weights,float)
    if grid.ndim!=1 or len(grid)<2 or weights.shape!=grid.shape or np.any(weights<0):
        raise ValueError('invalid grid weights')
    if not np.all(np.isfinite(weights)) or weights.sum()<=0 or np.any(np.diff(grid)<=0):
        raise ValueError('nonfinite/empty weights or unordered grid')
    weights=weights/weights.sum();cdf=np.cumsum(weights)
    probs=np.asarray(probabilities,float)
    if np.any((probs<=0)|(probs>=1)):raise ValueError('interior probabilities required')
    indexes=np.searchsorted(cdf,probs,side='left')
    if interpretation=='discrete_mass':return grid[indexes].tolist()
    if interpretation!='bin_density':raise ValueError('unknown interpretation')
    # Endpoint bins are half width, clipped to the unchanged search limits.
    edges=np.r_[grid[0],(grid[:-1]+grid[1:])/2,grid[-1]]
    prior=np.r_[0.,cdf[:-1]][indexes]
    fraction=(probs-prior)/weights[indexes]
    return (edges[indexes]+fraction*(edges[indexes+1]-edges[indexes])).tolist()


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def prepare():
    names=['interval_audit_v2.py','test_interval_audit_v2.py','protocol.json','synthetic.json','recorded.json']
    write(HERE/'interval_audit_v2_protocol.json',dict(schema='offline-interval-reporting-audit/v2',
        frozen_utc_ns=time.time_ns(),files={str(HERE/n):sha(HERE/n) for n in names},
        reason='Review found cumulative mass interpolated at centers shifts v1 quantiles downward',
        correction_scope='saved weights only; no RF/likelihood/prior/CFO/gate changes',
        primary_sensitivity='uniform density inside midpoint bins clipped to search domain',
        secondary_sensitivity='literal discrete grid masses; offgrid truth has discretization risk'))


def audit():
    began=time.monotonic();p=read(HERE/'interval_audit_v2_protocol.json')
    for path,digest in p['files'].items():
        if sha(path)!=digest:raise ValueError('offline interval input changed')
    rows=[]
    for kind in ['synthetic','recorded']:
        source=read(HERE/(kind+'.json'))
        items=source['rows'] if kind=='synthetic' else [dict(**c,request_id=r['request_id'])
            for r in source['rows'] for c in r['cells']]
        for i,item in enumerate(items):
            estimate=item['estimate'];primary=estimate['primary']
            if primary is None:continue
            proposal=primary['proposed'];grid=proposal['grid_offsets_hz'];weights=proposal['conditional_grid_weights']
            # Truth stays in offline evaluation, never enters quantile calculation.
            reports={method:quantiles(grid,weights,interpretation=method)
                for method in ['bin_density','discrete_mass']}
            true_cfo=item['truth_cfo_hz'] if kind=='synthetic' else 213456.75
            center=primary['predicted_cfo_hz'];truth_offset=true_cfo-center
            original=proposal['conditional_95_interval_offsets_hz']
            coverage={'frozen_v1':bool(original[0]<=truth_offset<=original[1])}
            for method,q in reports.items():coverage[method]=bool(q[0]<=truth_offset<=q[2])
            row=dict(source=kind,index=i,prediction_id=estimate['prediction_id'],
                original_interval_offsets_hz=original,quantiles_offsets_hz=reports,
                coverage=coverage,truth_offset_hz=truth_offset,
                nearest_grid_error_hz=float(np.min(abs(np.asarray(grid)-truth_offset))),
                uncertainty_qualified=False)
            if kind=='synthetic':
                row.update({k:item[k] for k in ['edge','db','forecast','true_rate_hz_s','donor_error_hz','repetition']})
            rows.append(row)
    totals={}
    for kind in ['synthetic','recorded']:
        selected=[r for r in rows if r['source']==kind]
        totals[kind]=dict(n=len(selected),covered={key:sum(r['coverage'][key] for r in selected)
            for key in ['frozen_v1','bin_density','discrete_mass']})
    write(HERE/'interval_audit_v2.json',dict(schema='offline-interval-reporting-audit/v2',
        protocol_sha256=sha(HERE/'interval_audit_v2_protocol.json'),rows=rows,totals=totals,
        original_sealed_outputs_unchanged=True,RF_calls=0,likelihood_calls=0,
        caveat='25Hz discretization and within-bin density are numerical assumptions; neither interval is calibrated RF uncertainty',
        seconds=time.monotonic()-began))
    print(json.dumps(totals),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','audit'])
    prepare() if p.parse_args().action=='prepare' else audit()
