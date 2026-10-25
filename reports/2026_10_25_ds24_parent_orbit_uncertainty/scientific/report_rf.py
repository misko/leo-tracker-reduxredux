"""Report sealed RF quantities only; never compute geographic truth errors."""
import csv
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
CASES=tuple(f'DS24-{i:04d}' for i in range(10,14))
ARMS=('c0','fitted_c')


def read(path):return json.loads(Path(path).read_text())


def report():
    import hashlib
    def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def verify(seal):
        for path,expected in seal['files'].items():
            if sha(path)!=expected:raise ValueError('sealed artifact changed: '+path)
    fixed_seal=read(HERE/'fixed_seal.json');fit_seal=read(HERE/'fits_seal.json')
    verify(fixed_seal);verify(fit_seal)
    output=HERE/'rf_report';output.mkdir(exist_ok=False)
    rows=[];cases=[]
    for case in CASES:
        fixed=read(HERE/'fixed'/f'{case}.json');result=read(HERE/'fits'/case/'result.json')
        case_report=dict(case=case,status=result['status'],research_policy_source=result['research_policy_source'],
            operational_policy_source=result['operational_policy_source'],failures=result['failures'],
            candidate_all_baseline_accepted_IDs_preserved=result['candidate_all_baseline_accepted_IDs_preserved'])
        cases.append(case_report)
        for arm in ARMS:
            f=fixed['arms'].get(arm,{})
            row=dict(case=case,arm=arm,fixed_qualified=f.get('numerically_qualified'),
                fixed_movement_proxy_m=1000*f.get('movement_proxy_norm_km',float('nan')),
                fixed_weak_variance_change_percent=100*f.get('weak_variance_fractional_change',float('nan')),
                candidate_adopted=result['research_policy_adopted'],operational_source='original_reference')
            baseline=result['methods'].get('matched_cold_baseline',{}).get('arms',{}).get(arm)
            candidate=result['methods'].get('retained_uncertainty',{}).get('arms',{}).get(arm)
            if baseline and candidate:
                method=result['methods']['retained_uncertainty']
                cov=result['coverage']['retained_uncertainty'][arm];reference=result['coverage']['original_reference'][arm]
                row.update(raw_candidate_shift_from_cold_m=1000*float(np.linalg.norm(np.asarray(candidate['endpoint_east_north_km'])-baseline['endpoint_east_north_km'])),
                    cold_baseline_RMS_hz=baseline['RMS_hz'],raw_candidate_gate_RMS_hz=candidate['RMS_hz'],
                    raw_candidate_full_RMS_hz=candidate['likelihood_conditional_RMS_hz'],
                    objective_change=candidate['negative_twice_elbo']-baseline['negative_twice_elbo'],
                    conservative_paired_valid=method['conservative_paired_valid'],
                    literal_expanded_paired_valid=method['literal_expanded_paired_valid'],
                    original_accepted=len(reference['accepted_observation_ids']),candidate_accepted=len(cov['accepted_observation_ids']),
                    lost_original_IDs=len(set(reference['accepted_observation_ids'])-set(cov['accepted_observation_ids'])),
                    gained_IDs=len(set(cov['accepted_observation_ids'])-set(reference['accepted_observation_ids'])),
                    curved_likelihood_IDs=cov['curved_points'],predictive_likelihood_IDs=cov['predictive_points'],total_GLRT=cov['total_GLRT'],
                    failed_curved_components=';'.join(q['component'] for q in candidate['gates']['tracks'] if not q['compatible']),
                    failed_predictive_components=';'.join(q['component'] for q in candidate['linear_gates'] if not q['compatible']))
            rows.append(row)
    fields=list(dict.fromkeys(key for row in rows for key in row))
    with (output/'RF_table.csv').open('x') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    for k,arm in enumerate(ARMS):
        panel=[q for q in rows if q['arm']==arm];xx=np.arange(4)+(k-.5)*.27
        axes[0].bar(xx,[q['fixed_movement_proxy_m'] for q in panel],width=.27,label=arm)
        axes[1].bar(xx,[q['fixed_weak_variance_change_percent'] for q in panel],width=.27,label=arm)
    axes[0].axhline(50,color='k',ls=':',label='predeclared50m triage')
    axes[1].axhline(5,color='k',ls=':',label='predeclared5% triage')
    axes[0].set_ylabel('Local model-change movement proxy (m)')
    axes[1].set_ylabel('Fixed-old-state weak variance increase (%)')
    for ax in axes:ax.set_xticks(range(4),[c[-4:] for c in CASES]);ax.legend(fontsize=8);ax.set_xlabel('Exposed DS24 scan')
    fig.suptitle('RF fixed-state diagnostics; local proxies, not actual position errors')
    fig.savefig(output/'fixed_state.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
    for k,arm in enumerate(ARMS):
        panel=[q for q in rows if q['arm']==arm and 'objective_change' in q];xx=np.array([CASES.index(q['case']) for q in panel])+(k-.5)*.27
        axes[0].bar(xx,[q['raw_candidate_full_RMS_hz']-q['cold_baseline_RMS_hz'] for q in panel],width=.13,label=arm+' full likelihood')
        axes[0].bar(xx+.13,[q['raw_candidate_gate_RMS_hz']-q['cold_baseline_RMS_hz'] for q in panel],width=.13,hatch='//',alpha=.6,label=arm+' conservative gate view')
        axes[1].bar(xx,[q['objective_change'] for q in panel],width=.27,label=arm)
    axes[0].set_ylabel('Raw candidate minus matched cold baseline RMS (Hz)')
    axes[1].set_ylabel('Raw candidate minus matched cold baseline −2ELBO')
    for ax in axes:ax.axhline(0,color='k',lw=.7);ax.set_xticks(range(4),[c[-4:] for c in CASES]);ax.set_xlabel('Exposed DS24 scan');ax.legend(fontsize=7)
    fig.suptitle('All available raw endpoints, including any unqualified results')
    fig.savefig(output/'fit_RF_changes.png',dpi=160);plt.close(fig)
    summary=dict(cases=cases,rows=rows,position_truth_or_GPS_used=False,
        fixed_seal_sha256=sha(HERE/'fixed_seal.json'),fit_seal_sha256=sha(HERE/'fits_seal.json'))
    with (output/'RF_summary.json').open('x') as stream:json.dump(summary,stream,indent=2,allow_nan=False)
    files={str(p):sha(p) for p in output.iterdir() if p.is_file()}
    files[str(Path(__file__))]=sha(Path(__file__))
    with (output/'seal.json').open('x') as stream:json.dump(dict(files=files),stream,indent=2)
    print(json.dumps(cases,indent=2))


if __name__=='__main__':report()
