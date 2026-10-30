"""Reconcile earlier RF-qualified recoveries after wider causal competition."""
import argparse,csv,gzip,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from review_annotation_competition import matched_expansion
from audit_annotation_phase_resolution import matched_geometry,near_threshold
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.retained_track_likelihood import PERIOD
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();sources={};evidence={}
    def load(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=compact_replays(compact_evidence(r));return r
    def verify(record):
        for name,digest in record.get('source_hashes',{}).items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('changed source '+name)
    def csvread(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return list(csv.DictReader(path.open()))
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=150);plt.close(fig)
    s=args.study;root=s/'shifted-qualified-competition-v1';phase=s/'shifted-qualified-phase-audit-v1'
    protocol=load(root/'protocol.json');verify(protocol);execution=load(root/'execution.json')
    pp=load(phase/'protocol.json');verify(pp);pe=load(phase/'execution.json')
    if any(r['status']!='complete' for r in execution+pe):raise ValueError('incomplete audit')
    if {r['job']['track_id'] for r in execution}!={j['track_id'] for j in protocol['jobs']}:raise ValueError('missing competition case')
    original_rows={};capture={}
    for n in (1,2):
        p=Path(f'reports/2026_10_30_shifted_annotation_batch{n}')
        for r in csvread(p/'comparisons.csv'):
            if r['qualified']=='True' and r['final_variant']=='True':original_rows[r['track_id']]=r
        capture.update({r['track_id']:r for r in csvread(p/'capture_provenance.csv')})
    if set(original_rows)!={j['track_id'] for j in protocol['jobs']}:raise ValueError('review does not cover all earlier qualified cases')
    ledger=csvread(args.previous/'annotation_ledger.csv');byid={r['track_id']:r for r in ledger}
    rows=[];phase_rows=[];diagnostics=[];votes=[]
    for job in protocol['jobs']:
        tid=job['track_id'];old=load(Path(protocol['source_root'])/tid/'result.json');new=load(root/tid/'result.json')
        load(root/tid/'protocol.json');load(root/(tid+'-terminal.json'));matched_expansion(old,new)
        original=original_rows[tid];a=old['annotation'];b=new['annotation'];final=b;final_source=root/tid/'result.json'
        trial=Path(original['source_trial']);control=load(trial/'control.json');addition=load(trial/'new_family.json');audit=load(trial/'exact_owner_replay.json');verify(audit)
        if not(control['paired_valid'] and addition['paired_valid'] and audit['all_verified']):raise ValueError('earlier qualification no longer supported')
        if byid[tid].get('membership_scope_audit'):
            scope=load(Path(byid[tid]['membership_scope_audit']));verify(scope)
            if not scope['RF_qualified_target_only']:raise ValueError('invalid earlier membership scope')
        stable=b['status']=='conditionally_supported_identity' and b['norad']==a['norad']
        matching=[r for r in pe if r['job']['track_id']==tid]
        if near_threshold(b) and {r['job']['step'] for r in matching}!={.05,.025}:raise ValueError('missing threshold resolution checks')
        for rec in sorted(matching,key=lambda r:-r['job']['step']):
            step=rec['job']['step'];name=tid+'-'+str(step);rr=load(phase/name/'result.json');load(phase/name/'protocol.json');load(phase/(name+'-terminal.json'))
            matched_geometry(new,rr);final=rr['annotation'];final_source=phase/name/'result.json'
            if final['status']!=b['status'] or final['norad']!=b['norad']:raise ValueError('phase classification changed; report must describe the change')
            stable &= final['status']=='conditionally_supported_identity' and final['norad']==a['norad']
            phase_rows.append(dict(track_id=tid,scan=original['scan'],step_s=step,coarse_margin=b['minimum_margin'],margin=final['minimum_margin'],
                margin_change=final['minimum_margin']-b['minimum_margin'],status=final['status'],norad=final['norad']))
        if not byid[tid]['predictive_research_inclusion'].startswith('RF_verified'):raise ValueError('later withholding must be reconciled explicitly')
        prior=byid[tid]['predictive_research_inclusion']
        byid[tid].update(predictive_recheck_source=str(final_source),predictive_recheck_state=final['status'],predictive_recheck_minimum_margin=final['minimum_margin'],
            candidate_competition_source=str(root/tid/'result.json'),candidate_competition_status=b['status'])
        if matching:byid[tid]['annotation_phase_resolution_source']=str(phase)
        if not stable:
            byid[tid].update(prior_predictive_research_inclusion=prior,predictive_research_inclusion='withheld_after_candidate_competition')
        rows.append(dict(scan=original['scan'],track_id=tid,norad=a['norad'],points=int(original['points']),capture_mode=capture[tid]['capture_mode'],
            old_margin=a['minimum_margin'],expanded_margin=b['minimum_margin'],final_margin=final['minimum_margin'],
            final_state=final['status'],retains_qualification=stable,
            **{k:float(original[k]) for k in ('c0_before_km','c0_after_km','fitted_c_before_km','fitted_c_after_km')}))
        for v in new['annotation']['votes']:votes.append(dict(track_id=tid,scan=original['scan'],**v))
        if not stable:
            inv=load(Path(job['inventory']));track=load(Path(inv['job']['root'])/inv['job']['case']/'tracks.json')[job['track_index']]
            v=min(b['votes'],key=lambda v:v['margin']);fold=next(f for f in new['folds'] if f['seed']==v['seed'])
            diagnostics.append((original,track,v,fold))
    csvout('qualified_review.csv',rows);csvout('phase_resolution.csv',phase_rows);csvout('votes.csv',votes);csvout('annotation_ledger.csv',ledger)
    pending={}
    for kind in ('shifted','role'):
        name='remaining_'+kind+'_candidates.json';pending[kind]=len(load(args.previous/name));shutil.copyfile(args.previous/name,out/name)
    fig,ax=plt.subplots(figsize=(12,6),layout='constrained');y=np.arange(len(rows))
    ax.barh(y-.18,[r['old_margin'] for r in rows],.36,color='#777',label='Original shortlist')
    ax.barh(y+.18,[r['final_margin'] for r in rows],.36,color=['#0072b2' if r['retains_qualification'] else '#d55e00' for r in rows],label='Expanded; orange is now withheld')
    ax.axvline(10,color='black',ls='--',label='Existing threshold 10');ax.set(xscale='log',yticks=y,
        yticklabels=[r['scan']+' / '+str(r['norad']) for r in rows],xlabel='Minimum held-score margin (log scale)',title='Audit of all nine earlier qualified shifted-origin recoveries')
    ax.invert_yaxis();ax.legend(fontsize=8);ax.grid(axis='x',alpha=.2);save(fig,'qualification_margins.png')
    if diagnostics:
        fig,axes=plt.subplots(len(diagnostics),2,figsize=(13,4*len(diagnostics)),squeeze=False,layout='constrained')
        for (ax,bx),(original,t,v,f) in zip(axes,diagnostics,strict=True):
            times=np.asarray(t['times']);values=np.asarray(t['values']);train,held=replay_split(times,f['split'])
            ax.plot(times,values/1000,'.',color='#bbb',label='All target GLRT');ax.plot(times[train],values[train]/1000,'.',color='#009e73',label='Training');ax.plot(times[held],values[held]/1000,'ko',ms=3,label='Held')
            for norad,color in ((v['norad'],'#0072b2'),(v['runner_up'],'#d55e00')):
                p=next(p for p in f['proposals'] if p['norad']==norad);score=p['arms'][v['arm']]['scores']['conditional_target'];mu=np.asarray(score['held_mean_hz']);sigma=np.asarray(score['prediction_sigma_hz']);residual=np.asarray(score['held_residual_hz'])
                np.testing.assert_allclose(values[held]+p['alias']*PERIOD-mu,residual,atol=1e-7)
                ax.errorbar(times[held],(mu-p['alias']*PERIOD)/1000,yerr=sigma/1000,fmt='s',ms=3,color=color,label=str(norad)+' prediction ±1σ')
                bx.errorbar(times[held],residual,yerr=sigma,fmt='o',ms=3,color=color,label=str(norad))
            ax.set(title=original['scan']+' / '+t['key'].split('-RF')[0],ylabel='Native CFO (kHz)');bx.set(title=f"Weakest competition: seed {v['seed']}, {v['arm']}",ylabel='Held residual (Hz)');bx.axhline(0,c='k',lw=.5)
            for axis in (ax,bx):axis.set_xlabel('Scan time (s)');axis.grid(alpha=.2);axis.legend(fontsize=7)
        save(fig,'withheld_competitors.png')
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
    for tid in sorted({r['track_id'] for r in phase_rows}):
        rr=sorted([r for r in phase_rows if r['track_id']==tid],key=lambda r:-r['step_s']);ax.plot([.1]+[r['step_s'] for r in rr],[0]+[r['margin_change'] for r in rr],'o-',label=rr[0]['scan'])
    ax.set(xlabel='Phase integration spacing (s)',ylabel='Margin change relative to 0.1 s',title='Near-threshold numerical sensitivity');ax.legend();ax.grid(alpha=.2);save(fig,'phase_resolution.png')
    kept=[r for r in rows if r['retains_qualification']];dropped=[r for r in rows if not r['retains_qualification']];batch=load(args.previous/'summary.json')
    summary=dict(reviewed_curves=len(rows),reviewed_points=sum(r['points'] for r in rows),retained_curves=len(kept),retained_points=sum(r['points'] for r in kept),
        withheld_curves=len(dropped),withheld_points=sum(r['points'] for r in dropped),max_margin_grid_change=max(abs(r['margin_change']) for r in phase_rows),
        batch=batch,remaining=pending,position_rerun=False,production_changed=False,goal_complete=False)
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    table='\n'.join(f"| {r['scan']} | {r['norad']} | {r['points']} | {r['old_margin']:.3f} → {r['final_margin']:.3f} | {'retained' if r['retains_qualification'] else 'withheld'} | {r['fitted_c_before_km']:.3f} → {r['fitted_c_after_km']:.3f} |" for r in rows)
    (out/'README.md').write_text(f'''# Rechecking qualified recoveries against competing satellites

All **nine RF-qualified recoveries / 310 points** from shifted batches one and two were rechecked, including their position regressions. Broader causal competition retains **{len(kept)} curves / {summary['retained_points']} points** and returns **{len(dropped)} curves / {summary['withheld_points']} points** to the withheld set. Clean residuals and a successful optimizer do not by themselves establish a unique satellite identity. The original experiments remain historical evidence; they are not erased or relabeled as successful current recoveries.

## Matched competition and position evidence

The candidate cap increases from three to twelve while observations, priors, training budgets, aliases and random physical holdouts remain unchanged. Every original candidate's held score is replayed. Candidates come from the existing causal geometry nomination procedure; this is not exhaustive all-catalogue marginal-likelihood evaluation. GPS is evaluation-only. The three randomized 12-second partitions, with two-second guards, overlap and are not independent replications.

| Scan | NORAD | Points | Minimum margin, original → reviewed | Current status | Historical fitted-c error, km |
| --- | --- | --- | --- | --- | --- |
{table}

![Qualified recovery competition](figures/qualification_margins.png)

62180 now faces closer competition from **67458**, and 67923 from **52634**. Both original identities still rank first in every partition and c arm, but their minimum margins fall below the existing threshold of ten. Neither runner-up is asserted to be the true identity. [Both c=0 and fitted-c historical position comparisons](qualified_review.csv) are retained. No positions were refitted in this retrospective check. Withholding is based on RF competition, not whether a fit happens to move toward the known evaluation site.

![Held predictions of competing satellites](figures/withheld_competitors.png)

These panels use each withheld target's weakest competition fold, selected by RF margin. Grey denotes all target GLRT, green training observations, and black held observations. Coloured squares and one-sigma bars show training-conditioned predictions at held timestamps only, including physical and calibration uncertainty. Residuals replay the archived predictions exactly. The bars are predictive standard deviations, not confidence intervals for satellite identity. Only independent evidence can resolve the remaining ambiguity; choosing the lower-RMS curve alone is insufficient.

## Phase-integration check near the threshold

Every expanded identity with a margin in **[8,12]** was evaluated at 0.05 s and 0.025 s phase spacing, including both sides of the fixed threshold. Candidate sets, aliases, physical partitions and training calibration replay exactly. Across these three curves, the maximum margin change is **{summary['max_margin_grid_change']:.8f}**. No classification changes. In particular, the approximately 10.007 margin is numerically stable in this test, but remains weakly separated from alternatives; it is not a calibrated correctness probability.

![Phase integration sensitivity](figures/phase_resolution.png)

## Continuing systematic coverage

[Shifted batch four](../2026_10_30_shifted_annotation_batch4/README.md) evaluates **{batch['annotations']}** further curves. All initially supported identities receive broader competition before full inclusion. It yields **{batch['qualified_curves']} curves / {batch['qualified_points']} points** passing the recorded RF, residual, ownership and numerical checks in separate matched position trials. The report retains every rejection and position regression, both c arms, acquisition provenance, GLRT curves and residual plots. These individual trials must not be summed into a claimed joint scan-level position improvement.

The updated ledger preserves prior native-IQ and shared-family withholdings and records the two new competition withholdings. **{pending['shifted']} shifted-origin cases and {pending['role']} older-role cases remain; the queues overlap.** Research eligibility is not production promotion. All-source annotation and joint inclusion remain unfinished.

The next steps are to continue the remaining inventory, extend competition checks to older qualified recovery series, and test mutually consistent recoveries together. For ambiguous cases, seek cross-channel/receiver family evidence or independent native-peak evidence before adding flexibility to receiver or orbit models. No new RF was collected and production remains unchanged.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
