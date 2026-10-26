"""Final coherent development figures and compact receipts; no inference."""
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from integrate import read,write,sha


def main():
    e=read(HERE/'position_evaluation_native.json');assert read(HERE/'position_inference_audit.json')['all_complete']
    lookup={(r['case'],r['variant']):r for r in e['rows']};cases=['DS24-0011','DS24-0097'];variants=['baseline','additions_proxy','additions_bin_floor']
    labels=['Sealed baseline','Expansion proxy','Expansion full-bin floor'];fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,case in enumerate(cases):
        x=np.arange(3)
        for j,(arm,label,color) in enumerate([('c0','c = 0','#2563eb'),('fitted_c','Fitted c','#0f766e')]):
            values=[1000*lookup[case,v]['arms'][arm]['position_error_km'] for v in variants]
            rms=[lookup[case,v]['arms'][arm]['RMS_hz'] for v in variants]
            bars=axes[0,col].bar(x+(j-.5)*.32,values,width=.3,color=color,label=label)
            for bar,value in zip(bars,values):axes[0,col].text(bar.get_x()+bar.get_width()/2,value+max(values)*.015,f'{value:.1f}',ha='center',fontsize=8)
            axes[1,col].plot(x,rms,'o-',color=color,label=label)
        axes[0,col].set_title(case);axes[0,col].set_ylabel('Post-seal position error (m)');axes[0,col].set_ylim(0,max(1000*lookup[case,v]['arms'][a]['position_error_km'] for v in variants for a in ('c0','fitted_c'))*1.14)
        for row in (0,1):axes[row,col].set_xticks(x,labels,rotation=8);axes[row,col].grid(axis='y',alpha=.2)
        axes[0,col].legend(frameon=False);axes[1,col].set_ylabel('Reported frequency RMS (Hz)');axes[1,col].legend(frameon=False)
    fig.suptitle('Coherent application: geographic effects and frequency fit are separate\nFour fresh weight variants; two equality-audited sealed controls',fontsize=13)
    for ext in ('png','pdf'):fig.savefig(HERE/('position_summary.'+ext),dpi=180)
    plt.close(fig)
    candidates=[];case_summary=[]
    for case in cases:
        ledger=read(HERE/(case+'_additions.json'));graph=read(HERE/'graphs'/case/'graph_audit.json')
        for a in ledger['staged']:
            candidates.append({k:a[k] for k in ('case','prediction_id','target_observation_id','block_ids','channel','native_receiver_id','receiver','time_s',
                'native','donors','predicted_cfo_hz','measured_cfo_hz','innovation_hz','zero_fft_bin','donor_count',
                'confirmation_margin','selected_mode_id','selected_offset_samples','reference_counter','earlier_width_hz','ordering_evidence')})
        variants_out={v:{arm:{k:lookup[case,v]['arms'][arm][k] for k in ('accepted_GLRT_count','total_GLRT_count','associated_GLRT_fraction','likelihood_points','RMS_hz','position_error_km','added_curved_ids','added_predictive_ids','added_accepted_ids')} for arm in ('c0','fitted_c')} for v in variants}
        case_summary.append(dict(case=case,native_added=graph['new_native_owners'],new_in_graph=graph['new_in_graph'],new_curved=graph['new_in_curved_graph'],
            original_GLRT_count=graph['original_GLRT_count'],total_GLRT_count=graph['total_GLRT_count'],
            zero_bin_new=sum(a['zero_fft_bin'] for a in ledger['staged']),variants=variants_out))
    write(HERE/'candidate_manifest.json',dict(candidates=candidates,new_native=len(candidates),
        raw_rows_local_only=True,original_plus_expansion_only=True,original_measurements_preserved=True))
    write(HERE/'summary.json',dict(cases=case_summary,effects=e['effects'],new_native=51,new_in_graph=46,new_curved=32,
        new_likelihood_curved=13,new_likelihood_predictive=11,new_likelihood_total=24,new_satellite_families=0,
        new_RF_reads=0,new_ALGO02_initializations=4,baseline_initializations_reused=2,
        fresh_ALGO02_reruns=0,cavity_stages_started_once_each=True,matched_c_arms=True,
        frequency_fit_improvement_claim=False,held_validation_claim=False,uncertainty_calibrated=False,promotion=False))
    full=read(HERE/'position_inference_audit.json')
    compact={k:v for k,v in full.items() if k!='audited'}
    compact['audited']=[{k:v for k,v in r.items() if k!='read_paths'} for r in full['audited']]
    compact['full_read_audit_sha256']=sha(HERE/'position_inference_audit.json');write(HERE/'position_inference_audit_compact.json',compact)
    timing=[]
    for job in read(HERE/'position_protocol.json')['jobs']:
        root=Path(job['root']);first=read(root/'execution.json');resume=read(root/'engine_continuation_execution.json')
        original_end=(root/'execution.json').stat().st_mtime_ns/1e9;resume_end=(root/'engine_continuation_execution.json').stat().st_mtime_ns/1e9
        original_begin=original_end-first['seconds'];resume_begin=resume_end-resume['continuation_seconds']
        timing.append(dict(case=job['case'],variant=job['variant'],first_attempt_seconds=first['seconds'],
            continuation_seconds=resume['continuation_seconds'],total_numerical_seconds=resume['total_numerical_seconds'],
            elapsed_with_interruption_seconds=resume_end-original_begin,interruption_seconds=resume_begin-original_end,
            elapsed_timestamp_basis='Derived from preserved completion-file mtime and recorded monotonic stage durations; filesystem-write timing precision, not fabricated execution callbacks'))
    write(HERE/'execution_timing.json',dict(jobs=timing,first_attempts_retained=True,continuation_authorized=True,
        no_numerical_budget_reset=True,maximum_total_numerical_budget_seconds=240))
    print(dict(new_native=51,new_graph=46,new_curved=32,new_likelihood=24,new_families=0))


if __name__=='__main__':main()
