"""Publish exact-orbit audits without promoting provisional associations."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import identity_consensus
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    sources={};evidence={}
    def load(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        value=read(path);evidence[str(path)]=compact_evidence(value);return value
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):
        fig.savefig(out/'figures'/name,dpi=150);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv'
    sources[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger}
    q=s/'systematic-annotation-v1';attempt=q/'attempt-24';load(attempt/'protocol.json');batch=[]
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];terminal=load(attempt/(tid+'-terminal.json'))
        row=dict(scan=j['label'],track_id=tid,status='execution_'+terminal['status'],norad=None)
        if terminal['status']=='complete':
            path=q/tid/'result.json';r=load(path);load(path.parent/'protocol.json')
            vote=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            row.update(status=vote['status'],norad=vote['norad'])
            byid[tid].update(state=vote['status'],norad=vote['norad'],minimum_margin=vote.get('minimum_margin'),
                annotation_source=str(path),partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),
                distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=row['status']
        batch.append(row)
    auditroot=s/'retrospective-annotation-phase-audit-v1';annotations={};checks={};executions=[]
    for attempt in sorted(auditroot.glob('attempt-*')):
        protocol=load(attempt/'protocol.json')
        for job in protocol['jobs']:
            tid=job['track_id'];terminal=load(attempt/(tid+'-terminal.json'))
            executions.append(dict(attempt=attempt.name,track_id=tid,scan=job['label'],status=terminal['status']))
            if terminal['status']!='complete':continue
            path=attempt/(tid+'.json');r=load(path)
            annotations[tid]=(r['annotations'][0],path);checks[tid]=r['rows']
    recheck=auditroot/'domain-recheck-v1.json';r=load(recheck)
    for a in r['annotations']:
        tid=a['track_id'];annotations[tid]=(a,recheck);checks[tid]=[x for x in r['rows'] if x['track_id']==tid]
    assert len(annotations)==64
    phase=[]
    for tid,(a,path) in annotations.items():
        row=byid[tid];row.update(phase_prior_state=row['state'],phase_audit_source=str(path),state=a['corrected']['status'])
        winning=[r for r in checks[tid] if r['nominated']]
        phase.append(dict(scan=a['scan'],track_id=tid,norad=a['original']['norad'],points=int(row['points']),
            original=a['original']['status'],corrected=a['corrected']['status'],
            maximum_phase_gap_s=max(r['maximum_unclipped_phase_change_s'] for r in winning),
            minimum_phase_s=min(r['phase_s'] for r in winning),maximum_phase_s=max(r['phase_s'] for r in winning),
            maximum_exact_difference_hz=max(r['maximum_linearization_error_hz'] for r in winning),source=str(path)))
    csvout('annotation_audit.csv',phase);csvout('annotation_executions.csv',executions);csvout('annotation_batch.csv',batch)
    csvout('winning_fold_checks.csv',[{k:v for k,v in r.items() if not isinstance(v,(list,dict))} for rr in checks.values() for r in rr if r['nominated']])
    graph=[];endpoint_rows=[]
    for path in sorted(s.glob('graph-inclusion-batch*-v1/qualified_owner_phase_audit_v1.json')):
        audit=load(path);protocol=load(path.parent/'protocol.json')
        for tid in sorted({r['track_id'] for r in audit['rows']}):
            rows=[r for r in audit['rows'] if r['track_id']==tid];root=path.parent/tid
            target=load(root/'target_0.json');control=load(root/'control.json');load(root/'protocol.json')
            assert len(rows)==4 and target['paired_valid']
            valid=all(r['all_pass'] and r['phase_converged'] and not r['incumbent_ownership_changes'] and not r['control_ownership_changes'] for r in rows)
            targets=[r for r in rows if r['role']=='target_0'];j=next(j for j in protocol['jobs'] if j['track_id']==tid)
            record=dict(scan=j['label'],track_id=tid,norad=target['target_entries'][0]['norad'],verified=valid,
                added_c0=target['arms']['c0']['added_points'],added_fitted_c=target['arms']['fitted_c']['added_points'],
                exact_max_difference_hz=max(r['maximum_linearization_difference_hz'] for r in targets),
                phase_gap_s=max(r['phase_reference_check']['phase_change_s'] for r in targets),
                minimum_exact_slack=min(r['minimum_slack'] for r in targets),source=str(path))
            for arm in ('c0','fitted_c'):
                record['control_error_'+arm+'_km']=error(control['arms'][arm]);record['target_error_'+arm+'_km']=error(target['arms'][arm])
            graph.append(record)
            byid[tid].update(research_inclusion='RF_candidate_exact_owner_verified' if valid else 'rejected_exact_phase_audit',inclusion_source=str(path))
            endpoint_rows.extend({k:v for k,v in r.items() if k not in ('owners','family_witnesses','all_gate_slacks')} for r in rows)
    assert len(graph)==12 and len({r['track_id'] for r in graph})==12
    csvout('graph_candidates.csv',graph);csvout('graph_endpoints.csv',endpoint_rows)
    experiments=[];domain={};tid='a8d10bb82a0c0a14ea77'
    load(s/'graph-phase-reference-domain-v1/protocol.json')
    for limit in (15,30):
        root=s/'graph-phase-reference-domain-v1'/f'reference{limit}';load(root/'protocol.json');load(root/(tid+'-terminal.json'))
        load(root/tid/'protocol.json');audit=load(root/'exact_phase_audit.json')
        for role in ('control','target_0'):
            result=load(root/tid/(role+'.json'))
            for arm,v in result['arms'].items():
                a=next(r for r in audit['rows'] if r['role']==role and r['arm']==arm)
                target=v['targets'][0] if role=='target_0' else None
                witness=next((r for r in a['family_witnesses'] if target and r['component']==target['component']),None)
                row=dict(reference_limit_s=limit,role=role,arm=arm,phase_converged=a['phase_converged'],gates_pass=a['all_pass'],
                    qualified=result['paired_valid'],error_km=error(v),objective=v['negative_twice_elbo'],
                    minimum_exact_slack=a['minimum_slack'],phase_gap_s=a['phase_reference_check']['phase_change_s'],
                    exact_difference_hz=a['maximum_linearization_difference_hz'],
                    target_exact_RMS_hz=witness['RMS_hz'] if witness else None,
                    failures='; '.join(k for k,value in a['all_gate_slacks'].items() if value<0),lost=v['lost_points'])
                if target:row.update({'tangent_'+k:v for k,v in target['gate']['conditional_residual_gate']['diagnostics'].items()})
                experiments.append(row);domain[limit,role,arm]=(v,a)
    csvout('reference_domain_trials.csv',experiments);csvout('annotation_ledger.csv',ledger)
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    ordered=sorted(phase,key=lambda r:r['maximum_phase_gap_s'])
    for i,r in enumerate(ordered):
        bad=r['corrected']!=r['original'];color='#d55e00' if bad else '#0072b2'
        axs[0].scatter(i,max(r['maximum_phase_gap_s'],1e-12),color=color,s=22)
        axs[1].scatter(i,max(r['maximum_exact_difference_hz'],1e-12),color=color,s=22)
        if bad:axs[1].annotate(r['scan'],(i,r['maximum_exact_difference_hz']),xytext=(-8,8),textcoords='offset points',ha='right',fontsize=8)
    axs[0].axhline(.01,color='black',ls='--',label='Convergence limit');axs[0].legend()
    for ax in axs:ax.set(xlabel='Audit case, sorted by phase gap',yscale='log');ax.grid(alpha=.2)
    axs[0].set_ylabel('Largest unclipped phase gap (s)');axs[1].set_ylabel('Largest target tangent/exact difference (Hz)')
    axs[1].set_ylim(top=axs[1].get_ylim()[1]*4)
    fig.suptitle('64 selected historical annotations: 62 retain conditional support, 2 downgraded\nMaximum over winning fold/arm fits; this is not a random population sample')
    save(fig,'annotation_phase_audit.png')
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,arm in enumerate(('c0','fitted_c')):
        for limit,color in ((15,'#d55e00'),(30,'#0072b2')):
            v,a=domain[limit,'target_0',arm];t=v['targets'][0];w=next(r for r in a['family_witnesses'] if r['component']==t['component'])
            times=np.array(t['times_s']);y=np.array(t['CFO_hz']);res=np.array(w['residual_hz'])
            if limit==15:axs[0,col].scatter(times,y/1000,s=16,color='black',label='GLRT')
            axs[0,col].plot(times,(y-res)/1000,color=color,label=f'Exact orbit + nuisance, limit {limit}s')
            axs[1,col].plot(times,res,'.-',color=color,label=f'Exact residual, limit {limit}s',ms=4)
            if limit==15:axs[1,col].plot(times,t['residual_hz'],':',color='#888888',label='Old tangent residual')
        for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=7)
        axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Residual (Hz)');axs[1,col].axhline(0,color='black',lw=.7)
    fig.suptitle('AUTO-99d8b775, RX2 CH4: numerical repair removes approximation error\nBoth wider-reference fits still fail the residual slope gate; no accepted recovery')
    save(fig,'reference_domain_residuals.png')
    fig,axs=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for arm,offset,color in (('c0',-.17,'#0072b2'),('fitted_c',.17,'#d55e00')):
        rows=[next(r for r in experiments if r['arm']==arm and r['reference_limit_s']==limit and r['role']==role)
            for limit,role in ((15,'control'),(15,'target_0'),(30,'target_0'))]
        axs[0].bar(np.arange(3)+offset,[r['error_km'] for r in rows],.3,color=color,label=arm)
        axs[1].bar(np.arange(2)+offset,[r['target_exact_RMS_hz'] for r in rows[1:]],.3,color=color,label=arm)
    axs[0].set_xticks(range(3),['Matched control','15s target\nREJECTED','30s target\nREJECTED']);axs[0].set_ylabel('Evaluation position error (km)')
    axs[1].set_xticks(range(2),['15s target\nREJECTED','30s target\nREJECTED']);axs[1].set_ylabel('Target exact-orbit residual RMS (Hz)')
    for ax in axs:ax.grid(axis='y',alpha=.2);ax.legend()
    fig.suptitle('Better frequency prediction does not certify better localization\nBoth controls agree across reference limits; GPS used only in this evaluation plot')
    save(fig,'frequency_vs_position.png')
    summary=dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),
        annotation_batch=dict(Counter(r['status'] for r in batch)),new_audits=len(phase),new_downgrades=sum(r['original']!=r['corrected'] for r in phase),
        cumulative_audited=sum(bool(r['phase_audit_source']) for r in ledger),cumulative_downgrades=sum(bool(r['phase_audit_source']) and r['phase_prior_state']!=r['state'] for r in ledger),
        graph_candidates=len(graph),graph_verified=sum(r['verified'] for r in graph),production_changed=False,retained_policy_changed=False)
    write(out/'summary.json',summary)
    bad=[r for r in phase if r['original']!=r['corrected']]
    report=f'''# Retrospective phase audit and bounded exact-orbit repair

The wider audit confirms a specific numerical failure, not a general reason to discard large curves. Of **64 additional historical annotations, 62 retain conditional support and two are downgraded**. Of **12 previously paired-passing graph inclusion candidates in the audited batch directories, 10 pass the new exact-orbit/convergence/ownership checks and two fail**. One rejected candidate was identified in the previous report; AUTO-bed86935 is newly rejected here. No production or retained cohort policy changes.

This continues the [training-confidence and phase audit](../2026_10_30_training_confidence_phase_audit/README.md). Earlier provisional success for AUTO-bed86935, track `792ab1d56e2d2054283a`, is superseded by this exact-orbit failure. It must not be counted as a verified recovery.

## Why some apparent associations were misleading

The old research loop fitted a satellite phase beyond ±15 seconds, clipped the next linearization reference to that boundary, and measured change after clipping. Successive clipped values could agree even though the orbit approximation remained wrong. Convergence now requires the **unclipped fitted phase to agree with its reference within 0.01 seconds**. Exact orbit replay independently checks the selected family. These tests validate numerical consistency; they do not establish satellite identity by themselves.

The retrospective audit prioritizes previously paired-passing graph candidates, then larger DS24 curves, then other supported identities. This selected sample cannot estimate the population-wide defect rate. All stored candidate/fold/arm endpoints are replayed; the old observations, random scan-wide 12-second blocks with 2-second guards, priors, and candidate lists are preserved. No optimization or GPS-based ranking is performed. Scores are not reranked after removing a failed candidate; only convergence metadata is corrected before recomputing identity consensus.

{table(bad,['scan','norad','points','minimum_phase_s','maximum_phase_s','maximum_phase_gap_s','maximum_exact_difference_hz','corrected'])}

![Annotation audit](figures/annotation_phase_audit.png)

Including the previous two audited annotations, **{summary['cumulative_audited']} original annotations have now been audited, with {summary['cumulative_downgrades']} downgrades**. Conditional support still depends on the frozen graph and searched competitors. The exact mean replay does not recompute an exact marginalized posterior or certify unseen competitors.

The first pass of attempt 2 completed 31 cases and failed execution on DS24-0095: a losing NORAD 57949 hypothesis requested orbit times outside the cached bank. The follow-up records four out-of-domain competitor fold/arm endpoints explicitly and leaves DS24-0095's supported winner unchanged. It does not extrapolate the orbit, suppress the failed receipt, or turn an unavailable exact comparison into a passing result. All 64 selected cases now have completed diagnostic results; original execution outcomes remain in [the execution table](annotation_executions.csv).

## Previously passing graph additions

These are all paired-passing candidates found in the examined `graph-inclusion-batch*-v1` directories, not every historical manual prototype. Each candidate has four replayed endpoints: control/addition × c=0/fitted-c. Qualification below requires exact residual gates, unclipped phase convergence, unchanged incumbent satellite owners, and unchanged control owners. Exact replacement is for the nominated family; other families retain their original model and are checked for phase convergence and existing gates.

{table(graph,['scan','norad','added_c0','added_fitted_c','verified','phase_gap_s','exact_max_difference_hz','minimum_exact_slack'])}

Added counts in failed rows are **proposed**, not accepted. The ten verified candidates are research candidates, not ten newly deployed recoveries. Position errors for matched controls and targets are preserved separately in [graph_candidates.csv](graph_candidates.csv).

AUTO-bed86935 is RX2 CH8, 52 points at 160.9–208.7 seconds, tested against NORAD 57641 in a 10 MS/s recording. AUTO-99d8b775 is RX2 CH4, 46 points at 153.2–193.6 seconds, tested against NORAD 100486 in a 2.5 MS/s recording. Their distinct satellites and opposite phase directions show the clipping problem is not specific to one satellite. This is not a controlled sample-rate comparison.

## Can a wider numerical reference repair the rejected curve?

For AUTO-99d8b775, matched 15-second and 30-second reference-limit variants start from the same respective control/addition endpoints. Each receives five additional phase-refresh rounds with 40 constrained optimizer steps. Observations, satellite IDs, aliases, noise, weights, physical priors, search region, and budgets stay matched across both c arms. This changes the numerical linearization reference limit, **not the satellite phase prior**. The target phase prior remains mean −1.222 seconds and sigma 4.403 seconds.

Every updated reference is checked against the existing orbit bank, including a 0.05-second derivative margin and the predictive geometry. No new TLE, future TLE, bank extension, or extrapolation is used. The target observations occupy only part of the scan, so a phase beyond 15 seconds can remain inside the cached time support.

{table(experiments,['reference_limit_s','role','arm','phase_converged','gates_pass','target_exact_RMS_hz','error_km'])}

The 30-second reference converges: the remaining raw phase gaps are about 0.000005/0.000053 seconds and tangent/exact differences are below 0.000002 Hz. Exact target RMS improves from about 234/224 Hz to **70.59/68.34 Hz**. However, slope z-scores remain **3.702/3.299**, exceeding the original limit of 3. The step scores **3.531/3.511 pass their limit of 4**; slope is the remaining failed gate in both arms. Both targets remain rejected, with zero incumbent point losses. This bounded optimizer result does not prove that no feasible fit exists.

![Exact orbit and residuals](figures/reference_domain_residuals.png)

![Frequency and position](figures/frequency_vs_position.png)

The apparently improved ~0.88/0.96 km positions under the clipped approximation were invalid fits. Numerically consistent target fits instead have errors **5.267/5.561 km**, compared with matched controls **1.166/1.165 km**. Better exact frequency fit does not establish better localization. These rejected endpoints are diagnostics, not algorithm performance claims. GPS at 37.849061591561885, −122.48574968092912 is used only to compute these errors; fitting remains in the original 25 × 25 km region centered at 37.906, −122.545.

## Inventory and next experiments

The new bounded annotation batch completes 31 of 32 jobs, with one timeout. It brings the inventory to **{summary['annotations_completed']} completed annotations / {summary['inventory_total']} entries**. Batch states: `{summary['annotation_batch']}`. This measures annotation coverage, not accepted GLRT association percentage. The cumulative [ledger](annotation_ledger.csv) preserves original annotation sources, corrected audit sources and prior states; native overlapping branches remain a separate inventory.

The next work should separate three questions: whether a curve has a stable satellite identity; whether its exact orbit and receiver model explain the full residual; and whether adding it improves independent position information. Finish the retrospective consistency checks, then revisit affected hypotheses with valid references and the same causal competitors. For residual structure that survives the repair, compare shared receiver corrections against shared satellite corrections using independent curves and randomized block prediction. Do not relax slope gates merely to retain points. Neither lower training RMS nor a favorable GPS error is an acceptance rule.

## Reproduction and evidence

`run_annotation_phase_audit.py` records selection and supervises bounded replays. `audit_annotation_phase.py` reconstructs original training endpoints and records out-of-domain alternatives. `audit_graph_inclusion_owners.py` verifies objectives, memberships, ownership and selected-family exact residuals. `probe_graph_phase_domain.py` launches the two matched reference limits; re-audit both with `--include-unqualified` so rejected endpoints remain visible. `report_phase_reference_retrospective.py` builds this report from immutable receipts.

Component tests cover clipped false convergence, valid orbit support, batch propagation of reference limits, deterministic audit selection, grouped prediction, confidence learning, and held-family comparisons. [Summary](summary.json), [all endpoint metrics](reference_domain_trials.csv), [winning-fold checks](winning_fold_checks.csv), [source hashes](sources.json), and [compact numerical evidence](evidence.json.gz) accompany the figures. Repeated observation-ID arrays and optimizer histories are hashed in the compact archive; their immutable source paths and file hashes are retained. No ALGO promotion or dataset-wide position gain is claimed.
'''
    (out/'README.md').write_text(report)
    for path in [Path(__file__),*map(Path,('tools/phase_reference_checks.py','tools/audit_annotation_phase.py','tools/audit_graph_inclusion_owners.py',
            'tools/refine_graph_inclusion_constraints.py','tools/run_annotation_phase_audit.py','tools/probe_graph_phase_domain.py'))]:
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
