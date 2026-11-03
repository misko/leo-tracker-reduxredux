"""Corrected, source-bound component study; invalid v1 phase runs are preserved."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from ds23_synthetic_phase_law import bounded_phase_draw
import probe_ds23_synthetic_nuisance_components as component
from run_algo01_ds23_sample import ROOT,read,write,sha
import run_ds23_combined_recovery_full as inference

OUT=ROOT/'reports/2026_10_20_ds23_synthetic_nuisance_v2'
PREVIOUS=ROOT/'reports/2026_10_20_ds23_synthetic_nuisance_validation'
PILOT=ROOT/'reports/2026_10_20_ds23_synthetic_nuisance_components'
NOISE=ROOT/'reports/2026_10_20_ds23_synthetic_noise'


def initialize():
    inference.prepare();previous=read(PREVIOUS/'protocol.json')
    for name,expected in previous['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=expected:raise ValueError('original control source changed')
    site=dict(previous['site_by_case']);site.update({c:[-5.,5.] for c in component.TEMPLATES})
    jobs=[dict(case=c,draw=0,group=g,stratum='random_validation') for c in previous['cases'] for g in component.GROUPS]
    jobs += [dict(case=c,draw=d,group=g,stratum='engineering') for c in component.TEMPLATES for d in range(2) for g in component.GROUPS]
    paths=[Path(__file__),ROOT/'tools/ds23_synthetic_phase_law.py',ROOT/'tools/probe_ds23_synthetic_nuisance_components.py',ROOT/'tools/probe_ds23_synthetic_noise.py',ROOT/'tools/probe_ds23_synthetic_closure.py']
    protocol=dict(jobs=jobs,site_by_case=site,workers=8,per_instance_seconds=120,
        random_sample_protocol_sha256=sha(PREVIOUS/'protocol.json'),same_cases_sites_noise_and_latent_quantiles_as_v1=True,
        correction='Student-t unit-variance scale sqrt((nu-2)/nu), matched to frozen distribution_cost and hierarchical_bound',
        invalidated_v1_groups=['phase','all'],v1_other_components_and_noise_reused_with_hash_bindings=True,
        phase_conditioned_on_bounds_s=[-15,15],true_radio_c=0,fit_both_c_arms=True,
        conditional_oracle_label_simulation_not_real_accuracy_gain=True,full_hierarchical_prior_predictive=False,
        source_sha256={p.name:sha(p) for p in paths})
    OUT.mkdir(parents=True,exist_ok=True);target=OUT/'protocol.json'
    if target.exists() and read(target)!=protocol:raise ValueError('corrected simulation protocol changed')
    if not target.exists():write(target,protocol)
    return protocol


def worker(job,site):
    case,draw,group=job['case'],job['draw'],job['group']
    if job['stratum']=='engineering' and group not in ('phase','all'):
        path=PILOT/(case+'_draw'+str(draw)+'_'+group+'.json')
        r=read(path)
        return dict(job,path=str(path.relative_to(ROOT)),sha256=sha(path),status=r['status'],reused_unaffected_v1=True)
    component.OUT=OUT;component.SITE=tuple(site);component.bounded_phase_draw=bounded_phase_draw
    r=component.run(case,draw,group)
    path=OUT/(case+'_draw'+str(draw)+'_'+group+'.json')
    return dict(job,path=str(path.relative_to(ROOT)),sha256=sha(path),status=r['status'],reused_unaffected_v1=False)


def stats(rows,stratum):
    result={}
    for group in ('noise_only',*component.GROUPS):
        result[group]={}
        for arm in inference.ARMS:
            selected=[r for r in rows if r['stratum']==stratum and r['group']==group and r['status']=='complete']
            errors=[r['arms'][arm]['synthetic_position_error_km'] for r in selected]
            result[group][arm]=dict(n=len(errors),mean_km=float(np.mean(errors)) if errors else None,
                median_km=float(np.median(errors)) if errors else None,maximum_km=max(errors) if errors else None,
                paired_qualified=sum(inference.valid(r['arms']) for r in selected),
                original_RF_gate_pass=sum(r['arms'][arm]['original_gate_counts']['all_original_gates_pass'] for r in selected))
    return result


def main():
    protocol=initialize();receipts=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        jobs=[pool.submit(worker,j,protocol['site_by_case'][j['case']]) for j in protocol['jobs']]
        for f in as_completed(jobs):
            receipts.append(f.result());write(OUT/'progress.json',dict(completed=len(receipts),total=len(jobs)))
    rows=[]
    for entry in receipts:
        if sha(ROOT/entry['path'])!=entry['sha256']:raise ValueError('component result changed')
        rows.append(dict(read(ROOT/entry['path']),stratum=entry['stratum']))
    for stratum,cases,draws,directory in [('random_validation',list(read(PREVIOUS/'protocol.json')['cases']),[0],PREVIOUS),('engineering',list(component.TEMPLATES),[0,1],NOISE)]:
        for case in cases:
            for draw in draws:
                path=directory/(case+'_draw'+str(draw)+'.json');r=read(path)
                rows.append(dict(r,group='noise_only',stratum=stratum))
                receipts.append(dict(case=case,draw=draw,group='noise_only',stratum=stratum,path=str(path.relative_to(ROOT)),sha256=sha(path),status=r['status'],reused_unaffected_v1=True))
    failures=[{k:r.get(k) for k in ['case','draw','group','stratum','error']} for r in rows if r['status']!='complete']
    evaluation=dict(instances=len(rows),failures=failures,summary={s:stats(rows,s) for s in ('engineering','random_validation')},
        receipts=receipts,protocol_sha256=sha(OUT/'protocol.json'),unit_variance_Student_correction_verified=True,
        real_DS23_accuracy_gain=False,not_full_hierarchical_prior_predictive=True)
    write(OUT/'evaluation.json',evaluation)
    print('CORRECTED_COMPONENT_STUDY_COMPLETE',evaluation['summary'],flush=True)


if __name__=='__main__':main()
