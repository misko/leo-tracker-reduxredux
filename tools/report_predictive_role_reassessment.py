"""Publish the first reconciled predictive-role batch and native measurement audit."""
import argparse,csv,gzip,hashlib,json,shutil
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_predictive_track_annotation import table
from report_inventory_experiments import error
from report_omitted_predictive_recovery import target_diagnostic
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from report_inactive_fragment_transfer import replay_slacks
from annotation_partition_plan import require_distinct_annotation
from leo.analysis.research.grouped_prediction import replay_split


def complete_replay_slacks(row):
    """Include new-family target screens as well as incumbent/shared screens."""
    slacks=replay_slacks(row)
    for kind in ('target','continuous_target'):
        for d in (row.get(kind) or {}).get('diagnostics',[]):
            n=d['noise'];prefix=d['component']+'/'+kind+'/'
            ratios=dict(rms=d['profile_RMS_hz']/450,bias=abs(d['profile_bias_hz'])/3000,
                mean=abs(n['mean_z'])/3,slope=abs(n['slope_z'])/3,
                quadratic=n['quadratic_bic_gain']/10,step=n['maximum_step_z']/4,
                lag1=abs(n['lag1_acf'])/(4/np.sqrt(len(d['times_s']))))
            slacks.update({prefix+k:1-v for k,v in ratios.items()})
            slacks[prefix+'elevation']=d['minimum_elevation_deg']
    return slacks


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    iteration=getattr(args,'iteration',1)
    s=args.study;q=s/'predictive-annotation-source-registry-v1';tr=s/f'reconciled-role-inclusion-v{iteration}';retry=getattr(args,'numerical_followup',None) or s/f'reconciled-role-numerical-followup-v{iteration}'
    hashes={};evidence={}
    def load(p):
        d=read(p);hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();evidence[str(p)]=compact_replays(compact_evidence(d));return d
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=140);plt.close(fig)
    previous=args.previous/'annotation_ledger.csv';ledger=list(csv.DictReader(previous.open()));byid={r['track_id']:r for r in ledger};hashes[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest()
    attempt=q/f'attempt-{iteration}'
    selected=load(attempt/'selected.json');load(attempt/'execution.json');load(attempt/'protocol.json')
    registry=load(q/'summary.json');pending=load(args.previous/'remaining_role_candidates.json') if (args.previous/'remaining_role_candidates.json').exists() else load(q/'pending.json')
    if not {r['track_id'] for r in selected}<={r['track_id'] for r in pending}:raise ValueError('batch repeats or leaves pending role queue')
    execution=load(tr/'execution.json');load(tr/'protocol.json')
    followup={r['job']['track_id']:r for r in load(retry/'execution.json')};load(retry/'protocol.json')
    provenance=s/f'capture-provenance-audit-v{iteration}';capture={r['track_id']:r for r in load(provenance/'rows.json')};cap_summary=load(provenance/'summary.json')
    for p,digest in cap_summary['source_hashes'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('changed capture provenance')
    shutil.copyfile(provenance/'capture_provenance.csv',out/'capture_provenance.csv');write(out/'capture_provenance_summary.json',cap_summary)
    annotations=[];partitions=[];gallery=[];terminals=[];plots={};positions=[];comparisons=[];failures=[];scope_links=[]
    interrupted=getattr(args,'interrupted_followup',None)
    if interrupted:
        load(interrupted/'protocol.json')
        for rec in load(interrupted/'execution.json'):
            if rec['status']!='execution_failed':raise ValueError('interrupted run must retain terminal failure')
            for stage in rec['stages']:terminals.append(dict(scan=rec['job']['label'],variant='interrupted_thread_oversubscription',**stage))
    for job in selected:
        tid=job['track_id'];terminal=load(attempt/(tid+'-terminal.json'));terminals.append(terminal)
        if terminal['status']!='complete':raise ValueError('annotation batch incomplete')
        r=load(q/tid/'result.json');p=load(q/tid/'protocol.json');a=r['annotation'];inv=load(Path(job['inventory']))
        track=read(Path(inv['job']['root'])/inv['job']['case']/'tracks.json')[job['track_index']]
        if r.get('inactive_graph_fragment'):raise ValueError('fragment requires separate physical scope reporting')
        signatures=[]
        for f in r['folds']:
            train,held=replay_split(np.array(track['times']),f['split']);sig=tuple(np.flatnonzero(held));signatures.append(sig)
            partitions.append(dict(track_id=tid,seed=f['seed'],train=int(train.sum()),held=int(held.sum()),held_indices=' '.join(map(str,sig))))
        if a['status']=='conditionally_supported_identity':
            require_distinct_annotation(r,p)
            if len(set(signatures))!=3:raise ValueError('repeated held point set')
        annotations.append(dict(scan=job['label'],track_id=tid,points=job['points'],old_status=byid[tid]['state'],
            status=a['status'],norad=a['norad'],margin=a.get('minimum_margin'),distinct_target_holds=len(set(signatures)),
            capture_mode=capture[tid]['capture_mode'],sample_rate_hz=capture[tid]['sample_rate_hz']))
        byid[tid].update(predictive_recheck_source=str(q/tid/'result.json'),predictive_recheck_state=a['status'],
            predictive_recheck_minimum_margin=a.get('minimum_margin'),annotation_likelihood_role='predictive_only; distinct randomized group validation')
        gallery.append((job,track,a))
    for original in execution:
        job=original['job'];tid=job['track_id'];variants=[('initial',tr,original)]
        if tid in followup:variants.append(('numerical_followup',retry,followup[tid]))
        for label,root,rec in variants:
            for stage in rec['stages']:terminals.append(dict(scan=job['label'],variant=label,**stage))
            if rec['status']=='execution_failed':raise ValueError('inclusion execution incomplete')
            p=root/tid/'trial';pr=load(p/'protocol.json');control=load(p/'control.json');v=load(p/('target_0.json' if rec['shared_family'] else 'new_family.json'));audit=load(p/'exact_owner_replay.json')
            for path,digest in audit['source_hashes'].items():
                if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('exact replay source changed')
            qualified=bool(control['paired_valid'] and v['paired_valid'] and audit['all_verified']);final=label==variants[-1][0]
            scope=None
            scope_path=args.membership_scopes/(tid+'.json') if getattr(args,'membership_scopes',None) else None
            if final and scope_path is not None and scope_path.exists():
                scope=load(scope_path)
                if not scope['RF_qualified_target_only']:raise ValueError('invalid membership scope')
                for source,digest in scope['source_hashes'].items():
                    if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=digest:raise ValueError('changed scoped trial')
                if str(p/'new_family.json') not in scope['source_hashes']:raise ValueError('membership scope belongs to another trial')
                (out/'membership_scopes').mkdir(exist_ok=True)
                shutil.copyfile(scope_path,out/'membership_scopes'/scope_path.name)
                scope_links.append(f'[{job["label"]} scope audit](membership_scopes/{scope_path.name})')
            inv=load(Path(job['inventory']));ids={o for t in pr['targets'] for o in t['observation_ids']}
            row=dict(scan=job['label'],track_id=tid,norad=job['annotation']['norad'],points=len(ids),qualified=qualified,variant=label,final_variant=final,source_trial=str(p))
            for arm,z in v['arms'].items():
                row[arm+'_before_km']=error(control['arms'][arm]);row[arm+'_after_km']=error(z)
                d=target_diagnostic(z);before=set(control['arms'][arm]['proposed_associated_ids']);after=set(z['proposed_associated_ids'])
                raw_after=after.copy()
                if scope is not None:after=set(scope['arms'][arm]['reviewed_associated_ids'])
                if qualified and (after-before!=ids or before-after):raise ValueError('qualified ownership differs from target')
                positions.append(dict(scan=job['label'],track_id=tid,variant=label,final_variant=final,arm=arm,qualified=qualified,
                    control_error_km=error(control['arms'][arm]),addition_error_km=error(z),target_RMS_hz=d['RMS_hz'],
                    control_objective=control['arms'][arm]['negative_twice_elbo'],addition_objective=z['negative_twice_elbo'],
                    baseline_percent=100*len(before)/inv['summary'][0]['total_GLRT'],proposed_percent=100*len(after)/inv['summary'][0]['total_GLRT'],
                    raw_proposed_points=len(raw_after),reviewed_proposed_points=len(after),unvalidated_extension_points=len(raw_after-after),
                    optimizer_success=z['history'][-1].get('success'),phase_change_s=z['final_phase_change_s'],exact_replay_pass=audit['all_verified']))
                if final:plots[tid,arm]=d
            for arow in audit['rows']:
                for gate,slack in complete_replay_slacks(arow).items():
                    if slack<0:failures.append(dict(scan=job['label'],variant=label,role=arow['role'],arm=arow['arm'],gate=gate,slack=slack,
                        evidence_role='target' if gate.split('/',1)[0] in {t['component'] for t in pr['targets']} else 'incumbent'))
            comparisons.append(row)
            if final:
                byid[tid].update(predictive_inclusion_source=str(p),predictive_research_inclusion='RF_verified_research_candidate' if qualified else 'inclusion_rejected')
                if scope is not None:byid[tid]['membership_scope_audit']=str(scope_path)
    final=[r for r in comparisons if r['final_variant']]; remaining=[r for r in pending if r['track_id'] not in {j['track_id'] for j in selected}]
    for name,rows in [('annotation_ledger.csv',ledger),('annotations.csv',annotations),('partitions.csv',partitions),('position_trials.csv',positions),('comparisons.csv',comparisons),('failed_replay_gates.csv',failures),('executions.csv',terminals)]:csvout(name,rows)
    write(out/'remaining_role_candidates.json',remaining)
    summary=dict(annotations=len(annotations),annotation_states=dict(Counter(r['status'] for r in annotations)),position_cases=len(final),
        qualified_curves=sum(r['qualified'] for r in final),qualified_points=sum(r['points'] for r in final if r['qualified']),remaining_role_candidates=len(remaining),
        capture_modes=dict(Counter(r['capture_mode'] for r in annotations)),production_changed=False,goal_complete=False)
    write(out/'summary.json',summary)
    fig,axs=plt.subplots(1,2,figsize=(13,6),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        x=np.arange(len(final));ax.barh(x-.16,[r[arm+'_before_km'] for r in final],.32,color='#999',label='Matched control')
        ax.barh(x+.16,[r[arm+'_after_km'] for r in final],.32,color=['#009e73' if r['qualified'] else '#d55e00' for r in final],label='Addition: green passes RF checks')
        ax.set(yticks=x,yticklabels=[r['scan'] for r in final],title=arm,xlabel='Evaluation position error (km)');ax.invert_yaxis();ax.legend(fontsize=7)
    save(fig,'position_comparison.png');pages=[]
    for page,start in enumerate(range(0,len(gallery),4),1):
        group=gallery[start:start+4];fig,axs=plt.subplots(len(group),2,figsize=(14,3.1*len(group)),layout='constrained',squeeze=False)
        for axes,(j,t,a) in zip(axs,group,strict=True):
            axes[0].plot(t['times'],np.array(t['values'])/1000,'.');axes[0].set(title=j['label']+' / '+t['key'],ylabel='GLRT CFO (kHz)')
            if (j['track_id'],'fitted_c') in plots:
                for arm in ('c0','fitted_c'):
                    d=plots[j['track_id'],arm];axes[1].plot(d['times_s'],d['residual_hz'],'.-',lw=.6,label=arm)
                d=plots[j['track_id'],'fitted_c'];axes[0].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,'k-',lw=.7);axes[1].axhline(0,c='k',lw=.5);axes[1].legend(fontsize=7);axes[1].set_ylabel('Orbital residual (Hz)')
            else:axes[1].text(.5,.5,a['status'].replace('_',' '),ha='center',transform=axes[1].transAxes);axes[1].set_axis_off()
            for ax in axes:ax.set_xlabel('Scan time (s)');ax.grid(alpha=.2)
        name=f'curves_{page}.png';save(fig,name);pages.append(f'![Curves {page}](figures/{name})')
    native=load(s/'omitted-60342-native-measurements-v1/result.json');write(out/'native_measurements.json',native)
    shutil.copyfile(s/'omitted-60342-native-measurements-v1/native_audit.png',out/'figures/native_audit.png')
    native_rows=[{k:r[k] for k in ('time_s','original_polynomial_residual_hz','fractional_margin','eligible_candidates','maximum_support_timing_shift_hz')} for r in sorted(native['points'],key=lambda r:abs(r['original_polynomial_residual_hz']),reverse=True)[:5]]
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    (out/'README.md').write_text(f'''# Predictive-role reassessment, native measurement evidence, and capture-mode correction

We reconciled the 985 older-role primary annotations against saved predictive-only annotation protocols in the study. None had an exact-target match in the recognized predictive schema. This is a source-scope finding, not proof that no historical experiment exists elsewhere. The 16 largest were reassessed without allowing target observations to calibrate the receiver. **{summary['remaining_role_candidates']} remain** in this role queue; the full 1,630-curve goal remains incomplete.

## Capture provenance correction

Earlier omitted-queue reports incorrectly treated `source.capture_mode` in fast compatibility exports as acquisition provenance. The adapter writes `adaptive` into this field for fast scans. The previous 53 curves actually comprise **49 fast and 4 adaptive** recordings: **27 fast at 10 MS/s, 22 fast at 2.5 MS/s, and four adaptive at 10 MS/s**. This correction supersedes their all-adaptive statements and capture-mode columns. The four legacy DS24 aliases mapped to DS25 remain adaptive. The 16 new cases are all fast: 13 at 10 MS/s and three at 2.5 MS/s.

[capture_provenance.csv](capture_provenance.csv) covers all 69 curves. For fast exports, the audit matches the input inventory's canonical digest, verifies every segment manifest digest and window count, and checks acquisition versus tracking sample rates. Direct scanner tracking records remain distinguished from compatibility wrappers. The current diagnostic reporter flags unverified fast wrappers instead of trusting the compatibility field. No persisted contract, measurement, satellite label, or saved position output was changed.

## Independent-role annotation results

The same causal catalogue and physical priors are used in both c arms. Three distinct random scanwide 12-second block partitions with 2-second guards are selected from timestamps alone. The report replays the held point sets. GPS is used only to report position error. Older labels and assessments remain separately recorded.

{table(annotations,['scan','points','old_status','status','norad','margin'])}

The outcomes are **{summary['annotation_states']}**. A confident candidate comparison can still fail absolute predictive agreement: V08 and AUTO-5b808147 illustrate this. Identity margins are not calibrated posterior probabilities. No ambiguous or unstable label is forced into position estimation.

## Matched position inclusion

All nine supported identities receive control/addition tests with matched c=0/fitted-c settings and 0.025-second phase integration for new families. One numerical-only failure receives a matched Powell retry; all original trials remain in [comparisons.csv](comparisons.csv). Exact replay and ownership checks are retained. No physical gate is loosened because position error improves.

{table(final,['scan','norad','points','qualified','c0_before_km','c0_after_km','fitted_c_before_km','fitted_c_after_km'])}

![Position comparisons](figures/position_comparison.png)

**{summary['qualified_curves']} curves / {summary['qualified_points']} points** pass the current RF checks. These remain per-curve research candidates; they are not production changes or a simultaneous combined solution. Passing frequency tests does not guarantee better localization. [position_trials.csv](position_trials.csv) separates coverage, frequency-fit objectives, RMS and position errors. [failed_replay_gates.csv](failed_replay_gates.csv) preserves failing replay constraints, while compact raw evidence retains target noise gates and optimizer outcomes.

V02's 102-point target substantially reduces position error but still fails its fitted-c residual slope (z≈4.05 > 3) and step statistic (≈4.34 > 4), despite RMS≈163 Hz. It remains rejected. This is a useful next model investigation rather than an accepted recovery.

{chr(10).join(pages)}

## 60342: excursions are already present in the native curve

The previous 60342 inclusion passed RF checks but moved fitted-c position error from 0.090 to 0.937 km. This audit exactly replays all archived winning observations and verifies that graph values differ only by integer aliases. The original graph itself had an adjacent-residual-correlation flag; it was not a uniformly clean measurement curve.

![Native measurements, quality, timing and receiver witnesses](figures/native_audit.png)

{table(native_rows,['time_s','original_polynomial_residual_hz','fractional_margin','eligible_candidates','maximum_support_timing_shift_hz'])}

The strongest original-polynomial excursion is about 318 Hz at 242.033 s, with a maximum first-order within-pilot timing effect of about 33 Hz. It is the only exported candidate passing the margin gate. Polynomial-versus-orbit residual correlations are **0.824 (c=0)** and **0.861 (fitted-c)**. Thus much of the irregular residual behavior exists before satellite association. This favors testing the measurement against its existing IQ before adding orbital or receiver flexibility. A polynomial residual does not prove measurement error: source mixing and approximation error remain possible.

Two same-RX native polynomial witnesses have 34 and 31 one-to-one pairs within 1.5 s and residual correlations of approximately -0.001 and 0.278. They do not show strong common excursions under this diagnostic. They are in-sample, and their polynomial fits can absorb shared smooth errors, so this does not rule out a shared receiver drift. The timing figures use the original polynomial derivative and pilot sample support; they are not absolute-clock validation or actual IQ-weighted centroid estimates.

## Next steps and reproducibility

Remeasure the complete 34-point 60342 target from existing IQ, with independent frame consistency and complementary-frame prediction, rather than removing its worst points. Keep the frequency estimator independent of GPS/TLE predictions. Investigate V02's residual structure with the same native-measurement and cross-family checks. Continue bounded reassessment of the remaining 969 older-role candidates; keep ambiguity, insufficient evidence, and physical model failures explicit.

[The updated 1,630-row ledger](annotation_ledger.csv), [remaining role candidates](remaining_role_candidates.json), [native evidence](native_measurements.json), [partition assignments](partitions.csv), [execution receipts](executions.csv), [source hashes](sources.json), and compressed scientific evidence accompany the report. No new RF was collected. Production and acceptance thresholds are unchanged.
''')
    if iteration>1:
        (out/'README.md').write_text(f'''# Predictive-role reassessment batch {iteration}

The next **{len(selected)}** curves from the frozen older-role queue have terminal predictive-only assessments. **{len(remaining)} remain**. The full 1,630-curve goal is incomplete. Selection follows descending point count without GPS-based ranking; no supported label is forced into inclusion.

## Identity and provenance

{table(annotations,['scan','points','old_status','status','norad','margin'])}

Outcomes: **{summary['annotation_states']}**. Every supported identity has three distinct randomized scanwide 12-second held block sets, with two-second guards. The report replays the physical point sets. Targets do not calibrate the receiver. Capture modes are **{summary['capture_modes']}**, verified from the acquisition provenance rather than the fast adapter's compatibility label; [capture_provenance.csv](capture_provenance.csv) retains the authorities and sample rates.

## Position trials

{table(final,['scan','norad','points','qualified','c0_before_km','c0_after_km','fitted_c_before_km','fitted_c_after_km'])}

![Matched position comparisons](figures/position_comparison.png)

**{summary['qualified_curves']} individual curves / {summary['qualified_points']} points** pass the current RF checks. These are separate research trials, not a simultaneous solution or a production change. Controls/additions and c=0/fitted-c arms use matched observations, candidate sets, priors and budgets; additions differ only by their specified targets. New-family phase integration uses 0.025-second spacing. Numerical retries, if any, preserve the physical gates. All original and retry outputs, including regressions and rejections, remain in [comparisons.csv](comparisons.csv) and [position_trials.csv](position_trials.csv). Exact replay failures are in [failed_replay_gates.csv](failed_replay_gates.csv).

Individual outcomes do not establish joint consistency. The earlier V06 joint audit illustrates this limitation; no union of individual position improvements is claimed. The failed-gate table distinguishes target from incumbent evidence and includes both nominal and continuously refined new-family target screens.

{('The first numerical follow-up was interrupted because excessive BLAS threading made it inefficient. Its terminal failure and protocol remain in executions.csv and hashed evidence. A fresh output repeats the same scientific settings and stage cap with OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1; no gate or data changes.') if interrupted else ''}

{('Scoped membership: reported association percentages count the matched control plus the independently validated target. Unscored automatic extension discoveries remain separate and unvalidated; raw and reviewed counts are both recorded in position_trials.csv. Audits: '+', '.join(scope_links)+'.') if scope_links else ''}

{chr(10).join(pages)}

## Remaining work and evidence

[The updated ledger](annotation_ledger.csv), [remaining candidates](remaining_role_candidates.json), [holdout point assignments](partitions.csv), [receipts](executions.csv), and source-hashed compact evidence preserve the next work. The separate [native IQ investigation](../2026_10_30_native_iq_recovery/README.md) reports the complete 60342 remeasurement and the V06 joint-family trial. No future TLE or evaluation GPS enters inference; GPS is used only for error reporting. Production is unchanged.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--iteration',type=int,default=1)
    p.add_argument('--membership-scopes',type=Path,help='Optional explicit audits of unscored incidental extension discoveries')
    p.add_argument('--numerical-followup',type=Path,help='Explicit preserved follow-up output, if different from the iteration default')
    p.add_argument('--interrupted-followup',type=Path,help='Preserve a terminal execution failure preceding a fresh run')
    run(p.parse_args())
