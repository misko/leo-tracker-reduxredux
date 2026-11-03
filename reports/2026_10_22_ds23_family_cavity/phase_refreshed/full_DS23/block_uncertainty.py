"""Post-evaluation sensitivity to correlated scan times; never selects fits."""

from pathlib import Path
import json
import hashlib
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest=ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json'
    evaluation=HERE/'position/evaluation.json';data=read(evaluation)
    members={r['dataset_label']:r for r in read(manifest)['members']};rows=data['rows'];out=[];groups=[]
    for policy in ['equal_assignment_priors','incumbent_sticky_prior']:
        for arm in ['c0','fitted_c']:
            selected=sorted([r for r in rows if (r['policy'],r['arm'])==(policy,arm)],key=lambda r:members[r['case']]['captured_utc_ns'])
            old=np.array([r['original_error_km'] for r in selected]);new=np.array([r['policy_error_km'] for r in selected]);delta=new-old
            times=np.array([members[r['case']]['captured_utc_ns'] for r in selected],dtype=np.int64)
            for hours in [1,3,6]:
                labels=times//int(hours*3600*1e9);unique=np.unique(labels)
                totals=np.array([sum(delta[labels==u]) for u in unique]);counts=np.array([sum(labels==u) for u in unique])
                rng=np.random.default_rng(2026102205);ix=rng.integers(0,len(unique),size=(10000,len(unique)))
                boot=totals[ix].sum(axis=1)/counts[ix].sum(axis=1)
                out.append(dict(policy=policy,arm=arm,block_hours=hours,occupied_blocks=len(unique),
                    mean_change_km=float(delta.mean()),mean_change95_km=np.percentile(boot,[2.5,97.5]).tolist()))
            for fmt in sorted({members[r['case']]['recording_format'] for r in selected}):
                sub=[r for r in selected if members[r['case']]['recording_format']==fmt]
                a=np.array([r['original_error_km'] for r in sub]);b=np.array([r['policy_error_km'] for r in sub])
                groups.append(dict(policy=policy,arm=arm,recording_format=fmt,count=len(sub),accepted=sum(r['accepted'] for r in sub),
                    original_mean_km=float(a.mean()),new_mean_km=float(b.mean()),original_median_km=float(np.median(a)),new_median_km=float(np.median(b)),
                    improved=int(sum(b<a-1e-6)),worsened=int(sum(b>a+1e-6))))
    result=dict(block_mean_sensitivity=out,recording_format_diagnostics=groups,manifest_sha256=sha(manifest),
        evaluation_sha256=sha(evaluation),seed=2026102205,repetitions=10000,
        post_evaluation_uncertainty_sensitivity_not_model_selection=True,no_new_location_or_untouched_holdout=True)
    (HERE/'position/temporal_block_sensitivity.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
