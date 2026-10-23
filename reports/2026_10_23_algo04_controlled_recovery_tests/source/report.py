"""Evaluation-only GPS, tables and scientific plots for bounded controls."""
from pathlib import Path
import csv
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experiment import OUT,SOURCE,CASES,ARMS
from run_algo01_ds23_sample import read,write,sha
from report_algo02_ds23 import position_error


def table(name,rows):
    with (OUT/'tables'/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def main():
    for name in ['tables','figures','evidence']:(OUT/name).mkdir(exist_ok=True)
    for stage in ['norescue','rank','native','physical']:
        assert read(OUT/(stage+'_execution.json'))['all_passed'],stage
    rows=[];graph=[];physical=[];trialrows=[];scores=[];inputs={}
    for case in CASES:
        f=read(SOURCE/'raw'/case/'result.json');n=read(OUT/'raw'/case/'native.json');r=read(OUT/'raw'/case/'ranking.json')
        no=read(OUT/'raw'/case/'norescue.json')
        records={'reference':f['reference'],'rejected_candidate':f['candidate'],**n['methods']}
        for name,d in records.items():
            for arm,s in d['arms'].items():
                cv=d['coverage'][arm]
                rows.append(dict(case=case,method=name,arm=arm,error_km=position_error(s['endpoint_latlon']),
                    associated=cv['associated'],all_GLRT=cv.get('total_GLRT',f['reference']['coverage'][arm]['total_GLRT']),
                    associated_percent=cv['percent'],RMS_hz=s['RMS_hz'],
                    native_accepted=d.get('native_accepted'),parent=d.get('parent_name')))
        for name,d in {'rejected_graph':dict(parent_arms=f['graph']['arms'],parent_coverage=f['graph']['coverage']),**n['methods']}.items():
            for arm,s in d['parent_arms'].items():
                graph.append(dict(case=case,method=name,arm=arm,error_km=position_error(s['endpoint_latlon']),
                    associated_percent=d['parent_coverage'][arm]['percent'],RMS_hz=s['RMS_hz']))
        for t in no['trials']:
            for arm,s in t['arms'].items():
                trialrows.append(dict(case=case,trial=t['name'],kind=t['kind'],arm=arm,
                    norads=';'.join(str(a['norad']) for a in t['additions']),added_curved_points=t['added_curved_points'],
                    ordinary_extra_budget_used=t['ordinary_extra_budget_used'],paired_valid=t['paired_valid'],
                    parent_IDs_preserved=t['parent_IDs_preserved'],error_km=position_error(s['endpoint_latlon']),
                    RMS_hz=s['RMS_hz'],minimum_gate_slack=s['minimum_gate_slack']))
        for candidate in r['results']:
            for arm in ARMS:
                scores.append(dict(case=case,branch=candidate['name'],arm=arm,score=candidate['scores'][arm],
                    improvement_vs_reference=r['results'][0]['scores'][arm]-candidate['scores'][arm],
                    penalty=r['threshold'],qualified=candidate['qualified'],selected=candidate['name']==r['selected']['name']))
        if case in CASES[:3]:
            d=read(OUT/'raw'/case/'physical.json')
            for name,v in d['results'].items():
                for arm,s in v['arms'].items():
                    physical.append(dict(case=case,method=name,arm=arm,error_km=position_error(s['endpoint_latlon']),RMS_hz=s['RMS_hz'],
                        event_time_s=d['proposal']['time_s'],event_amplitude_hz=s['event_amplitudes_hz'][0] if s['event_amplitudes_hz'] else None,
                        paired_valid=v['paired_valid'],witness_supported=v['witness_supported'],parent_IDs_preserved=v['parent_IDs_preserved'],
                        same_mask_gain=v['same_mask_gain'][arm],search_penalty=d['search_penalty'],
                        eligible_for_further_validation=v['eligible_for_further_validation']))
        for path in sorted((OUT/'raw'/case).glob('*.json')):inputs[str(path.relative_to(OUT))]=sha(path)
    table('positions.csv',rows);table('graph_stage.csv',graph);table('ordinary_trials.csv',trialrows)
    table('common_family_scores.csv',scores);table('physical_trials.csv',physical)
    summary=[]
    for arm in ARMS:
        for method in ['reference','rejected_candidate','norescue','common_family_rank']:
            values=[r for r in rows if r['arm']==arm and r['method']==method]
            errors=np.array([r['error_km'] for r in values]);total=sum(r['all_GLRT'] for r in values);associated=sum(r['associated'] for r in values)
            summary.append(dict(arm=arm,method=method,scans=len(values),mean_error_km=float(errors.mean()),median_error_km=float(np.median(errors)),
                worst_error_km=float(errors.max()),associated=associated,all_GLRT=total,associated_percent=100*associated/total))
    table('five_case_summary.csv',summary)
    methods=['reference','rejected_candidate','norescue','common_family_rank']
    labels=['Published reference','Rejected candidate','Ordinary fit + native','Family ranking + native']
    colors=['#555555','#d95f02','#1b9e77','#7570b3']
    for metric,ylabel,filename in [('error_km','Position error (km)','position_errors.png'),('associated_percent','Original GLRT associated (%)','association.png')]:
        fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
        for ax,arm in zip(axes,ARMS):
            for k,(method,label,color) in enumerate(zip(methods,labels,colors)):
                values=[next(r[metric] for r in rows if r['case']==case and r['arm']==arm and r['method']==method) for case in CASES]
                ax.bar(np.arange(5)+(k-1.5)*.2,values,.19,color=color,label=label)
            ax.set_xticks(range(5),[c[-4:]+(' (control)' if c in CASES[3:] else '') for c in CASES],rotation=20)
            ax.set_ylabel(ylabel);ax.set_title(arm);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
            if metric=='associated_percent':ax.set_ylim(0,100)
        fig.suptitle('Five predeclared development scans — native stage rerun from each selected parent')
        fig.savefig(OUT/'figures'/filename,dpi=165);plt.close(fig)
    diag=read(OUT/'evidence/gate_diagnostics.json')
    gate_rows=[]
    for r in diag:
        key,value=r['worst_slacks'][0]
        gate_rows.append(dict(case=r['case'],method=r['method'],arm=r['arm'],worst_gate=key,slack=value,statistic_to_threshold=1-value))
    table('worst_gates.csv',gate_rows)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    for ax,arm in zip(axes,ARMS):
        for k,(method,label,color) in enumerate([('ordinary_initial','Ordinary initial','#377eb8'),('constrained_graph','Constrained rescue','#d95f02')]):
            values=[next(r['statistic_to_threshold'] for r in gate_rows if r['case']==case and r['arm']==arm and r['method']==method) for case in CASES[:3]]
            ax.bar(np.arange(3)+(k-.5)*.3,values,.28,label=label,color=color)
            for i,v in enumerate(values):ax.text(i+(k-.5)*.3,v+.01,f'{v:.3f}',ha='center',fontsize=9)
        ax.axhline(1,c='crimson',ls='--',label='Rejection threshold');ax.set_ylim(0,1.25)
        ax.set_xticks(range(3),[c[-4:] for c in CASES[:3]]);ax.set_ylabel('Worst normalized gate statistic');ax.set_title(arm);ax.legend(fontsize=8)
    fig.suptitle('Residual constraints become active at the returned position')
    fig.savefig(OUT/'figures/gate_boundaries.png',dpi=165);plt.close(fig)
    residuals=read(OUT/'evidence/curve_residuals.json')
    fig,axes=plt.subplots(3,2,figsize=(13,10),layout='constrained')
    for row,case in enumerate(CASES[:3]):
        data=read(OUT/'raw'/case/'physical.json');key=data['proposal']['component'];track=next(t for t in data['tracks'] if t['component']==key)
        times=np.array(track['times']);values=np.array(track['native_CFO_hz'])
        axes[row,0].scatter(times,values/1000,s=18,c='black',label='Original GLRT CFO')
        for method,label,color in [('ordinary_initial','Ordinary fit','#377eb8'),('constrained_graph','Constrained rescue','#d95f02'),('receiver_step','Receiver-step diagnostic','#4daf4a')]:
            r=next(r for r in residuals if r['case']==case and r['component']==key and r['method']==method and r['arm']=='fitted_c')
            assert np.array_equal(times,r['times'])
            axes[row,0].plot(times,(values-np.array(r['residual_hz']))/1000,c=color,label=label)
            axes[row,1].plot(times,r['residual_hz'],'.-',c=color,label=label,ms=3)
        for ax in axes[row]:
            ax.axvline(data['proposal']['time_s'],c='gray',ls=':');ax.set_title(key.split('-RF')[0]+' / '+str(track['norad']));ax.set_xlabel('Time (s)');ax.grid(alpha=.2)
        axes[row,0].set_ylabel('Native CFO (kHz)');axes[row,1].set_ylabel('Conditional residual (Hz)');axes[row,1].axhline(0,c='black',lw=.7)
    axes[0,0].legend(fontsize=7);axes[0,1].legend(fontsize=7)
    fig.suptitle('Same recovered points and satellite identity · fitted c\nLeft: full orbit-plus-radio prediction; right: residual; dotted line: proposed step')
    fig.savefig(OUT/'figures/native_cfo_residuals.png',dpi=165);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    for ax,arm in zip(axes,ARMS):
        for k,(method,label) in enumerate([('null','No added step'),('receiver_step','Receiver step'),('family_step','Satellite-family step')]):
            vv=[next(r for r in physical if r['case']==case and r['arm']==arm and r['method']==method) for case in CASES[:3]]
            bars=ax.bar(np.arange(3)+(k-1)*.24,[r['error_km'] for r in vv],.23,label=label)
            for bar,r in zip(bars,vv):
                if not r['paired_valid']:bar.set_hatch('///');bar.set_alpha(.5)
        ax.set_xticks(range(3),[c[-4:] for c in CASES[:3]]);ax.set_title(arm);ax.set_ylabel('Position error (km)');ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Physical-step controls on identical selected graph masks\nHatched = failed paired gates; none qualifies for adoption')
    fig.savefig(OUT/'figures/physical_controls.png',dpi=165);plt.close(fig)
    shape=read(OUT/'evidence/native_shape.json')['rows']
    shape_rows=[dict(case=r['case'],component=r['component'],norad=r['norad'],points=r['points'],persisted_pieces=r['persisted_pieces'],
        polynomial_degree=r['whole']['degree'],polynomial_RMS_hz=r['whole']['RMS_hz'],max_standardized_residual=r['whole']['max_standardized_residual'],
        last_point_standardized_residual=r['last_point_standardized_residual'],split_BIC_gain=r['split_BIC_gain'],
        proposed_split_s=r['best_split']['time_s']) for r in shape]
    table('native_shape.csv',shape_rows)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
    ax.barh(range(len(shape_rows)),[r['split_BIC_gain'] for r in shape_rows],color=['#d95f02' if r['split_BIC_gain']>0 else '#377eb8' for r in shape_rows])
    ax.set_yticks(range(len(shape_rows)),[r['component'].split('-RF')[0].replace('DS23-','') for r in shape_rows])
    ax.axvline(0,c='black',lw=.8);ax.set_xlabel('Whole polynomial BIC − best two-piece BIC (including split search penalty)')
    ax.set_title('Satellite-free native curve diagnostic · no points removed\nAlias-unwrapped CFO, degrees 1–4; two-piece model permits a discontinuity')
    ax.grid(axis='x',alpha=.2);fig.savefig(OUT/'figures/native_shape.png',dpi=165);plt.close(fig)
    write(OUT/'evidence/report_receipt.json',dict(source_sha256=sha(Path(__file__)),raw_result_sha256=inputs,
        full_candidate_reference_sha256={case:sha(SOURCE/'raw'/case/'result.json') for case in CASES},
        GPS_only_in_report=True,full_DS23_not_rerun=True,new_ALGO_promoted=False,
        summary=summary,all_physical_models_fail_adoption=not any(r['eligible_for_further_validation'] for r in physical)))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
