"""Publish independent-family ramp validation, full fits and inventory progress."""
import argparse
from collections import Counter
import csv,gzip,hashlib,json
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
    out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir();sources={};evidence={}
    repo=Path(__file__).resolve().parents[1]
    def load(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    def csvread(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return list(csv.DictReader(path.open()))
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    ledger=csvread(repo/'reports/2026_10_29_graph_recovery_iteration15/annotation_ledger.csv');byid={r['track_id']:r for r in ledger}
    queue=args.study/'systematic-annotation-v1';batch=[]
    load(queue/args.attempt/'protocol.json')
    for row in load(queue/args.attempt/'selected.json'):
        tid=row['track_id'];terminal=load(queue/args.attempt/(tid+'-terminal.json'))
        entry=dict(scan=row['label'],track_id=tid,points=row['points'],execution=terminal['status'],status=None,norad=None)
        if terminal['status']=='complete':
            path=queue/tid/'result.json';r=load(path);load(path.parent/'protocol.json')
            a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'));entry.update(status=a['status'],norad=a.get('norad'))
            byid[tid].update(state=a['status'],norad=a.get('norad'),minimum_margin=a.get('minimum_margin'),annotation_source=str(path),
                partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),
                distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        else:byid[tid]['state']='execution_'+terminal['status']
        batch.append(entry)
    csvout('annotation_ledger.csv',ledger);csvout('batch_annotations.csv',batch)
    validations=[];fits=[];executions=[];qualification=[];replays=[];gallery=[]
    protocol=load(args.ramps/'protocol.json')
    for job in protocol['jobs']:
        tid=job['track_id'];root=args.ramps/tid;terminal=load(args.ramps/(tid+'-terminal.json'))
        first_status=terminal['status']
        if args.continuation and (args.continuation/tid/'result.json').exists():
            load(args.continuation/'protocol.json');record=load(args.continuation/tid/'continuation.json')
            if record['source']!=str(root):raise ValueError('continuation source mismatch')
            for path,digest in record['source_sha256'].items():
                if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('continuation source changed')
            root=args.continuation/tid;terminal=load(args.continuation/(tid+'-terminal.json'))
            terminal=dict(terminal,status='complete_after_resume' if terminal['status']=='complete' else terminal['status'])
        executions.append(dict(scan=job['label'],track_id=tid,status=terminal['status'],original_status=first_status,reason=terminal.get('reason'),seconds=terminal['seconds']))
        if (root/'protocol.json').exists():load(root/'protocol.json')
        # Partial runs are explicit; never report missing fits as failures/passes.
        complete_validation=(root/'validation.json').exists()
        folds=load(root/'validation.json')['folds'] if complete_validation else []
        for fold in folds:
            for name,pair in fold['models'].items():
                for arm,v in pair.items():
                    baseline=fold['models']['original'][arm];a=v['target_score'];b=v['existing_score']
                    validations.append(dict(scan=job['label'],track_id=tid,seed=fold['seed'],model=name,arm=arm,
                        target_RMS_hz=a['rms_hz'],baseline_RMS_hz=baseline['target_score']['rms_hz'],
                        target_score_delta=a['negative_twice_log_density']-baseline['target_score']['negative_twice_log_density'],
                        existing_score_delta=b['negative_twice_log_density']-baseline['existing_score']['negative_twice_log_density'],
                        target_phase_s=v['target_phase_mean_s'],phase_boundary_mass=v['target_phase_boundary_mass'],
                        final_phase_change_s=v['final_phase_change_s'],minimum_elevation_deg=v['minimum_elevation_deg']))
        results={}
        for name in ('original','receiver_hz','receiver_fractional'):
            for suffix in ('control','target'):
                tag=name+'_'+suffix;path=root/(tag+'.json')
                if not path.exists():continue
                r=load(path);results[tag]=r
                for arm,v in r['arms'].items():
                    g=v['targets'][0]['gate'] if v['targets'] else None
                    fits.append(dict(scan=job['label'],track_id=tid,model=name,variant=suffix,arm=arm,paired_valid=r['paired_valid'],
                        error_km=error(v),added=v['added_points'],lost=v['lost_points'],objective=v['negative_twice_elbo'],
                        target_RMS_hz=g['conditional_residual_gate']['rms_hz'] if g else None,target_passes=g['compatible'] if g else None,
                        failed_curved=';'.join(t['component'] for t in v['gates']['tracks'] if not t['compatible']),
                        failed_predictive=';'.join(t['component'] for t in v['linear_gates'] if not t['compatible']),
                        phase_change_s=v['final_phase_change_s']))
                if name=='original':
                    oldpath=args.original_inclusions/tid/('control.json' if suffix=='control' else 'target_0.json');old=load(oldpath)
                    for arm,v in r['arms'].items():
                        other=old['arms'][arm];delta=abs(v['negative_twice_elbo']-other['negative_twice_elbo'])
                        gap=float(np.linalg.norm(np.array(v['endpoint_east_north_km'])-other['endpoint_east_north_km']))
                        if delta>1e-5 or gap>1e-5:raise ValueError('unchanged full fit did not replay')
                        replays.append(dict(scan=job['label'],variant=suffix,arm=arm,objective_delta=delta,endpoint_delta_km=gap))
            if name=='original':continue
            vv=[r for r in validations if r['track_id']==tid and r['model']==name]
            predictive=bool(len(vv)==6 and all(r['target_score_delta']<=0 and r['existing_score_delta']<=0 and
                r['target_RMS_hz']<=r['baseline_RMS_hz'] and r['final_phase_change_s']<=.01 and
                r['minimum_elevation_deg']>=0 and r['phase_boundary_mass']<=.05 for r in vv))
            control=results.get(name+'_control');target=results.get(name+'_target')
            qualification.append(dict(scan=job['label'],model=name,complete_validation=complete_validation,
                predictive_screen_pass=predictive,full_control_pass=control['paired_valid'] if control else None,
                full_target_pass=target['paired_valid'] if target else None,
                joint_screen_pass=bool(predictive and control and target and control['paired_valid'] and target['paired_valid'])))
        if folds:
            fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for col,arm in enumerate(('c0','fitted_c')):
                for name,color in [('original','black'),('receiver_hz','#4477aa'),('receiver_fractional','#cc3311')]:
                    local=[r for r in validations if r['track_id']==tid and r['model']==name and r['arm']==arm]
                    axs[0,col].plot(range(len(local)),[r['target_RMS_hz'] for r in local],'o-',label=name,c=color)
                    axs[1,col].plot(range(len(local)),[r['existing_score_delta'] for r in local],'o-',label=name,c=color)
                axs[0,col].set(title=arm,ylabel='Held target RMS (Hz)');axs[1,col].set(ylabel='Existing held score change',xlabel='Randomized partition');axs[1,col].axhline(0,c='black',lw=.5)
                for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=7);ax.set_xticks(range(3),[str(f['seed']) for f in folds],rotation=20)
            fig.suptitle(job['label']+' — entire target family excluded from receiver training\nLower held scores are better; no target frequency enters receiver calibration')
            fig.savefig(figs/(tid+'_validation.png'),dpi=130);plt.close(fig)
            gallery.append(f"### {job['label']} independent-family validation\n\n![Held prediction](figures/{tid}_validation.png)\n")
        target_results=[(name,results[name+'_target']) for name in ('original','receiver_hz','receiver_fractional') if name+'_target' in results]
        if target_results:
            fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for col,arm in enumerate(('c0','fitted_c')):
                for name,r in target_results:
                    d=r['arms'][arm]['targets'][0]
                    axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,label=name)
                    axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=2,label=name)
                axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=8,c='black',label='GLRT track CFO')
                axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Full-fit residual (Hz)');axs[1,col].axhline(0,c='black',lw=.5)
                for ax in axs[:,col]:ax.grid(alpha=.2);ax.legend(fontsize=7)
            fig.suptitle(job['label']+' — full joint position fits, diagnostic until all checks pass')
            fig.savefig(figs/(tid+'_full.png'),dpi=130);plt.close(fig)
            gallery.append(f"### {job['label']} full position-fit residuals\n\n![CFO and residuals](figures/{tid}_full.png)\n")
    csvout('validation_scores.csv',validations);csvout('ramp_full_fits.csv',fits);csvout('execution.csv',executions);csvout('qualification.csv',qualification);csvout('original_model_replay.csv',replays)
    audited={}
    for path in args.gate_audits:
        for row in load(path)['results']:audited[(row['track_id'],row['model'],row['arm'])]=row
    gate_rows=[]
    for r in audited.values():
        for role,key in [('curved','rows'),('predictive','linear_rows')]:
            for v in r.get(key,[]):
                if v['compatible']:continue
                gate_rows.append(dict(scan=r['scan'],model=r['model'],arm=r['arm'],component=v['component'],norad=v['norad'],
                    role=role,target=v.get('target',False),failures=';'.join(v['failures']),
                    RMS_hz=v.get('RMS_hz',v.get('conditional',{}).get('rms_hz')),
                    conditional_pass=v.get('conditional',{}).get('compatible'),profile_noise=json.dumps(v['profile_noise'],sort_keys=True)))
    csvout('rejection_gate_audit.csv',gate_rows)
    # Separate original-model inclusion batch, not part of the five-case ramps.
    next_trials=[];next_gallery=[];next_executions=[];next_protocol=load(args.inclusions/'protocol.json')
    for job in next_protocol['jobs']:
        tid=job['track_id'];terminal=load(args.inclusions/(tid+'-terminal.json'))
        pair_available=all((args.inclusions/tid/file).exists() for file in ('control.json','target_0.json'))
        next_executions.append(dict(scan=job['label'],track_id=tid,status=terminal['status'],reason=terminal.get('reason'),
                                   matched_pair_files_available=pair_available))
        if not pair_available:continue
        r=load(args.inclusions/tid/'target_0.json');c=load(args.inclusions/tid/'control.json')
        fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        for col,(arm,v) in enumerate(r['arms'].items()):
            g=v['targets'][0]['gate'];next_trials.append(dict(scan=job['label'],track_id=tid,arm=arm,norad=job['annotation']['norad'],
                passes=r['paired_valid'],before_km=error(c['arms'][arm]),after_km=error(v),added=v['added_points'],lost=v['lost_points'],
                target_passes=g['compatible'],target_RMS_hz=g['conditional_residual_gate']['rms_hz']))
            d=v['targets'][0];axs[0,col].scatter(d['times_s'],np.array(d['CFO_hz'])/1000,s=10,c='black',label='GLRT track CFO')
            axs[0,col].plot(d['times_s'],np.array(d['predicted_CFO_hz'])/1000,c='#4477aa',label='Shared causal orbit + receiver')
            axs[1,col].plot(d['times_s'],d['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
            axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)')
            for ax in axs[:,col]:ax.grid(alpha=.2)
            axs[0,col].legend(fontsize=8)
        fig.suptitle(f"{job['label']} / {job['annotation']['norad']} — {'PASSES' if r['paired_valid'] else 'REJECTED'}\nUnchanged original model; standalone trial")
        fig.savefig(figs/(tid+'_new_inclusion.png'),dpi=130);plt.close(fig)
        next_gallery.append(f"### {job['label']} / {tid}\n\n![CFO and residual](figures/{tid}_new_inclusion.png)\n")
    csvout('next_graph_inclusions.csv',next_trials)
    csvout('next_graph_execution.csv',next_executions)
    (out/'new_inclusion_gallery.md').write_text('# New original-model inclusion trials\n\n'+'\n'.join(next_gallery))
    if fits:
        fig,axs=plt.subplots(1,2,figsize=(14,5),layout='constrained')
        names=[j['label'] for j in protocol['jobs']]
        for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
            for shift,(model,color) in zip((-.2,0,.2),(('original','black'),('receiver_hz','#4477aa'),('receiver_fractional','#cc3311')),strict=True):
                for k,scan in enumerate(names):
                    rr=[r for r in fits if r['scan']==scan and r['arm']==arm and r['model']==model]
                    for r in rr:
                        ax.scatter(k+shift,r['error_km'],s=40,c=color,marker='o' if r['variant']=='control' else 'x')
                    if len(rr)==2:ax.plot([k+shift]*2,[r['error_km'] for r in rr],c=color,lw=.7)
                ax.plot([],[],c=color,label=model)
            ax.set_xticks(range(len(names)),names,rotation=30,ha='right');ax.set(title=arm,ylabel='Evaluation error (km)');ax.grid(alpha=.2);ax.legend(fontsize=8)
        fig.suptitle('Full position fits: circles = control; crosses = target included\nAll results diagnostic unless predictive and full-fit screens pass')
        fig.savefig(figs/'position_comparison.png',dpi=140);plt.close(fig)
    summary=dict(annotation_batch=len(batch),annotation_outcomes=dict(Counter(r['status'] or 'execution_'+r['execution'] for r in batch)),
        original_inventory=len(ledger),assessed=sum(bool(r['annotation_source']) for r in ledger),
        ramp_executions=dict(Counter(r['status'] for r in executions)),ramp_joint_screen_passes=sum(r['joint_screen_pass'] for r in qualification),
        next_graph_trials=len(next_trials)//2,next_graph_passes=sum(r['passes'] for r in next_trials if r['arm']=='fitted_c'),
        next_graph_execution=dict(Counter(r['status'] for r in next_executions)),
        maximum_original_replay_objective_delta=max((r['objective_delta'] for r in replays),default=None),no_production_change=True)
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    (out/'gallery.md').write_text('# Receiver ramp diagnostics\n\n'+'\n'.join(gallery))
    target_fits=[r for r in fits if r['variant']=='target']
    md=f"""# Independent-family receiver correction experiments

The [preceding residual audit](../2026_10_29_graph_recovery_iteration15/README.md) found a rejected RX1 CH6 curve whose pattern appeared in other RX1 satellite families, across bands. This experiment tests that hypothesis on **all five previously rejected graph inclusions**, including a case without enough multi-family residual witnesses. Execution outcomes: {summary['ramp_executions']}. **{summary['ramp_joint_screen_passes']} model/case combinations pass the combined predictive and full-fit screen.** No production behavior changes.

## Models and independent prediction

The existing model is compared with additive-Hz and RF-proportional receiver corrections. Both add continuous linear ramps beginning every 10 seconds over scan timestamps, on the target receiver, with a Gaussian 50 Hz prior on each ten-second increment (RF-scaled at 11.5 GHz for the fractional model). This is a small exploratory model family, informed by the prior residual investigation; its prior has not been validated on a new cohort. Existing receiver drift, orbital and fragment coordinates remain in the joint model, and the Gaussian marginal likelihood supplies a complexity penalty. Ramps have no frequency discontinuities. Grid locations never use target residuals or GPS.

For each of the existing three distinct randomized 12-second block partitions, with 2-second guards, receiver calibration excludes **the target's entire satellite family**. Every target point is withheld from those calibration equations. Calibration uses only other families' training blocks, fixed 150 Hz noise and unit family powers, matched across c arms. Target training blocks then condition held-target predictions over phase, orbital modes, bias **and shared receiver uncertainty**; held frequencies enter scores, never those predictions. The separately fitted receiver coefficients are unchanged, but Gaussian conditioning can transfer target-training information through receiver covariance into held predictions. This is valid conditional prediction, not a strict demonstration that other satellites alone determine the target correction. Causal phase quadrature has 0.025 s spacing. Held observations from the other families test collateral effects. Nominee and alias remain the previously validated ones: this is a conditional receiver-model test, not a new catalogue identity search.

The conservative screen requires all six partition/c-arm comparisons to improve or preserve target predictive score, target RMS and other-family predictive score, with converged phases, visible geometry and no significant phase-boundary mass. This screen is a diagnostic decision rule, not a calibrated population error guarantee. All full-fit controls and targets must also pass unchanged old-track residual, region, phase and point-preservation checks. Even a passing correction requires renewed candidate competition under the changed receiver model and evaluation on a new cohort before promotion. A stricter transfer ablation must additionally prevent target-training observations from updating receiver uncertainty within predictive conditioning. GPS error never selects a model.

{table(qualification,['scan','model','predictive_screen_pass','full_control_pass','full_target_pass','joint_screen_pass'])}

## Propagation to position

Full fits restore the original observation weights and other priors, and use the same 25×25 km regional-center start, five phase refreshes and 48 iterations per refresh. For each correction, both no-target and target-included fits are run. New curved targets can calibrate the receiver in these full fits; the family-excluded validation above measures held predictions with the receiver-conditioning limitation described above. Both c arms match observations, nominees, priors and search budgets. Original-model replay discrepancy is at most {summary['maximum_original_replay_objective_delta']} objective units. A better in-sample CFO fit or position error alone never authorizes recovery.

{table(target_fits,['scan','model','arm','paired_valid','error_km','added','lost','target_RMS_hz','target_passes'])}

![Position effects](figures/position_comparison.png)

[All held-prediction and full CFO/residual figures](gallery.md), [held scores](validation_scores.csv), [full fits including controls](ramp_full_fits.csv), [qualification decisions](qualification.csv), and [execution receipts](execution.csv) distinguish completed results from any capped or failed jobs. CFO figures place observations and predictions on the original track's display alias branch; numerical fits retain the frozen candidate alias. Rejected trial positions are diagnostic, not accepted localization results. Position errors use only the previously confirmed evaluation site, 37.849061591561885, −122.48574968092912, after inference.

## What remains wrong in the rejected cases

Endpoint replay separates failures that a single overall pass flag hides. In AUTO-d9185bf9, the receiver correction brings the target's conditional RMS to about 63 Hz and its residual/geometry checks pass. Its final target rejection instead comes from the existing **multiple orbital-owner requirement**: the current learned orbital-correction policy requires more independently qualified RX/channel owners. Separately, an existing RX2 CH8 curve assigned to 64758 crosses the autocorrelation gate, despite RMS near 24 Hz. These are distinct failures; the target must not be described as still failing its conditional residual screen.

AUTO-453faf4c's target also passes the corrected full residual checks, while an old RX1 CH4 curve fails residual structure checks. Its independent target prediction is additionally worse in one held partition. AUTO-7ec14096 has an existing predictive CH7 curve that fails after correction. The [exact rejection audit](rejection_gate_audit.csv) records profile/conditional noise, geometry, aliases and owner qualifications in both c arms without changing acceptance.

Next experiments should distinguish receiver-model resolution from an earlier wrong association on the affected old curves. Candidate competition for those curves must be repeated under the proposed model. Active-owner-based orbital-complexity backoff is a separate hypothesis for the single-owner target; it must change the physical model and be refitted, rather than bypassing its qualification gate. Receiver corrections on both RXs should be checked independently. Retaining every old ID is a conservative promotion screen, not proof that those IDs are correct; disagreements require a competing, validated assignment. These remain open tests, not claimed fixes.

## Inventory and unchanged-model recovery also continue

The next {len(batch)} graph assessment attempts yield {summary['annotation_outcomes']}. **{summary['assessed']} / {len(ledger)}** original graph entries now have explicit assessments. The independent inclusion batch provides {summary['next_graph_trials']} complete matched control/target pairs and **{summary['next_graph_passes']} passing trials** under the unchanged model. Execution outcomes are {summary['next_graph_execution']}; [receipts](next_graph_execution.csv) distinguish completed pairs from whole jobs. The existing single-target runner redundantly repeats its target as a combined fit, so a capped job can still contain a complete, parseable control and target pair; only those completed pairs enter the table. These automatic recordings belong to the broader inventory; their gains must not be added to the separate 93-scan DS24 native-policy percentages. Same-scan alternatives require joint testing before combining.

{table([r for r in next_trials if r['arm']=='fitted_c'],['scan','norad','passes','before_km','after_km','added','lost','target_RMS_hz'])}

The [full graph ledger](annotation_ledger.csv), [new annotation outcomes](batch_annotations.csv), [both-arm original-model inclusion results](next_graph_inclusions.csv), and [all new inclusion plots](new_inclusion_gallery.md) retain unresolved cases. The complete objective remains open: assessed identity outcomes can still be ambiguous, and the remaining queue has not been completed. The DS24 native inventory remains separately tracked; nine unavailable GLRT exports remain excluded.

## Reproduction

`run_independent_receiver_ramps.py` runs the five original failure cases with five workers and a 600-second per-case cap. `probe_independent_receiver_ramps.py` records randomized partitions, model definitions, target-family exclusion, conditional predictions and full position fits. `run_annotation_inventory.py run --limit 32 --workers 16 --distinct-partitions` advances the ledger; `run_supported_graph_inclusions.py --attempts attempt-15 --workers 8` tests its preceding supported nominations. `report_receiver_ramp_validation.py` builds this report from frozen receipts. [Source hashes](sources.json), [compressed evidence](evidence.json.gz), and [original replay checks](original_model_replay.csv) retain provenance. Tests cover legacy step behavior, continuous-ramp support and RF scaling, predictive mean/cross-covariance propagation, entire-family exclusion and timestamp-only grid construction. No future TLE, new RF acquisition, dropped old point or relaxed residual gate is accepted.
"""
    (out/'README.md').write_text(md);print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('study','ramps','inclusions','original-inclusions','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--attempt',required=True);p.add_argument('--continuation',type=Path)
    p.add_argument('--gate-audits',type=Path,nargs='*',default=[]);run(p.parse_args())
