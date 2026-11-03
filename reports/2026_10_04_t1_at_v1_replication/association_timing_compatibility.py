"""Audit how coverage-selected timing shifts compare with localization priors.

No fits or association changes. Large shifts flag a mismatch with the stated
prior, not proof of an incorrect satellite identity or a calibrated p-value.
"""
import csv
import json
from pathlib import Path
import numpy as np
from leave_one_satellite_out import load,HERE
from timing_bound_comparison import digest
from subset_positions import serial

OUT=HERE/'timing-prior-ablation'


def timing_summary(numbers,timing,owners):
    numbers,timing,owners=map(np.asarray,(numbers,timing,owners))
    if numbers.ndim!=1 or timing.shape!=numbers.shape or not len(numbers):raise ValueError('Invalid satellite/timing arrays')
    if len(set(numbers.tolist()))!=len(numbers) or not np.all(np.isin(owners,numbers)):raise ValueError('Unknown or duplicate satellite')
    mean=float(np.mean(timing));delta=timing-mean
    counts=np.array([sum(owners==n) for n in numbers])
    return dict(common_timing_s=mean,relative_timing_rms_s=float(np.sqrt(np.mean(delta**2))),
        relative_over3s_satellites=int(sum(abs(delta)>3)),relative_over3s_windows=int(sum(counts[abs(delta)>3])),
        relative_over5s_satellites=int(sum(abs(delta)>5)),relative_over5s_windows=int(sum(counts[abs(delta)>5])),
        nominal_relative_prior_nll=float(.5*np.sum(delta**2)),
        tracks=[dict(satellite=int(n),total_shift_s=float(t),relative_shift_s=float(x),windows=int(k))
                for n,t,x,k in zip(numbers,timing,delta,counts)])


def main():
    rows=[];details={}
    for scan in (f'N{i:02}' for i in range(1,17)):
        d,meta,_=load(scan);source=Path(meta['association_source'])
        assert digest(source)==meta['association_sha256']
        receipt=json.loads(source.read_text());selected={r['catalog_number']:r for r in receipt['final']['selected']}
        times=np.array([selected[int(n)]['offset_s'] for n in d.numbers])
        np.testing.assert_array_equal(times,d.initial[6:])
        stats=timing_summary(d.numbers,times,d.owners)
        rows.append(dict(scan=scan,satellites=len(d.numbers),windows=len(d.times),
                         **{k:v for k,v in stats.items() if k!='tracks'}))
        details[scan]=dict(association_source=str(source),association_sha256=digest(source),
            input_sha256=meta['input_sha256'],**stats)
    OUT.mkdir(exist_ok=True)
    with (OUT/'association-timing-compatibility.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    report=dict(scope=__doc__,association_objective='assigned unique windows - 10 * selected satellites',
        association_timing_penalty='None in primary coverage objective; timing is used in candidate refinement and exact-count tie-breaks.',localization_relative_timing_sigma_s=1.,
        note='Coverage counts and negative log likelihood have different units; these penalties are not directly subtracted from coverage.',
        details=details)
    (OUT/'association-timing-compatibility.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
