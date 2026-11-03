"""Aggregate shared receiver drift tests on identical held-out memberships."""
import csv,json
import numpy as np
from benchmark import ROOT,digest


def main():
    folder=ROOT/'receiver-spline';rows=[];sources={}
    for scan in ('A','B'):
        p=folder/f'{scan}.json';r=json.loads(p.read_text());sources[str(p)]=digest(p)
        for source,sha in r['sources'].items():assert digest(source)==sha
        for arm in ('fitted-c','zero-c'):
            rr=[v for v in r['results'] if v['arm']==arm];assert sorted(v['fold'] for v in rr)==list(range(5))
            count=sum(v['identical_test_points'] for v in rr)
            row=dict(scan=scan,arm=arm,identical_test_points=count,heldout_log_likelihood_change=sum(v['heldout_change'] for v in rr),
                improved_prediction_folds=sum(v['heldout_change']>0 for v in rr),
                improved_leave_satellite_out_folds=sum(v['leave_satellite_out_rms_hz']<v['before_rms_hz'] for v in rr),
                largest_test_correction_hz=max(v['max_abs_test_correction_hz'] for v in rr))
            for key in ('before_rms_hz','shared_rms_hz','leave_satellite_out_rms_hz'):
                row[key]=float(np.sqrt(sum(v['identical_test_points']*v[key]**2 for v in rr)/count))
            rows.append(row)
    with (folder/'comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (folder/'summary.json').write_text(json.dumps(dict(rows=rows,sources=sources,
        warning='Training-only receiver-shared nonlinear drift diagnostic. Constant and linear components excluded; fixed zero-centered priors. Transfer excludes each satellite from this correction fit, not from earlier calibration. No newly decoded or certified coverage.'),indent=2))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
