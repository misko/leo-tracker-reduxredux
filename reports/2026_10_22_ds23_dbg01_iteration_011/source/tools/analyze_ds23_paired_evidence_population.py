"""Report-only format and temporal-block sensitivity of the sealed RF guard."""

from pathlib import Path
import numpy as np

import probe_ds23_paired_replacement_evidence as study
from run_algo02_ds23 import DEFAULT_RUN
from run_algo01_ds23_sample import read,write,sha


def bootstrap(old,new,timestamps,hours,seed=2026102211,samples=5000):
    labels=np.asarray(timestamps,dtype=np.int64)//int(hours*3600e9);blocks=sorted(set(labels));indices=[np.flatnonzero(labels==b) for b in blocks]
    draw=np.random.default_rng(seed).integers(0,len(indices),(samples,len(indices)))
    mean=[];median=[]
    for sample in draw:
        ix=np.concatenate([indices[j] for j in sample]);mean.append(float(np.mean(new[ix]-old[ix])));median.append(float(np.median(new[ix])-np.median(old[ix])))
    return dict(hours=hours,occupied_blocks=len(indices),samples=samples,seed=seed,
        mean_change95_km=np.percentile(mean,[2.5,97.5]),median_change95_km=np.percentile(median,[2.5,97.5]))


def main():
    out=study.OUT
    if (out/'population_sensitivity.json').exists():raise FileExistsError('preserve population sensitivity')
    data=read(out/'evaluation.json');meta={r['dataset_label']:r for r in read(DEFAULT_RUN/'sample.json')['selected']};summary=[];uncertainty=[]
    for arm in ['c0','fitted_c']:
        old={r['case']:r for r in data['rows'] if r['method']=='published_c0_positive' and r['arm']==arm}
        for method in ['paired_positive','paired_2log2_margin']:
            new={r['case']:r for r in data['rows'] if r['method']==method and r['arm']==arm};cases=sorted(old)
            for fmt in sorted({meta[c]['recording_format'] for c in cases}):
                members=[c for c in cases if meta[c]['recording_format']==fmt];a=np.array([old[c]['position_error_km'] for c in members]);b=np.array([new[c]['position_error_km'] for c in members])
                summary.append(dict(arm=arm,method=method,recording_format=fmt,cases=len(members),
                    old_mean_km=float(a.mean()),new_mean_km=float(b.mean()),old_median_km=float(np.median(a)),new_median_km=float(np.median(b)),
                    changed_cases=[c for c in members if new[c]['accepted_replacement']!=old[c]['accepted_replacement']]))
            a=np.array([old[c]['position_error_km'] for c in cases]);b=np.array([new[c]['position_error_km'] for c in cases]);times=[meta[c]['captured_utc_ns'] for c in cases]
            for hours in [1,3,6]:uncertainty.append(dict(arm=arm,method=method,**bootstrap(a,b,times,hours)))
    # Describe concentration of evidence without using it for any RF choice.
    engineering={'DS23-0268','DS23-0405','DS23-0080'};outside=[]
    for arm in ['c0','fitted_c']:
        a={r['case']:r for r in data['rows'] if r['method']=='published_c0_positive' and r['arm']==arm and r['case'] not in engineering}
        b={r['case']:r for r in data['rows'] if r['method']=='paired_positive' and r['arm']==arm and r['case'] not in engineering}
        outside.append(dict(arm=arm,cases=len(a),old_mean_km=float(np.mean([r['position_error_km'] for r in a.values()])),
            new_mean_km=float(np.mean([r['position_error_km'] for r in b.values()])),
            changed_cases=[c for c in a if a[c]['accepted_replacement']!=b[c]['accepted_replacement']]))
    write(out/'population_sensitivity.json',dict(format_summary=summary,temporal_bootstrap=uncertainty,
        outside_original_engineering_three=outside,report_only_no_policy_selection=True,
        intervals_descriptive_after_extensive_same_site_development=True,no_new_location_or_full_goal_achievement=True,
        source_sha256=sha(Path(__file__)),sample_metadata_sha256=sha(DEFAULT_RUN/'sample.json')))
    import report_ds23_dbg01_iteration_001 as f
    f.csv_write(out/'format_summary.csv',summary);f.csv_write(out/'temporal_bootstrap.csv',uncertainty)
    print(summary,flush=True);print(uncertainty,flush=True)


if __name__=='__main__':main()
