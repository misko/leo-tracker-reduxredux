"""Blinded, format-balanced extension of known-label component simulations."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from run_algo01_ds23_sample import ROOT,read,write,sha
import run_ds23_combined_recovery_full as inference

OUT=ROOT/'reports/2026_10_20_ds23_synthetic_nuisance_validation'
SITES=((-5.,5.),(5.,5.),(-5.,-5.),(5.,-5.))


def balanced_sample(members,available,excluded,per_format,seed):
    rng=np.random.default_rng(seed);selected=[]
    for fmt in ('short_window_iq_recording','starlink_adaptive_hop_iq'):
        pool=sorted(m['dataset_label'] for m in members if m['recording_format']==fmt and m['dataset_label'] in available and m['dataset_label'] not in excluded)
        if len(pool)<per_format:raise ValueError('insufficient eligible format population')
        selected.extend(rng.choice(pool,per_format,replace=False).tolist())
    return sorted(selected)


def initialize():
    base=inference.prepare();members=read(inference.DEFAULT_RUN/'sample.json')
    excluded=set(members['development_cases'])|{'DS23-0001','DS23-0002','DS23-0268','DS23-0039','DS23-0342'}
    cases=balanced_sample(members['selected'],set(base['available_cases']),excluded,10,882733)
    paths=[Path(__file__),ROOT/'tools/probe_ds23_synthetic_nuisance_components.py',ROOT/'tools/probe_ds23_synthetic_noise.py',ROOT/'tools/probe_ds23_synthetic_closure.py']
    protocol=dict(cases=cases,site_by_case={c:list(SITES[k%len(SITES)]) for k,c in enumerate(cases)},
        scenarios=['noise_only','all_components'],draw=0,workers=8,per_instance_seconds=120,
        original_population=413,available_real_templates=410,selection_seed=882733,per_format=10,
        excluded_cases=sorted(excluded),selection_uses_only_format_and_availability=True,
        evaluation_position_and_errors_not_read_for_selection_or_inference=True,
        conditional_oracle_label_simulation_not_real_accuracy_validation=True,
        full_hierarchical_prior_predictive=False,
        original_RF_templates_previously_analyzed_not_untouched_holdout=True,
        source_sha256={p.name:sha(p) for p in paths},
        original_full_protocol_sha256=sha(inference.OUT/'protocol.json'),
        original_independent_audit_sha256=sha(inference.OUT/'evaluation_audit.json'))
    OUT.mkdir(parents=True,exist_ok=True);path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('validation protocol changed')
    if not path.exists():write(path,protocol)
    return protocol


def worker(case,scenario,site):
    import probe_ds23_synthetic_nuisance_components as component
    import probe_ds23_synthetic_noise as noise
    component.OUT=OUT;noise.OUT=OUT;component.SITE=tuple(site);noise.SITE=tuple(site)
    result=component.run(case,0,'all') if scenario=='all_components' else noise.run(case,0)
    path=OUT/(case+'_draw0'+('_all' if scenario=='all_components' else '')+'.json')
    return dict(case=case,scenario=scenario,path=str(path.relative_to(ROOT)),sha256=sha(path),status=result['status'])


def summarize(rows):
    output={}
    for scenario in ('noise_only','all_components'):
        output[scenario]={}
        for arm in inference.ARMS:
            selected=[r for r in rows if r['scenario']==scenario and r['status']=='complete'];errors=[r['arms'][arm]['synthetic_position_error_km'] for r in selected]
            qualified=[r for r in selected if inference.valid(r['arms'])]
            q=[r['arms'][arm]['synthetic_position_error_km'] for r in qualified]
            output[scenario][arm]=dict(n=len(errors),mean_km=float(np.mean(errors)) if errors else None,
                median_km=float(np.median(errors)) if errors else None,maximum_km=max(errors) if errors else None,
                paired_qualified=len(qualified),qualified_mean_km=float(np.mean(q)) if q else None,
                qualified_median_km=float(np.median(q)) if q else None,
                original_RF_gate_pass=sum(r['arms'][arm]['original_gate_counts']['all_original_gates_pass'] for r in selected))
    return output


def main():
    protocol=initialize();receipts=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        jobs=[pool.submit(worker,c,s,protocol['site_by_case'][c]) for c in protocol['cases'] for s in protocol['scenarios']]
        for f in as_completed(jobs):
            receipts.append(f.result());write(OUT/'progress.json',dict(completed=len(receipts),total=len(jobs)))
    rows=[]
    for r in receipts:rows.append(dict(read(ROOT/r['path']),scenario=r['scenario']))
    failures=[{k:r.get(k) for k in ('case','scenario','status','error')} for r in rows if r['status']!='complete']
    write(OUT/'evaluation.json',dict(instances=len(rows),summary=summarize(rows),failures=failures,
        receipts=receipts,all_selected_instances_retained=True,protocol_sha256=sha(OUT/'protocol.json'),
        synthetic_evidence_only=True,no_real_data_accuracy_improvement_claim=True))
    print('VALIDATION_COMPLETE',summarize(rows),flush=True)


if __name__=='__main__':main()
