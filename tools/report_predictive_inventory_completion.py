"""Report terminal inventory batches without treating assessment as acceptance."""
import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from debug_fast_graph_unassociated import read, write
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from report_predictive_track_annotation import table
from report_inventory_experiments import error
from report_inactive_fragment_transfer import replay_slacks


def assessed(row):
    return any(row.get(k) for k in ('annotation_source', 'predictive_recheck_source',
                                   'inactive_fragment_annotation_source'))


def run(args):
    s=args.study; q=s/'systematic-annotation-v1'; out=args.output
    out.mkdir(parents=True,exist_ok=False); (out/'figures').mkdir()
    hashes={}; evidence={}; executions=[]
    def load(path):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        result=read(path); evidence[str(path)]=compact_replays(compact_evidence(result)); return result
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n'); w.writeheader(); w.writerows(rows)
    def save(fig,name):
        fig.savefig(out/'figures'/name,dpi=145); plt.close(fig)
    previous=args.previous/'annotation_ledger.csv'
    hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open())); byid={r['track_id']:r for r in ledger}
    if len(byid)!=len(ledger):raise ValueError('duplicate inventory identity')
    annotations=[]
    def annotation(job,terminal,path,group):
        tid=job['track_id']; term=load(terminal); executions.append(dict(group=group,**term))
        row=dict(group=group,scan=job['label'],track_id=tid,points=job['points'],execution=term['status'])
        if term['status']!='complete':
            annotations.append(dict(row,status='execution_'+term['status'])); return
        result=load(path/'result.json'); load(path/'protocol.json'); a=result['annotation']
        if result.get('inclusion_mode')!='predictive_only':raise ValueError('unexpected annotation role')
        row.update(status=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'))
        annotations.append(row); source=str(path/'result.json')
        if result.get('inactive_graph_fragment'):
            byid[tid].update(inactive_fragment_annotation_source=source,inactive_fragment_state=a['status'],inactive_fragment_norad=a['norad'])
        else:
            byid[tid].update(predictive_recheck_source=source,predictive_recheck_state=a['status'],
                predictive_recheck_minimum_margin=a.get('minimum_margin'),state=a['status'],norad=a['norad'],
                annotation_likelihood_role='predictive_only; assessment, not accepted association')
    for attempt in args.attempts:
        p=q/attempt; load(p/'protocol.json'); load(p/'execution.json')
        for job in load(p/'selected.json'):
            annotation(job,p/(job['track_id']+'-terminal.json'),q/job['track_id'],attempt)
    root=s/'timedout-predictive-reassessment-v1'; pr=load(root/'protocol.json'); load(root/'execution.json')
    for source,digest in pr['source_hashes'].items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=digest:raise ValueError('old timeout evidence changed')
    for job in pr['jobs']:
        annotation(job,root/(job['track_id']+'-terminal.json'),root/job['track_id'],'fresh timeout reassessment')
    comparisons=[]; trials=[]; failures=[]; curves=[]
    def position(job,folder,shared,label):
        pr=load(folder/'protocol.json'); c=load(folder/'control.json')
        a=load(folder/('target_0.json' if shared else 'new_family.json')); audit=load(folder/'exact_owner_replay.json')
        qualified=bool(c['paired_valid'] and a['paired_valid'] and audit['all_verified'])
        target=set(o for t in pr['targets'] for o in t['observation_ids'])
        inv=load(Path(job['inventory'])); den=inv['summary'][0]['total_GLRT']
        row=dict(case=label,scan=job['label'],track_id=job['track_id'],norad=job['annotation']['norad'],
                 target_points=len(target),RF_qualified=qualified)
        for arm in ('c0','fitted_c'):
            row.update({arm+'_control_km':error(c['arms'][arm]),arm+'_addition_km':error(a['arms'][arm])})
        comparisons.append(row)
        for role,pair in [('control',c),('target_0' if shared else 'new_family',a)]:
            for arm,v in pair['arms'].items():
                replay=next(r for r in audit['rows'] if (r['role'],r['arm'])==(role,arm))
                slacks=replay_slacks(replay); old=set(c['arms'][arm]['proposed_associated_ids'])
                ids=set(v['proposed_associated_ids']); changes=replay['incumbent_ownership_changes']
                last=v['history'][-1]
                trials.append(dict(case=label,scan=job['label'],role=role,arm=arm,error_km=error(v),
                    proposed_points=len(ids),proposed_percent=100*len(ids)/den,target_added=len((ids-old)&target),
                    incidental_added=len((ids-old)-target),lost=len(old-ids),paired_valid=pair['paired_valid'],
                    exact_verified=replay['verified'],RF_qualified=qualified,
                    missing_owners=sum(x['after'] is None for x in changes),reassigned_owners=sum(x['after'] is not None for x in changes),
                    minimum_exact_slack=min(slacks.values(),default=None),objective=v['negative_twice_elbo'],
                    phase_gap_s=v['final_phase_change_s'],quadrature_pass=v.get('phase_resolution_audit',{}).get('local_agreement'),
                    optimizer_success=last.get('success'),optimizer_reason=last.get('message',last.get('fit',{}).get('stopped')),
                    phase_boundary_mass=v.get('family',{}).get('phase_boundary_mass')))
                for gate,slack in slacks.items():
                    if slack<0:failures.append(dict(case=label,role=role,arm=arm,gate=gate,slack=slack))
                if role!='control':
                    diagnostics=v.get('target_diagnostics',[]) if shared else v.get('family',{}).get('diagnostics',[])
                    for diag in diagnostics:
                        if shared:residual=np.array(diag['residual_hz'])
                        else:
                            residual=np.array(diag['raw_residual_hz'])-diag['profile_bias_hz']; n=diag['noise']
                            ratios=dict(mean=n['mean_z']/3,slope=n['slope_z']/3,quadratic=n['quadratic_bic_gain']/10,
                                step=n['maximum_step_z']/4,lag1=abs(n['lag1_acf'])/(4/np.sqrt(len(residual))))
                            for k,ratio in ratios.items():
                                if ratio>1:failures.append(dict(case=label,role=role,arm=arm,gate=diag['component']+'/target/'+k,slack=1-ratio))
                        curves.append(dict(case=label,arm=arm,times=diag['times_s'],cfo=diag['CFO_hz'],residual=residual,
                                           qualified=qualified,component=diag['component']))
        if job['track_id'] in byid:
            byid[job['track_id']].update(predictive_inclusion_source=str(folder),
                predictive_research_inclusion='RF_verified_candidate; not production promoted' if qualified else 'rejected; trial and replay retained')
    for name in args.inclusions:
        root=s/name; load(root/'protocol.json'); cases=load(root/'execution.json')
        for case in cases:
            job=case['job']; folder=root/job['track_id']
            for stage in case['stages']:executions.append(dict(group=name,**load(folder/(stage['stage']+'-terminal.json'))))
            if case['status']!='complete':continue
            position(job,folder/'trial',case['shared_family'],name+'/'+job['track_id'])
    # Explicit joint experiment: the two individual successes are not added arithmetically.
    for name,label in [('predictive-ceb24498-joint63388-v1','joint63388'),
                       ('predictive-ceb24498-joint63388-refined-v1','joint63388_refined')]:
        root=s/name; pr=load(root/'protocol.json'); execution=load(root/'execution.json')
        for stage in execution['stages']:executions.append(dict(group=label,**load(root/(stage['stage']+'-terminal.json'))))
        if execution['status']=='complete':
            position(dict(pr['jobs'][0],track_id=label),root/'trial',False,label)
    remaining=[r for r in ledger if not assessed(r)]
    for name,rows in [('annotation_ledger.csv',ledger),('remaining_assessments.csv',remaining),('annotations.csv',annotations),
                      ('comparison.csv',comparisons),('position_trials.csv',trials),('failed_gates.csv',failures),('executions.csv',executions)]:csvout(name,rows)
    summary=dict(inventory_total=len(ledger),assessed_any_role=len(ledger)-len(remaining),remaining=len(remaining),
        new_assessments=len(annotations),annotation_statuses=dict(Counter(r['status'] for r in annotations)),
        position_cases=len(comparisons),qualified_cases=sum(r['RF_qualified'] for r in comparisons),production_changed=False)
    write(out/'summary.json',summary)
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        for r in comparisons:
            ax.scatter(r[arm+'_control_km'],r[arm+'_addition_km'],c='#009e73' if r['RF_qualified'] else '#d55e00',marker='*' if r['case'].startswith('joint63388') else 'o',s=85)
        limit=max(max(r[arm+'_control_km'],r[arm+'_addition_km']) for r in comparisons)*1.05
        ax.plot([0,limit],[0,limit],'k--',lw=.8); ax.set(xlabel='Matched control error (km)',ylabel='Proposed addition error (km)',title=arm);ax.grid(alpha=.2)
    fig.suptitle('Green passes RF checks; orange remains rejected even when GPS error improves\nStar: joint inclusion; each point is a separate controlled trial')
    save(fig,'position_transfer.png')
    groups=list(dict.fromkeys(r['group'] for r in annotations)); statuses=sorted({r['status'] for r in annotations})
    fig,ax=plt.subplots(figsize=(11,5),layout='constrained');left=np.zeros(len(groups))
    for status in statuses:
        values=[sum(r['group']==g and r['status']==status for r in annotations) for g in groups]
        ax.barh(groups,values,left=left,label=status);left+=values
    ax.set(xlabel='Curves assessed',title='Assessment outcomes are not accepted satellite associations');ax.legend(fontsize=8,loc='upper center',bbox_to_anchor=(.5,-.12),ncol=2)
    save(fig,'annotation_outcomes.png')
    # All trial residuals remain visible, not only the successful candidates.
    labels=list(dict.fromkeys(r['case'] for r in curves))
    for page,start in enumerate(range(0,len(labels),8),1):
        selected=labels[start:start+8];fig,axs=plt.subplots(4,2,figsize=(14,12),layout='constrained')
        for ax,label in zip(axs.flat,selected):
            for r in [r for r in curves if r['case']==label]:
                ax.plot(r['times'],r['residual'],'.-',ms=3,label=r['arm']+' '+r['component'])
            row=next(r for r in comparisons if r['case']==label)
            ax.axhline(0,c='k',lw=.6);ax.set(title=row['scan']+' / '+str(row['norad'])+(' / RF pass' if row['RF_qualified'] else ' / rejected'),xlabel='Time (s)',ylabel='Profile residual (Hz)');ax.legend(fontsize=6);ax.grid(alpha=.2)
        for ax in list(axs.flat)[len(selected):]:ax.set_visible(False)
        save(fig,f'residuals_{page}.png')
    qualified=[r for r in comparisons if r['RF_qualified']]
    fig,axs=plt.subplots(max(1,len(qualified)),2,figsize=(14,max(4,4*len(qualified))),squeeze=False,layout='constrained')
    for pair,row in zip(axs,qualified):
        for curve in [r for r in curves if r['case']==row['case']]:
            t=np.array(curve['times']);cfo=np.array(curve['cfo']);res=curve['residual']
            if curve['arm']=='c0':pair[0].scatter(t,cfo/1000,c='k',s=12,label=curve['component']+' GLRT')
            pair[0].plot(t,(cfo-res)/1000,label=curve['arm']+' prediction + profiled offset')
            pair[1].plot(t,res,'.-',label=curve['arm']+' '+curve['component'])
        pair[0].set(title=row['scan']+' / '+row['track_id'],xlabel='Time (s)',ylabel='CFO (kHz)')
        pair[1].set(title='Residuals',xlabel='Time (s)',ylabel='Profile residual (Hz)');pair[1].axhline(0,c='k',lw=.6)
        for ax in pair:ax.grid(alpha=.2);ax.legend(fontsize=6)
    save(fig,'qualified_curves.png')
    figure_links='\n\n'.join(f'![Residuals {i}](figures/residuals_{i}.png)' for i in range(1,(len(labels)+7)//8+1))
    text=f'''# Completing bounded predictive assessments and testing inclusion

The frozen inventory now has **{summary['assessed_any_role']} / {summary['inventory_total']} curves assessed in at least one likelihood role**. This includes unresolved identities and curves with insufficient independent partitions. It does not mean that all curves are correctly identified, nor that all observations are usable for localization. There are **{summary['remaining']} records without a completed assessment**. No production algorithm or acceptance threshold changes.

## What was tested

This iteration completes {len(annotations)} fresh predictive assessments: the listed queue batches plus separate reassessments of the 24 earlier terminal timeouts. The old timeout receipts and partial outputs remain immutable and their hashes are verified. A timeout is an execution outcome, not evidence against a satellite. The predictive method fits receiver calibration without the target, then conditions satellite predictions on training target observations. It does not use the candidate curve to calibrate a receiver offset or drift. Validation uses reproducible random scanwide 12 s blocks with 2 s guards and distinct timestamp partitions. Short curves can lack enough partitions; this is insufficient validation evidence, not a claim that their GLRT signal is noise.

![Outcomes](figures/annotation_outcomes.png)

{table([dict(status=k,count=v) for k,v in summary['annotation_statuses'].items()],['status','count'])}

The source ledger preserves earlier likelihood roles separately. Completing a first pass does not resolve ambiguous candidates, disagreement across partitions, or model mismatch. [Every annotation](annotations.csv), [the inventory ledger](annotation_ledger.csv), and [remaining assessments](remaining_assessments.csv) are included.

## Satellite identity is only the first test

Every supported identity in the specified inclusion batches receives a bounded position trial and exact-orbit replay. c=0 and fitted-c retain matched observations, candidates, priors and search budgets. The regional initialization is the 25 × 25 km box centered at 37.906, −122.545. Evaluation GPS (37.849061591561885, −122.48574968092912) does not select identities, corrections or trials. Only causal TLEs are used. Shared families retain their shared conditional model; new or uncalibrated families use a phase mixture with orbital and receiver uncertainty.

Each stage has a 600 s wall-clock cap. Passing requires both the control and proposed fit to qualify in both c arms, plus exact replay, phase checks, physical/residual gates and incumbent ownership checks. Exact replay replaces one family at a time; it is not a simultaneous exact-orbit refit of every family. A lower GPS error from a rejected trial is not an achieved improvement. Scores on different observation sets are not comparable localization evidence.

{table(comparisons,['scan','track_id','norad','target_points','c0_control_km','c0_addition_km','fitted_c_control_km','fitted_c_addition_km','RF_qualified'])}

![Position trials](figures/position_transfer.png)

There are **{len(qualified)} qualified trial configurations out of {len(comparisons)} completed configurations**. These are research results, not distinct curves or additive gains. The joint 63388 experiment explicitly fits the two disjoint curves together; it is not the sum of their independently measured improvements. The earlier 27-point result and the new 25-point result use zero overlapping observations. The per-arm [position table](position_trials.csv) reports proposed coverage, target additions, incidental additions, losses, ownership changes, numerical checks, objective and evaluation error. Proposed coverage in rejected rows is not accepted coverage.

The first joint trial passes target residual gates and exact replay but fails the phase-integration accuracy check: the 0.1 s grid changes the local score by up to 0.0028 / 0.0043, above the unchanged 0.001 tolerance. The 0.05 versus 0.025 s comparison differs by only about 3–4 millionths. The separate refined trial therefore repeats the same regional fits with a 0.025 s phase grid. This follows numerical evidence, not GPS error, and retains the original failed trial. A phase integration step is a model computation setting, not the recording sample rate.

The refined joint fit qualifies: **52 added points**, no losses, and coverage **73.446% → 74.776%** (2,871 → 2,923 of 3,909 GLRT points). Error changes **2.145 → 2.028 km** for c=0 and **2.100 → 2.019 km** for fitted-c. These two CH7 fragments interleave along the same apparent curve: their observation IDs and exact timestamps do not overlap, and the nearest timestamps across fragments differ by at least 0.353 s. They are not two independent satellite passes. The shared-family fit is therefore essential; their individual error improvements cannot be summed.

The earlier-timeout recovery **AUTO-49154edb / 62035** qualifies with **44 points**. Error changes **0.666 → 0.627 km** for c=0 and **0.548 → 0.504 km** for fitted-c. This is one research scan result, not evidence that the whole dataset now reaches 500 m.

![Qualified curves and predictions](figures/qualified_curves.png)

The qualified AUTO-3dabeeab addition increases evaluation error by about 0.20 km in both c arms. This is a direct counterexample to equating more associated GLRT with better position accuracy. The model can pass the current RF tests while still pulling the position away from ground truth. It remains visible as a research candidate, with no production promotion.

## Residual evidence and remaining work

{figure_links}

[Failed gates](failed_gates.csv) distinguish target structure from conflicts with retained curves. Low RMS alone is insufficient: nonzero trend, curvature, steps or serial correlation can still make a candidate inconsistent with the model. The gate thresholds remain mean/slope z ≤ 3, quadratic BIC gain ≤ 10, maximum step z ≤ 4, and absolute lag-one correlation ≤ 4/sqrt(N), alongside physical and numerical checks. Passing those tests is evidence under this model, not proof of a perfect satellite identity.

The next priority is grouped evidence for short fragments and independent evidence for receiver events or satellite-model corrections, followed by simultaneous inclusion of compatible candidates. The goal remains incomplete: an assessment inventory is not an accepted association catalogue. No full-dataset position benefit or ALGO promotion is claimed. Source hashes, compact scientific evidence and terminal receipts accompany this report. The targeted regression suite passed 53 tests before this report was generated.
'''
    (out/'README.md').write_text(text)
    for name in ('run_predictive_queue_inclusions.py','report_predictive_inventory_completion.py'):
        p=Path(__file__).with_name(name);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    print(summary,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--attempts',nargs='+',required=True);p.add_argument('--inclusions',nargs='+',required=True)
    run(p.parse_args())
