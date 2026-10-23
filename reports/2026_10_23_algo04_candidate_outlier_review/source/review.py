"""Retrospective saved-result review; no fitting or inference selection."""
from pathlib import Path
import csv
import hashlib
import json
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parents[1]
SOURCE = Path('/srv/bulk/leo/research/algo04-candidate-20261023')
FOCUS = ['0081', '0326', '0344', '0390', '0404', '0256', '0299', '0071', '0272', '0041']


def position_error(latlon):
    # Exact published great-circle metric; evaluation only.
    reference = (37.849061591561885, -122.48574968092912)
    a,b = map(math.radians,(latlon[0],reference[0]))
    dlon = math.radians(latlon[1]-reference[1])
    h = math.sin((a-b)/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 12742*math.asin(math.sqrt(min(1.,max(0.,h))))


def write_csv(name, rows):
    with (OUT/'tables'/name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def gate_rows(case, arm, stage, parent_components):
    rows = []
    for t in stage['arms'][arm]['gates']['tracks']:
        gate = t.get('conditional_residual_gate', {})
        diag = gate.get('diagnostics', {})
        n = t['points']
        if not diag or not n:
            continue
        usage = dict(mean=diag['mean_z']/3, slope=diag['slope_z']/3,
                     quadratic=diag['quadratic_bic_gain']/10,
                     step=diag['maximum_step_z']/4,
                     lag1=abs(diag['lag1_acf'])/(4/math.sqrt(n)),
                     rms=gate['rms_hz']/450)
        dominant = max(usage, key=usage.get)
        rows.append(dict(case=case, arm=arm, component=t['component'],
                         norad=t['norad'], points=n,
                         added=t['component'] not in parent_components,
                         conditional_RMS_hz=gate['rms_hz'], lag1_acf=diag['lag1_acf'],
                         step_z=diag['maximum_step_z'], slope_z=diag['slope_z'],
                         closest_conditional_gate=dominant, max_gate_usage=usage[dominant],
                         **{'usage_'+k:v for k,v in usage.items()}))
    return rows


def main():
    for folder in ['figures','tables','evidence']:
        (OUT/folder).mkdir(parents=True, exist_ok=True)
    positions = list(csv.DictReader((SOURCE/'tables/positions.csv').open()))
    index = {(r['case'],r['method'],r['arm']):r for r in positions}
    for r in positions:
        assert abs(position_error([float(r['latitude']),float(r['longitude'])])-float(r['error_km']))<1e-8
    cases = sorted({r['case'] for r in positions})
    assert len(cases)==410 and len(positions)==2460
    rows, gates, additions, receipts, trials = [], [], [], [], []
    additional_inputs = {}
    for case in cases:
        file = SOURCE/'raw'/case/'result.json'
        raw = file.read_bytes(); result = json.loads(raw)
        receipts.append(dict(case=case,sha256=hashlib.sha256(raw).hexdigest()))
        ref,graph,final = [result[k] for k in ('reference','graph','candidate')]
        selected = graph.get('selected') or {}
        refined = bool(selected.get('constrained_refinement_attempted',False))
        changed = bool(result.get('graph_changed',False))
        for arm in ['c0','fitted_c']:
            r,g,c = [index[case,m,arm] for m in ('reference','graph','candidate')]
            error = [float(x['error_km']) for x in (r,g,c)]
            slack = graph['arms'][arm].get('minimum_gate_slack')
            rows.append(dict(case=case,arm=arm,recording_format=r['recording_format'],
                reference_error_km=error[0],graph_error_km=error[1],candidate_error_km=error[2],
                graph_delta_error_km=error[1]-error[0],native_delta_error_km=error[2]-error[1],
                total_delta_error_km=error[2]-error[0],graph_changed=changed,
                selected_constrained_refinement=refined,
                saved_minimum_gate_slack=slack,
                near_margin=bool(refined and slack is not None and slack<=.010101),
                added_graph_points=int(g['associated_points'])-int(r['associated_points']),
                added_native_points=int(c['associated_points'])-int(g['associated_points']),
                graph_RMS_delta_hz=float(g['RMS_hz'])-float(r['RMS_hz']),
                native_RMS_delta_hz=float(c['RMS_hz'])-float(g['RMS_hz']),
                reference_associated_percent=float(r['associated_percent']),
                candidate_associated_percent=float(c['associated_percent'])))
            if case[-4:] in FOCUS:
                old={t['component'] for t in ref['arms'][arm]['gates']['tracks']}
                gates.extend(gate_rows(case,arm,graph,old))
        if case[-4:] in FOCUS:
            trial_file = SOURCE/'raw'/case/'single_curve_reentry'/f'{case}_positions.json'
            if trial_file.exists():
                additional_inputs[str(trial_file)] = hashlib.sha256(trial_file.read_bytes()).hexdigest()
                for i,t in enumerate(json.loads(trial_file.read_text())['trials']):
                    for arm,s in t['arms'].items():
                        trials.append(dict(case=case,trial=i,arm=arm,
                            components=';'.join(a['component'] for a in t['additions']),
                            norads=';'.join(str(a['norad']) for a in t['additions']),
                            added_curved_points=t['added_curved_points'],
                            paired_valid=t['paired_valid'],constrained_refinement=t['constrained_refinement_attempted'],
                            error_km=position_error(s['endpoint_latlon']),RMS_hz=s['RMS_hz']))
            nomination = SOURCE/'raw'/case/'single_curve_reentry'/f'{case}_nominations.json'
            if nomination.exists():
                additional_inputs[str(nomination)] = hashlib.sha256(nomination.read_bytes()).hexdigest()
            targets = json.loads(nomination.read_text())['targets'] if nomination.exists() else []
            by_name = {t['target']['component']:t for t in targets}
            for a in selected.get('additions',[]):
                t = by_name.get(a['component']); target=t['target'] if t else {}
                choices = sorted([v for v in t['candidates'] if v['qualified']],key=lambda v:v['score']) if t else []
                chosen=next((v for v in choices if v['norad']==a['norad']),None)
                alternatives=[v for v in choices if v['norad']!=a['norad']]
                additions.append(dict(case=case,component=a['component'],norad=a['norad'],
                    points=target.get('points'),start_s=target.get('start_s'),end_s=target.get('end_s'),
                    persisted_pieces=target.get('pieces'),
                    nominee_score=chosen['score'] if chosen else None,
                    best_other_norad=alternatives[0]['norad'] if alternatives else None,
                    conditional_nomination_score_margin=alternatives[0]['score']-chosen['score'] if chosen and alternatives else None,
                    nomination_elevation_deg=chosen['minimum_elevation_deg'] if chosen else None))
    write_csv('stage_changes.csv',rows);write_csv('focus_conditional_gates.csv',gates);write_csv('recovered_sources.csv',additions)
    write_csv('saved_graph_trials.csv',trials)
    groups=[]
    for arm in ['c0','fitted_c']:
        population=[r for r in rows if r['arm']==arm]
        for label,predicate in [('no graph change',lambda r:not r['graph_changed']),
                                ('graph without constrained refinement',lambda r:r['graph_changed'] and not r['selected_constrained_refinement']),
                                ('graph with constrained refinement',lambda r:r['graph_changed'] and r['selected_constrained_refinement']),
                                ('refined and near saved margin',lambda r:r['near_margin'])]:
            group=[r for r in population if predicate(r)]
            groups.append(dict(arm=arm,group=label,scans=len(group),
                graph_regressions_above_half_km=sum(r['graph_delta_error_km']>.5 for r in group),
                graph_improvements_above_half_km=sum(r['graph_delta_error_km']<-.5 for r in group),
                mean_graph_delta_km=float(np.mean([r['graph_delta_error_km'] for r in group])) if group else None))
    write_csv('refinement_groups.csv',groups)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    chosen=['0081','0326','0344','0390','0404','0256','0299','0071']
    colors=['#444444','#d95f02','#7570b3']
    for ax,arm in zip(axes,['c0','fitted_c']):
        x=np.arange(len(chosen))
        for i,m in enumerate(['reference','graph','candidate']):
            y=[float(index['DS23-'+case,m,arm]['error_km']) for case in chosen]
            ax.bar(x+(i-1)*.25,y,.24,color=colors[i],label=m)
        ax.set_xticks(x,chosen,rotation=35);ax.set_ylabel('Position error (km)');ax.set_title(arm)
        ax.grid(axis='y',alpha=.2);ax.legend()
    fig.suptitle('Worst candidate errors and diagnostic regressions — saved results, no new fits')
    fig.savefig(OUT/'figures/worst_stage_errors.png',dpi=170);plt.close(fig)
    selected_gates=[g for g in gates if g['arm']=='fitted_c' and g['added'] and g['case'][-4:] in ['0344','0256','0404','0299','0390']]
    names=['slope','quadratic','step','lag1','rms']
    values=np.array([[max(0,g['usage_'+k]) for k in names] for g in selected_gates])
    fig,ax=plt.subplots(figsize=(10,5),layout='constrained')
    im=ax.imshow(values,vmin=0,vmax=1,cmap='YlOrRd',aspect='auto')
    labels=[g['component'].split('-RF')[0].replace('DS23-','')+' / '+str(g['norad']) for g in selected_gates]
    ax.set_yticks(range(len(labels)),labels);ax.set_xticks(range(len(names)),names)
    for i in range(len(labels)):
        for j in range(len(names)):ax.text(j,i,f'{values[i,j]:.2f}',ha='center',va='center')
    fig.colorbar(im,ax=ax,label='Statistic / rejection threshold (1 = gate boundary)')
    ax.set_title('Recovered curves at the graph endpoint, fitted c\nConditional residual diagnostics; negative quadratic gains displayed as zero')
    fig.savefig(OUT/'figures/recovered_gate_usage.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    for ax,arm in zip(axes,['c0','fitted_c']):
        for refined,color in [(False,'#1b9e77'),(True,'#d95f02')]:
            group=[r for r in rows if r['arm']==arm and r['graph_changed'] and r['selected_constrained_refinement']==refined]
            ax.scatter([r['added_graph_points'] for r in group],[r['graph_delta_error_km'] for r in group],s=20,alpha=.65,color=color,label=('Constrained refinement' if refined else 'No constrained refinement'))
        ax.axhline(0,color='k',lw=.8);ax.set_xlabel('Added graph associations');ax.set_ylabel('Graph − reference error (km)');ax.set_title(arm);ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Selected graph changes across all DS23 — descriptive, not a causal ablation')
    fig.savefig(OUT/'figures/graph_refinement_population.png',dpi=170);plt.close(fig)
    pairs={'0256':['RX2-CH1-T001','RX1-CH7-T000'],
           '0404':['RX1-CH3-T000','RX1-CH3-T004'],
           '0299':['RX1-CH8-T001','RX1-CH3-T001']}
    expected_labels={'0256':{'57606','58181'},'0404':{'69835','66470'},'0299':{'66940'}}
    fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
    for col,(short,components) in enumerate(pairs.items()):
        case='DS23-'+short
        for row,arm in enumerate(['c0','fitted_c']):
            chosen=[]
            for wanted in ([components[0]],[components[1]],components):
                found=[t for t in trials if t['case']==case and t['arm']==arm
                    and set(t['norads'].split(';'))<=expected_labels[short]
                    and set(x.split('-RF')[0].split(case+'-')[1] for x in t['components'].split(';'))==set(wanted)]
                assert len(found)==1
                chosen.append(found[0])
            assert abs(chosen[2]['error_km']-float(index[case,'graph',arm]['error_km']))<1e-8
            ax=axes[row,col];vals=[float(index[case,'reference',arm]['error_km'])]+[t['error_km'] for t in chosen]
            bars=ax.bar(range(4),vals,color=['#555555','#377eb8','#377eb8','#d95f02'])
            for k,t in enumerate(chosen,1):
                if not t['paired_valid']:bars[k].set_hatch('///');bars[k].set_alpha(.45)
            ax.set_xticks(range(4),['Reference','A','B','A+B']);ax.set_ylim(0,8.5);ax.grid(axis='y',alpha=.2)
            for k,v in enumerate(vals):ax.text(k,v+.12,f'{v:.2f}',ha='center',fontsize=8)
            ax.set_title(f'{case} · {arm}');ax.set_ylabel('Position error (km)')
            if row==1:ax.set_xlabel('A: '+components[0]+'\nB: '+components[1],fontsize=8)
    fig.suptitle('Saved whole-curve trials: accepting more points can worsen position\nHatching = failed paired qualification; bars are diagnostic results, not GPS-selected repairs')
    fig.savefig(OUT/'figures/saved_single_vs_joint_trials.png',dpi=170);plt.close(fig)
    audit=dict(cases=len(cases),position_rows=len(positions),no_new_fits=True,
               no_GPS_in_inference=True,posthoc_ranking_uses_published_GPS_errors=True,
               gate_thresholds_source='tools/ds23_feasible_position.py',
               near_margin_definition='saved minimum slack <=0.010101, selected constrained refinement only; descriptive label',
               published_position_errors_verified=2460,
               saved_joint_trials_match_graph_endpoints=True,
               positions_csv_sha256=hashlib.sha256((SOURCE/'tables/positions.csv').read_bytes()).hexdigest(),
               source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),results=receipts,
               additional_input_sha256=additional_inputs)
    (OUT/'evidence/review_receipt.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(groups,indent=2),flush=True)


if __name__=='__main__':main()
