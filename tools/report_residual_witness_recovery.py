"""Publish receiver/family witnesses, repaired annotations and recovery transfer."""
import argparse,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_cross_family_prediction import held_metrics
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    evidence={};hashes={}
    def load(p):
        hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=compact_evidence(r);return r
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv';hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};batch=[]
    q=s/'systematic-annotation-v1';attempt=q/'attempt-25';load(attempt/'protocol.json')
    for j in load(attempt/'selected.json'):
        tid=j['track_id'];term=load(attempt/(tid+'-terminal.json'));row=dict(scan=j['label'],track_id=tid,status='execution_'+term['status'])
        if term['status']=='complete':
            path=q/tid/'result.json';r=load(path);load(path.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            row.update(status=a['status'],norad=a['norad']);byid[tid].update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),
                annotation_source=str(path),partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:byid[tid]['state']=row['status']
        batch.append(row)
    audits=[];audit_checks=[]
    for number in (3,4):
        root=s/'retrospective-annotation-phase-audit-v1'/f'attempt-{number}'
        for j in load(root/'protocol.json')['jobs']:
            tid=j['track_id'];terminal=load(root/(tid+'-terminal.json'));assert terminal['status']=='complete'
            path=root/(tid+'.json');r=load(path);a=r['annotations'][0];winning=[x for x in r['rows'] if x['nominated']]
            row=byid[tid];row.update(phase_prior_state=row['state'],state=a['corrected']['status'],phase_audit_source=str(path))
            audits.append(dict(scan=j['label'],track_id=tid,original=a['original']['status'],corrected=a['corrected']['status'],norad=a['original']['norad'],
                phase_gap_s=max(x['maximum_unclipped_phase_change_s'] for x in winning),target_exact_difference_hz=max(x['maximum_linearization_error_hz'] for x in winning)))
            audit_checks.extend(winning)
    refit=s/'annotation-phase-reference-v08-v1';repair=load(refit/'exact_phase_audit.json');load(refit/'protocol.json');new=load(refit/'result.json')
    vote=repair['annotations'][0]['corrected'];assert vote['status']=='conditionally_supported_identity'
    tid=new['track_id'];row=byid[tid]
    row.update(annotation_prior_source=row['annotation_source'],annotation_source=str(refit/'result.json'),
        phase_initial_audit_source=row['phase_audit_source'],phase_audit_source=str(refit/'exact_phase_audit.json'),
        phase_repair_source=str(refit),phase_repair_from_state=row['state'],state=vote['status'],minimum_margin=vote['minimum_margin'])
    csvout('annotation_batch.csv',batch);csvout('phase_audit.csv',audits)
    before=[r for r in audit_checks if r['track_id']==tid];after=[r for r in repair['rows'] if r['nominated']]
    after=[next(r for r in after if (r['seed'],r['arm'])==(b['seed'],b['arm'])) for b in before]
    fig,axs=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for label,rr,offset,color in [('Original',before,-.17,'#d55e00'),('Repaired',after,.17,'#0072b2')]:
        axs[0].bar(np.arange(6)+offset,[r['maximum_unclipped_phase_change_s'] for r in rr],.3,color=color,label=label)
        axs[1].bar(np.arange(6)+offset,[r['maximum_linearization_error_hz'] for r in rr],.3,color=color,label=label)
    for ax in axs:
        ax.set_xticks(range(6),[str(r['seed'])+'\n'+r['arm'] for r in before],fontsize=7);ax.set_yscale('log');ax.legend();ax.grid(axis='y',alpha=.2)
    axs[0].axhline(.01,color='black',ls='--');axs[0].set_ylabel('Maximum phase/reference gap across families (s)')
    axs[1].set_ylabel('Target orbit approximation difference (Hz)')
    fig.suptitle('V08: repair background family 52311; preserve target 66102\nThe target approximation was already accurate; the whole fit was not converged.')
    save(fig,'v08_background_phase_repair.png')
    # All full-data candidates, including failures, remain visible.
    root=s/'graph-inclusion-batch24-v1';protocol=load(root/'protocol.json');exact=load(root/'qualified_owner_phase_audit_v1.json')
    failures=load(root/'gate_audit.json');trials=[];verified=[];gallery=[]
    for j in protocol['jobs']:
        tid=j['track_id'];folder=root/tid;term=load(root/(tid+'-terminal.json'));assert term['status']=='complete'
        control=load(folder/'control.json');target=load(folder/'target_0.json');pr=load(folder/'protocol.json');inv=load(Path(j['inventory']))
        aa=[r for r in exact['rows'] if r['track_id']==tid]
        passed=len(aa)==4 and all(r['all_pass'] and r['phase_converged'] and not r['incumbent_ownership_changes'] and not r['control_ownership_changes'] for r in aa)
        if passed:verified.append(tid)
        byid[tid].update(research_inclusion='RF_candidate_exact_owner_verified' if passed else 'rejected_original_model',inclusion_source=str(folder))
        for arm,v in target['arms'].items():
            c=control['arms'][arm];total=next(r['total_GLRT'] for r in inv['summary'] if r['arm']==arm)
            trials.append(dict(scan=j['label'],track_id=tid,arm=arm,norad=pr['targets'][0]['norad'],target_points=pr['targets'][0]['points'],
                RF_verified=passed,raw_pair_pass=target['paired_valid'],control_pair_pass=control['paired_valid'],
                added=v['added_points'],lost=v['lost_points'],lost_control=len(set(c['proposed_associated_ids'])-set(v['proposed_associated_ids'])),
                control_percent=100*len(c['proposed_associated_ids'])/total,target_percent=100*len(v['proposed_associated_ids'])/total,
                control_error_km=error(c),target_error_km=error(v),phase_gap_s=v['final_phase_change_s'],sample_rate_hz=inv['job']['sample_rate_hz']))
        fig,axs=plt.subplots(2,2,figsize=(11,6),layout='constrained')
        for col,(arm,v) in enumerate(target['arms'].items()):
            t=v['targets'][0];tt=t['times_s'];res=np.asarray(t['residual_hz']);y=np.asarray(t['CFO_hz'])
            axs[0,col].scatter(tt,y/1000,s=9,color='black',label='GLRT');axs[0,col].plot(tt,(y-res)/1000,label='Fitted orbit + nuisance')
            axs[1,col].plot(tt,res,'.-',ms=3);axs[1,col].axhline(0,color='black',lw=.7)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Time (s)',ylabel='Model residual (Hz)')
            for ax in axs[:,col]:ax.grid(alpha=.2)
        axs[0,0].legend(fontsize=8);fig.suptitle(f"{j['label']} / NORAD {pr['targets'][0]['norad']} — "+('RF verified candidate' if passed else 'REJECTED'))
        name=tid+'.png';save(fig,name);gallery.append(f"### {j['label']}\n\n![CFO and residual](figures/{name})\n")
    csvout('graph_trials.csv',trials);(out/'graph_gallery.md').write_text('# All 18 graph trials\n\nTangent-model plots; the four qualifying candidates additionally pass exact replay. Rejected fits are not accepted evidence.\n\n'+'\n'.join(gallery))
    rejection_rows=[dict(scan=r['scan'],track_id=r['track_id'],arm=r['arm'],component=v['component'],target=v.get('target',False),failures='; '.join(v['failures']))
        for r in failures['results'] for v in r['rows']+r['linear_rows'] if v['failures']]
    csvout('graph_rejections.csv',rejection_rows)
    # Descriptive simultaneous-curve evidence, with no GPS or residual fitting.
    witnesses=[];witness_gallery=[]
    for short in ('99d8b775','bed86935','f0255747'):
        r=load(s/f'residual-witness-{short}-v1.json');fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
        for col,v in enumerate(r['results']):
            target=v['target'];t=np.asarray(target['times_s']);res=np.asarray(target['residual_hz']);local=v['witnesses']
            axs[0,col].plot(t,res-res.mean(),'o-',color='black',ms=3,label='Target (mean removed)')
            for w in local:
                if w['component']==target['component'] or w['receiver']!=target['receiver']:continue
                tt=np.array(w['times_s']);rr=np.array(w['residual_hz']);axs[0,col].plot(tt,rr-rr.mean(),'.-',ms=2,alpha=.7,label=f"{w['norad']} CH{w['channel']}")
            for pos,w in enumerate(local):
                color='black' if w['component']==target['component'] else '#0072b2' if w['receiver']==target['receiver'] else '#999999'
                axs[1,col].scatter(w['slope_hz_s'],pos,color=color)
            axs[1,col].set_yticks(range(len(local)),[f"{w['norad']} RX{w['receiver']} CH{w['channel']}" for w in local],fontsize=8)
            axs[1,col].axvline(0,color='black',lw=.5);axs[1,col].invert_yaxis();axs[1,col].set_xlabel('Descriptive residual slope (Hz/s)')
            axs[0,col].set(title=v['arm'],ylabel='Centered exact residual (Hz)',xlabel='Time (s)');axs[0,col].legend(fontsize=7)
            for ax in axs[:,col]:ax.grid(alpha=.2)
            for g in v['groups']:
                witnesses.append(dict(scan=r['job']['label'],arm=v['arm'],group=g['group'],scaling=g['scaling'],
                    distinct_families=g['distinct_families'],witness_curves=g['witness_curves'],
                    target_rate_hz_s=g['needed_target_rate_hz_s'],predicted_rate_hz_s=g['predicted_target_rate_hz_s'],
                    target_RMS_hz=v['target_rate']['RMS_hz'],target_affine_lower_bound_hz=v['target_rate']['affine_RMS_hz'],RMS_after_descriptive_correction_hz=g['target_RMS_after_hz']))
        fig.suptitle(r['job']['label']+' — simultaneous residual witnesses\nBlack: target; blue slope markers: same receiver; gray: other receiver. Full-fit diagnostics, not held validation.')
        name='witness_'+short+'.png';save(fig,name);witness_gallery.append(f"![{r['job']['label']} witnesses](figures/{name})")
    csvout('residual_witnesses.csv',witnesses)
    domain=[]
    for limit in (15,30):
        root=s/'graph-phase-reference-domain-bed86935-v1'/f'reference{limit}';load(root/'protocol.json');a=load(root/'exact_phase_audit.json')
        tid='792ab1d56e2d2054283a';load(root/(tid+'-terminal.json'));load(root/tid/'protocol.json')
        for role in ('control','target_0'):
            r=load(root/tid/(role+'.json'))
            for arm,v in r['arms'].items():
                exactrow=next(x for x in a['rows'] if x['role']==role and x['arm']==arm)
                domain.append(dict(reference_limit_s=limit,role=role,arm=arm,error_km=error(v),qualified=r['paired_valid'],
                    phase_gap_s=v['final_phase_change_s'],exact_difference_hz=exactrow['maximum_linearization_difference_hz'],
                    target_exact_RMS_hz=exactrow['family_witnesses'][0]['RMS_hz'] if role=='target_0' else None,
                    failures='; '.join(k for k,value in exactrow['all_gate_slacks'].items() if value<0)))
    csvout('ch8_phase_repair.csv',domain)
    # The first batch's terminal failures are technical, never scientific votes.
    executions=[];held=[];families=[]
    for version in (1,2):
        root=s/f'graph-inclusion-block-validation24-v{version}';pr=load(root/'protocol.json')
        for j in pr['jobs']:
            name=j['track_id']+'-'+str(j['seed']);terminal=load(root/(name+'-terminal.json'))
            executions.append(dict(version=version,scan=j['label'],seed=j['seed'],status=terminal['status']))
            if version==1 or terminal['status']!='complete':continue
            r=load(root/name/'result.json');load(root/name/'protocol.json')
            for arm in ('c0','fitted_c'):
                c=next(v for v in r['rows'] if v['role']=='control' and v['arm']==arm);t=next(v for v in r['rows'] if v['role']=='target' and v['arm']==arm)
                select=lambda x:not x['same_family'] and x['train_points']>=4
                metrics=held_metrics(c['held_predictions'],t['held_predictions'],select)
                held.append(dict(scan=j['label'],track_id=j['track_id'],seed=j['seed'],arm=arm,control_qualified=c['qualified'],target_qualified=t['qualified'],
                    control_error_km=error(c),target_error_km=error(t),**metrics))
                for norad in sorted({x['norad'] for x in c['held_predictions'] if select(x)}):
                    m=held_metrics(c['held_predictions'],t['held_predictions'],lambda x:select(x) and x['norad']==norad)
                    families.append(dict(scan=j['label'],seed=j['seed'],arm=arm,norad=norad,**m))
    csvout('validation_executions.csv',executions);csvout('held_comparison.csv',held);csvout('held_family_comparison.csv',families)
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained');qualified=[r for r in trials if r['RF_verified']]
    for arm,marker in (('c0','o'),('fitted_c','s')):
        rr=[r for r in qualified if r['arm']==arm]
        for row in rr:
            axs[0].plot([row['control_error_km'],row['target_error_km']],[row['scan'],row['scan']],color='#777777',lw=1)
            axs[0].scatter(row['control_error_km'],row['scan'],marker=marker,facecolors='none',edgecolors='#777777')
            axs[0].scatter(row['target_error_km'],row['scan'],marker=marker,color='#0072b2' if arm=='c0' else '#d55e00',label=arm if row is rr[0] else None)
    for r in held:
        passed=r['control_qualified'] and r['target_qualified'];axs[1].scatter(r['RMS_gain_hz'],r['control_error_km']-r['target_error_km'],
            marker='o' if passed else 'x',color='#0072b2' if r['scan']=='AUTO-e32d57a7' else '#d55e00' if r['scan']=='AUTO-49154edb' else '#999999',s=40)
    axs[0].set(xlabel='Full-data position error (km)',title='Four RF-verified candidates: hollow control → filled addition');axs[0].legend()
    axs[1].set(xlabel='Other-family held RMS improvement (Hz)',ylabel='Training-subset position-error improvement (km)',title='Held prediction vs position: circles pass training gates')
    from matplotlib.lines import Line2D
    axs[1].legend(handles=[Line2D([],[],marker='o',ls='',color=color,label=label) for color,label in
        [('#0072b2','AUTO-e32d57a7'),('#d55e00','AUTO-49154edb'),('#999999','Other two scans')]],title='Scan (both c arms)',fontsize=8,title_fontsize=8)
    axs[1].axvline(0,color='black',lw=.7);axs[1].axhline(0,color='black',lw=.7)
    for ax in axs:ax.grid(alpha=.2)
    save(fig,'prediction_and_position.png')
    csvout('annotation_ledger.csv',ledger)
    queue=load(q/'protocol.json');members={r['track_id']:r['engine_member'] for r in queue['rows']}
    ds24_pending=[r for r in ledger if 'DS24' in r['scopes'] and r['state']=='conditionally_supported_identity' and not r['phase_audit_source']]
    summary=dict(annotations_completed=sum(bool(r['annotation_source']) for r in ledger),inventory_total=len(ledger),
        annotation_batch=dict(Counter(r['status'] for r in batch)),new_audits=len(audits),initial_new_downgrades=sum(r['original']!=r['corrected'] for r in audits),
        repaired_annotations=1,cumulative_audited=sum(bool(r['phase_audit_source']) for r in ledger),
        unaudited_DS24_supported_curved=sum(members[r['track_id']] for r in ds24_pending),unaudited_DS24_supported_predictive=sum(not members[r['track_id']] for r in ds24_pending),
        inclusion_trials=len(protocol['jobs']),RF_verified_candidates=len(verified),completed_validation_fold_arms=len(held),
        passing_validation_fold_arms=sum(r['control_qualified'] and r['target_qualified'] for r in held),production_changed=False,retained_policy_changed=False)
    write(out/'summary.json',summary)
    report=f'''# Residual witnesses, annotation repair, and recovery transfer

This iteration separates numerical correctness, identity support, residual compatibility, and position usefulness. **Four of 18 new graph additions pass exact-orbit, convergence, and ownership checks**, but their position effects differ. A separate 120-point V08 annotation is restored after repairing a background satellite's phase reference. Two previously rejected curves still lack sufficient simultaneous evidence to justify an extra receiver or satellite correction.

This follows the [phase-reference retrospective](../2026_10_30_phase_reference_retrospective/README.md). All inference uses causal orbit inputs, matched c=0/fitted-c experiments, and the original 25 × 25 km region centered at 37.906, −122.545. GPS at 37.849061591561885, −122.48574968092912 is evaluation-only. Production and retained cohort policy remain unchanged.

## Does the residual error follow a receiver or a satellite?

The new diagnostic reconstructs saved full-fit endpoints, verifies their objectives, and replaces each active curved fragment's orbit mean with exact causal geometry. It examines other curves **inside the target's time interval**, requiring at least four points and a span of at least half the target span or five seconds, whichever is larger. Receiver groups exclude the entire target satellite family. Satellite groups exclude the target curve. Each other family gets one median vote, so repeated channels do not dominate. Both absolute-Hz and RF-proportional rate hypotheses are recorded.

These are descriptive residual comparisons after a full-data fit, not independent validation or formal confidence intervals. Position and nuisance parameters are already conditioned on the target. Free affine removal supplies only a diagnostic lower bound and cannot authorize an association.

{table([r for r in witnesses if r['scaling']=='hz' and r['group'] in ('same_receiver','same_receiver_band')],['scan','arm','group','distinct_families','witness_curves','target_rate_hz_s','predicted_rate_hz_s'])}

AUTO-99d8b775 needs approximately −3.54/−3.15 Hz/s removed from its RX2 CH4 residual, but three other families on RX2 give only −0.46/−0.70 Hz/s. The sole same-band witness has the opposite sign. There is no overlapping same-satellite witness. This does not support a simple common RX2 drift as the explanation. An apparent similar slope on the *other* receiver is not evidence for an RX2 correction.

AUTO-bed86935 needs about −4.24/−3.27 Hz/s on RX2 CH8. Its two same-receiver witnesses belong to **one** other satellite, and there are no qualifying same-receiver high-band or same-satellite witnesses. The model is underconstrained for distinguishing a high-band receiver error from a satellite error during this interval. The good AUTO-f0255747 candidate has a much smaller residual slope (~0.61/0.49 Hz/s) without needing an extra rate parameter; absence of witnesses alone is not a rejection criterion.

{chr(10).join(witness_gallery)}

## Repairing the CH8 numerical reference does not recover the track

AUTO-bed86935 repeats the matched reference-limit experiment on its 52-point RX2 CH8 curve, NORAD 57641. Both controls and additions receive five rounds of 40 constrained steps from corresponding saved endpoints. The 15/30-second limits change the numerical reference only: observations, IDs, alias, physical priors, noise, weights and budget are unchanged. Every updated reference, including derivative support, must stay inside the existing orbit bank.

{table(domain,['reference_limit_s','role','arm','qualified','phase_gap_s','target_exact_RMS_hz','error_km'])}

The wider reference eliminates the ~290 Hz approximation discrepancy. It leaves target RMS **56.7/46.5 Hz**, but slope and lag-one structure still fail, with additional failures on old curves. Error improves to **2.245/2.448 km** from controls **4.896/4.860 km**; those are rejected endpoints, not accepted localization improvements. Removing a fitted affine trend would reduce target RMS to about 22 Hz, but the available witnesses do not justify that freedom. All failed gates are retained in [ch8_phase_repair.csv](ch8_phase_repair.csv).

## A different failure: the target is accurate but the background fit is not

The next 64 historical phase audits find one initial downgrade: **V08, RX1 CH4, 120 points, NORAD 66102**. Its target phase approximation differs from exact geometry by less than 0.000001 Hz. Instead, background NORAD **52311** wants phase −15.09 to −15.16 seconds while its reference is stuck at −15. The whole training fit therefore fails convergence. This is not evidence that 66102 is the wrong target identity.

Refitting every original candidate in every original fold with a domain-checked 30-second reference restores conditional support for 66102. Candidate IDs, aliases, random blocks, priors and 5 × 48-step budgets remain frozen; nomination is not rerun and no future TLE is introduced. Exact replay verifies the revised endpoints. The maximum winning-fit phase gap is below 0.000004 seconds and target tangent/exact discrepancy below 0.000002 Hz. The smallest winning margin stays about **237.1**. This repairs annotation support, not full-scan position inclusion. The ledger preserves the original source, the initial failed audit, and the repaired source.

![Background phase repair](figures/v08_background_phase_repair.png)

## Four new full-model inclusion candidates

Every supported curved-model identity in annotation attempt 24 receives a refitted no-addition control and a full addition trial. Eighteen trials complete. Four retain all incumbent/control satellite owners and pass exact selected-family orbit, existing residual gates, and unclipped phase convergence. Each target contains 42 points; additional accepted-by-gates points elsewhere in the scan explain larger coverage changes.

{table([r for r in trials if r['RF_verified']],['scan','arm','norad','added','control_percent','target_percent','control_error_km','target_error_km'])}

AUTO-e32d57a7 improves both position arms substantially. AUTO-49154edb worsens both despite passing RF checks. The other two change position little. These candidates are not promoted using GPS outcomes. They are separate trials against each scan's retained policy; an earlier recovery in the same scan is not automatically stacked into the new trial. [All 18 CFO/residual plots](graph_gallery.md), [every trial](graph_trials.csv), and [rejected-gate details](graph_rejections.csv) preserve failures as well as successes.

## Does a recovered curve improve independent-family prediction?

All four RF-verified candidates enter a second test, without selecting on position error. Three frozen randomized **scan-wide 12-second block partitions with 2-second guards** are reused per candidate. Every held observation is excluded from training. Both control and addition use the same nominated satellite and alias for the target row; the control excludes its values. Training starts at the regional center, uses fixed 150 Hz noise and unit family powers, and performs five rounds of 48 steps. This is a curved-only conditional-model validation; old predictive rows are excluded and full-data noise/weight policies are not reused. Graph selection, incumbent identities and prior choices remain conditioning assumptions, so this is not independent satellite identification.

Held comparison uses identical original observations from **other satellite families**, with at least four training points per evaluated curve. Constants and other nuisance parameters are learned from training only. Exact plug-in mean residuals are scored; uncertainty is not integrated and overlapping partitions are not independent replicates. Training qualification is reported separately.

{table(held,['scan','seed','arm','control_qualified','target_qualified','RMS_gain_hz','control_error_km','target_error_km'])}

![Prediction versus position](figures/prediction_and_position.png)

The completed comparisons show that improved other-family RMS can coexist with worse position. In the qualified AUTO-49154edb partition, both c arms improve held RMS while position deteriorates. Conversely, AUTO-e32d57a7 can improve position while its held RMS worsens in another partition. Therefore neither target fit nor aggregate other-family RMS is sufficient as a promotion rule under this model. The next useful step is to inspect family-level directional information and nuisance/position tradeoffs, with the [per-family held scores](held_family_comparison.csv), rather than tuning a scalar threshold against GPS.

The first validation batch hit a technical error: exact replay assumed predictive rows existed in a curved-only model. Its 12 failed executions remain archived. The wrapper now handles an empty predictive set, a regression test verifies correct residual replacement and restoration, and the repaired batch is recorded separately. These execution failures are not satellite evidence.

## Inventory and reproducibility

Annotation attempt 25 completes all 32 jobs, bringing coverage to **{summary['annotations_completed']} / {summary['inventory_total']} original large-track entries**. Its statuses are `{summary['annotation_batch']}`. Annotation coverage is not accepted GLRT coverage. **{summary['cumulative_audited']} historical annotations now have phase audits.** All previously supported DS24 curved-model annotations have been checked; **{summary['unaudited_DS24_supported_predictive']} supported predictive-only DS24 annotations** still need their separate replay path. Native overlapping branches remain a separate inventory.

Run `diagnose_graph_residual_witnesses.py` for frozen simultaneous residual context; `probe_graph_phase_domain.py` and `audit_graph_inclusion_owners.py` for the CH8 reference comparison; `refit_annotation_phase_domain.py` and `audit_annotation_phase.py` for the V08 repair; and `validate_graph_inclusion_blocks.py` for the matched training/held experiments. This report is generated by `report_residual_witness_recovery.py`.

**19 targeted tests pass**, covering grouped holdouts, training masks, family exclusion and balancing, RF rate scaling, empty predictive-set exact replay, confidence learning, phase convergence, domain checks, and identical held observation sets. Ledger counts, source hashes, archive readability and all report/gallery links are also verified.

[Summary](summary.json), [cumulative ledger](annotation_ledger.csv), [new annotations](annotation_batch.csv), [phase audits](phase_audit.csv), [residual witness metrics](residual_witnesses.csv), [held comparisons](held_comparison.csv), [execution receipts](validation_executions.csv), [source hashes](sources.json), and [compact numerical evidence](evidence.json.gz) accompany this report. Repeated observation IDs and optimizer histories are hashed in the archive, with immutable source paths retained. No new ALGO version or dataset-wide position improvement is claimed.
'''
    (out/'README.md').write_text(report)
    for path in [Path(__file__),*map(Path,('tools/cross_curve_residual_witnesses.py','tools/diagnose_graph_residual_witnesses.py','tools/validate_graph_inclusion_blocks.py',
        'tools/refit_annotation_phase_domain.py','tools/annotate_track_predictively.py','tools/audit_annotation_phase.py','tools/audit_explicit_phase_endpoint.py'))]:
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    print(summary)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
