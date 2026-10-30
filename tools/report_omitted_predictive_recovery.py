"""Publish corrected omitted-track routing, distinct validation and position trials."""
import argparse,csv,gzip,hashlib,json,shutil
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays
from leo.analysis.research.grouped_prediction import replay_split
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from run_reconciled_predictive_inclusions import require_distinct_annotation


def target_diagnostic(row):
    if 'family' in row:
        d=row['family']['diagnostics'][0]
        return dict(times_s=d['times_s'],CFO_hz=d['CFO_hz'],
            predicted_CFO_hz=np.array(d['prediction_CFO_hz'])+d['profile_bias_hz'],
            residual_hz=np.array(d['raw_residual_hz'])-d['profile_bias_hz'],RMS_hz=d['profile_RMS_hz'])
    d=row['target_diagnostics'][0]
    return dict(d,predicted_CFO_hz=np.array(d['predicted_CFO_hz'])+d['bias_hz'])


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();hashes={};evidence={}
    def load(path,compact=True):
        d=read(path);hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        if compact:evidence[str(path)]=compact_replays(compact_evidence(d))
        return d
    def csvout(name,rows):
        keys=list(dict.fromkeys(k for r in rows for k in r))
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    registry=s/'inclusion-source-registry-v2';rs=load(registry/'summary.json');load(registry/'curve_trial_links.json');load(registry/'trial_registry.json')
    for name in ('supported_reconciliation.csv','pending_candidates.json'):
        p=registry/name;hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();shutil.copyfile(p,out/name)
    prelim=s/'omitted-predictive-inclusion-v1';root=s/'omitted-predictive-distinct-inclusion-v1';retry=s/'omitted-predictive-numerical-followup-v1'
    pr=load(root/'protocol.json');executions=load(root/'execution.json');earlier=load(prelim/'execution.json');followup=load(retry/'execution.json');load(retry/'protocol.json')
    assert len(executions)==8 and len(followup)==3 and all(r['status']!='execution_failed' for r in executions+followup)
    newer={r['job']['track_id']:r for r in followup};byid={r['job']['track_id']:r for r in executions}
    partitions=[];annotations=[];physical=[];positions=[];final=[];plots=[];qualified=[];receipts=[];rawids=set()
    oldledger=args.previous/'annotation_ledger.csv';ledger=list(csv.DictReader(oldledger.open()));hashes[str(oldledger)]=hashlib.sha256(oldledger.read_bytes()).hexdigest();lookup={r['track_id']:r for r in ledger}
    for job in pr['jobs']:
        tid=job['track_id'];r=byid[tid];inv=load(Path(job['inventory']));target=next(t for t in inv['tracks'] if t['track_id']==tid)
        basepath=Path(inv['job']['root'])/inv['job']['case'];tracks=load(basepath/'tracks.json',compact=False);track=tracks[target['track_index']];times=np.asarray(track['times'])
        native=load(basepath/'tracking.json',compact=False)['source'];mode=native['capture_mode'];rate=native['sample_rate_hz']
        val=root/tid/'annotation';a=load(val/'result.json');ap=load(val/'protocol.json');require_distinct_annotation(a,ap)
        old=load(Path(job['validation'])/'result.json');distinct={}
        for kind,result in [('old',old),('refreshed',a)]:
            signatures=[]
            for f in result['folds']:
                train,held=replay_split(times,f['split']);sig=tuple(np.flatnonzero(held));signatures.append(sig)
                partitions.append(dict(track_id=tid,scan=job['label'],kind=kind,seed=f['seed'],training_points=int(train.sum()),held_points=int(held.sum()),
                    target_held_indices=' '.join(map(str,sig)),held_blocks=' '.join(map(str,sorted(set(np.floor(times[held]/12).astype(int)))))))
            distinct[kind]=len(set(signatures))
        assert distinct['refreshed']==3
        annotations.append(dict(track_id=tid,scan=job['label'],points=job['points'],engine_member=job['engine_member'],
            active_curvature=target['current']['active_curvature'],capture_mode=mode,sample_rate_hz=rate,
            old_distinct_partitions=distinct['old'],new_distinct_partitions=distinct['refreshed'],old_norad=job['annotation']['norad'],
            new_norad=a['annotation']['norad'],status=a['annotation']['status'],minimum_margin=a['annotation']['minimum_margin']))
        final_record=newer.get(tid,r);final_root=retry if tid in newer else root;folder=final_root/tid/'trial'
        for kind,version,receipt in [('preliminary',prelim,next(x for x in earlier if x['job']['track_id']==tid)),('distinct',root,r)]+([('numerical_followup',retry,newer[tid])] if tid in newer else []):
            load(version/(tid+'-terminal.json'));receipts.extend(dict(scan=job['label'],iteration=kind,**st) for st in receipt['stages'])
            p=version/tid/'trial';tp=load(p/'protocol.json');c=load(p/'control.json');v=load(p/('target_0.json' if receipt['shared_family'] else 'new_family.json'));replay=load(p/'exact_owner_replay.json')
            for source,digest_value in replay['source_hashes'].items():
                actual=hashes.get(source) or hashlib.sha256(Path(source).read_bytes()).hexdigest()
                if actual!=digest_value:raise ValueError('exact replay refers to changed source: '+source)
            is_final=p==folder;passed=c['paired_valid'] and v['paired_valid'] and replay['all_verified']
            if is_final:assert passed==(final_record['status']=='RF_verified_research_candidate')
            for arm,z in v['arms'].items():
                d=target_diagnostic(z);noise={k:v[0].item() for k,v in batch_noise_screen(np.asarray(d['residual_hz'])[None],np.asarray(d['times_s'])).items()}
                cids=set(c['arms'][arm]['proposed_associated_ids']);ids=set(z['proposed_associated_ids']);tids=set(o for e in tp['targets'] for o in e['observation_ids'])
                if passed:assert ids-cids==tids and not cids-ids
                row=dict(track_id=tid,scan=job['label'],iteration=kind,final_variant=is_final,arm=arm,norad=a['annotation']['norad'],
                    points=job['points'],capture_mode=mode,sample_rate_hz=rate,control_error_km=error(c['arms'][arm]),addition_error_km=error(z),
                    qualified=is_final and passed,preliminary_pair_pass=passed,baseline_points=len(cids),proposed_points=len(ids),
                    total_GLRT=inv['summary'][0]['total_GLRT'],baseline_percent=100*len(cids)/inv['summary'][0]['total_GLRT'],
                    proposed_percent=100*len(ids)/inv['summary'][0]['total_GLRT'],credited_points=len(ids-cids) if is_final and passed else 0,
                    RMS_hz=d['RMS_hz'],control_objective=c['arms'][arm]['negative_twice_elbo'],addition_objective=z['negative_twice_elbo'],
                    exact_replay_pass=replay['all_verified'],control_pair_pass=c['paired_valid'],addition_pair_pass=v['paired_valid'],
                    final_phase_change_s=z['final_phase_change_s'],optimizer_success=z['history'][-1].get('success'),
                    optimizer_message=z['history'][-1].get('message'),quadrature_pass=z.get('phase_resolution_audit',{}).get('local_agreement'),**noise)
                positions.append(row)
                if is_final:physical.append(row)
            if is_final:
                plots.append((job,v,passed));cv=c;av=v;finalprotocol=tp
        row=dict(scan=job['label'],track_id=tid,norad=a['annotation']['norad'],points=job['points'],qualified=final_record['status']=='RF_verified_research_candidate',
            c0_before_km=error(cv['arms']['c0']),c0_after_km=error(av['arms']['c0']),
            fitted_c_before_km=error(cv['arms']['fitted_c']),fitted_c_after_km=error(av['arms']['fitted_c']),
            final_trial=str(folder),capture_mode=mode,sample_rate_hz=rate)
        final.append(row)
        lookup[tid].update(predictive_recheck_source=str(val/'result.json'),predictive_recheck_state=a['annotation']['status'],
            predictive_recheck_minimum_margin=a['annotation']['minimum_margin'],predictive_research_inclusion=final_record['status']+'; not production promoted',
            predictive_inclusion_source=str(folder),annotation_likelihood_role='predictive_only; distinct random partitions')
        if row['qualified']:
            ids=set(o for e in finalprotocol['targets'] for o in e['observation_ids'])
            if rawids&ids:raise ValueError('double-counted recovered measurements')
            rawids.update(ids);qualified.append(row)
    csvout('annotations.csv',annotations);csvout('partitions.csv',partitions);csvout('all_position_trials.csv',positions)
    csvout('final_positions.csv',final);csvout('physical_checks.csv',physical);csvout('annotation_ledger.csv',ledger);csvout('executions.csv',receipts)
    remaining=[j for j in read(registry/'pending_candidates.json') if j['track_id'] not in byid];assert len(remaining)==45
    write(out/'remaining_omitted_candidates.json',remaining)
    summary=dict(registry={k:v for k,v in rs.items() if k!='source_hashes'},freshly_validated=len(executions),
        qualification_counts=dict(Counter(r['qualified'] for r in final)),distinct_qualified_points=len(rawids),remaining_omitted_candidates=len(remaining),
        capture_modes=dict(Counter(r['capture_mode'] for r in annotations)),production_changed=False,full_goal_complete=False)
    write(out/'summary.json',summary)
    fig,axs=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    for ax,arm in zip(axs,('c0','fitted_c'),strict=True):
        x=np.arange(len(final));ax.barh(x-.16,[r[arm+'_before_km'] for r in final],.32,color='#999',label='Matched control')
        ax.barh(x+.16,[r[arm+'_after_km'] for r in final],.32,color=['#009e73' if r['qualified'] else '#d55e00' for r in final],label='Addition: green qualifies')
        ax.set(yticks=x,yticklabels=[r['scan']+' / '+str(r['norad']) for r in final],xlabel='Evaluation position error (km)',title=arm);ax.invert_yaxis()
        ax.legend(handles=[Patch(color=c,label=n) for c,n in [('#999','Matched control'),('#009e73','Qualified addition'),('#d55e00','Rejected addition')]],fontsize=8);ax.grid(axis='x',alpha=.2)
    save(fig,'position_comparison.png')
    for page in range(2):
        fig,axs=plt.subplots(4,2,figsize=(14,13),layout='constrained')
        for axes,(job,v,passed) in zip(axs,plots[page*4:page*4+4],strict=True):
            d=target_diagnostic(v['arms']['fitted_c']);axes[0].plot(d['times_s'],np.asarray(d['CFO_hz'])/1000,'.',label='Native graph GLRT')
            axes[0].plot(d['times_s'],np.asarray(d['predicted_CFO_hz'])/1000,c='k',lw=.8,label='Causal orbit + nuisance terms')
            for arm,color in [('c0','#0072b2'),('fitted_c','#d55e00')]:
                q=target_diagnostic(v['arms'][arm]);axes[1].plot(q['times_s'],q['residual_hz'],'.-',lw=.6,color=color,label=arm)
            axes[0].set(title=job['label']+' / '+job['component'].split('-RF')[0]+' / '+('QUALIFIED' if passed else 'REJECTED'),ylabel='CFO (kHz)')
            axes[1].set(title='Residual after one track bias',ylabel='Residual (Hz)');axes[1].axhline(0,c='k',lw=.5)
            for ax in axes:ax.set_xlabel('Scan time (s)');ax.legend(fontsize=8);ax.grid(alpha=.2)
        save(fig,f'curves_{page+1}.png')
    fig,ax=plt.subplots(figsize=(12,5),layout='constrained')
    rr=[r for r in physical if r['arm']=='fitted_c'];x=np.arange(len(rr))
    ax.bar(x-.18,[r['baseline_percent'] for r in rr],.36,color='#999',label='Matched control')
    ax.bar(x+.18,[r['proposed_percent'] if r['qualified'] else r['baseline_percent'] for r in rr],.36,color=['#009e73' if r['qualified'] else '#999' for r in rr],label='Qualified recovery only')
    ax.set(xticks=x,xticklabels=[r['scan'] for r in rr],ylabel='Associated GLRT (%)',ylim=(0,100));ax.tick_params(axis='x',rotation=25);ax.legend();ax.grid(axis='y',alpha=.2);save(fig,'coverage.png')
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    coverage_rows=[{k:r[k] for k in ('scan','points','baseline_percent','proposed_percent','credited_points')} for r in physical if r['arm']=='fitted_c']
    text=f'''# Recovering predictive curves omitted by the calibration-engine queue

The source reconciliation exposed a routing error: the predictive inclusion batch reused a selector requiring `engine_member=True`. That excludes curves omitted from the calibration engine even when they have a supported predictive-only identity. We removed this requirement for the predictive queue while preserving it for the calibration-participating route. An omitted curve still has to pass identity, physical residual, ownership, phase and numerical checks.

Of the eight largest affected curves, **{len(qualified)} qualify**, recovering **{len(rawids)} distinct GLRT points** across separate scans. No curve is forced into receiver calibration, and no GPS position selects a candidate or retry. The full goal is incomplete; this report leaves **45 additional omitted curves** from this reconciliation queue for subsequent validation and position trials.

## Source inventory and exact scope

The registry scans {rs['protocols_scanned']} study protocols and indexes {rs['indexed_trial_outputs']} position outputs, linking them to {rs['linked_curves']} of the 1,630 inventoried curves by observation IDs or explicit legacy curve IDs. It distinguishes full-curve coverage from partial overlap and calibration-participating trials from predictive-only trials. A sibling replay is not accepted as evidence for another trial: its hash must cover that trial file.

Of the 63 supported primary annotations lacking an inclusion link, **10 already have predictive trials** and **53 have no full predictive trial in the recognized saved-output schemas**. All 53 are omitted from the calibration engine. This is an inventory of the specified study and schemas, not proof that no other historical experiment exists elsewhere. Reconciliation alone awards no association credit. [The 63-record source table](supported_reconciliation.csv) and compact trial registry evidence are retained.

All eight selected captures are **adaptive**, confirmed from raw tracking metadata. Six are 10 MS/s and two are 2.5 MS/s. Filenames and inherited inventory metadata are not reliable substitutes for capture metadata. Consequently these are research-corpus adaptive recoveries, **not a DS24-fast performance evaluation**. [annotations.csv](annotations.csv) records capture mode and sample rate per case.

## Validation correction before qualification

The old three random seeds gave only **two distinct target holdouts in every selected case**. Preliminary position tests using those identities remain immutable and receive no recovery credit in this report. We then reran causal candidate nomination and identity validation with three distinct randomized scanwide 12-second partitions and two-second guards. The partition schedule is selected using timestamps alone; receiver fits exclude held/guard observations. The report independently replays target masks and verifies three distinct holdouts and the saved schedule. All eight identities remain supported. These reused scans are research validation, not a fresh independent dataset-wide generalization test.

{table(annotations,['scan','points','old_distinct_partitions','new_distinct_partitions','old_norad','new_norad','minimum_margin'])}

[partitions.csv](partitions.csv) includes actual held indices, blocks, seeds and point counts. `engine_member=False` and `active_curvature=False` remain true for all eight: this work uses their predictions while preserving the rule that they must not calibrate receiver offsets or drifts.

## Position results with matched c ablation

Each control/addition and both c arms start at the same center of a 25 × 25 km region, use the same observations apart from the explicitly added target, causal catalogue, nuisance priors and budgets. New-family inclusion integrates phase at 0.025 s and physical orbital/receiver uncertainty; a shared-family target uses the existing receiver/family information. The target does not change receiver calibration at a fixed position. GPS is used only to calculate report-time error.

{table(final,['scan','norad','points','qualified','c0_before_km','c0_after_km','fitted_c_before_km','fitted_c_after_km'])}

![Matched position comparisons](figures/position_comparison.png)

The first refreshed pass qualifies four cases. Three further cases pass residual, phase-grid, ownership and exact-orbit checks but fail optimizer completion in c=0 (one also fails its control optimizer). They receive a separate **matched Powell retry** for control/addition and both c arms, preserving observations, identities, priors, five phase rounds and the declared 48-iteration/240-evaluation budget. Selection uses numerical failures alone. The 67087 residual failure is excluded from retries. Original L-BFGS-B results are retained in [all_position_trials.csv](all_position_trials.csv), including unsuccessful optimizers. Objective effects and position errors are separate columns; scores across different observation counts are not localization accuracy.

The largest observed gains are AUTO-16634e72 / 68380 (fitted-c **1.180 → 0.654 km**) and AUTO-3dbe7ded / 65070 (**1.089 → 0.668 km**). AUTO-2366313a / 64856 adds 43 points with a small roughly 2 m error increase. Additional associations are useful evidence, but do not guarantee a better location in every scan. These improvements are separate per-scan experiments, not additive shifts or a full-dataset performance claim.

{table(coverage_rows,['scan','points','baseline_percent','proposed_percent','credited_points'])}

![Coverage: only qualified additions credited](figures/coverage.png)

The table exposes proposed coverage for rejected cases, while `credited_points` and the plotted accepted coverage remain zero/unchanged for them. Qualified additions preserve every incumbent point and exact owner; target observation sets are disjoint and checked against each control. No duplicate credit is awarded for the preliminary tests, the refreshed tests, or numerical retries.

## Native curves and residuals

![Curves 1](figures/curves_1.png)
![Curves 2](figures/curves_2.png)

The unrecovered AUTO-f122bc7e / 67087 track has only about 80–81 Hz RMS, but retains a trend (slope z ≈ 4.46), step (z ≈ 5.02), and serial correlation (≈ 0.63; limit ≈ 0.58). Low RMS and a stable identity alone do not make it consistent with the current receiver/orbit model. It is left unresolved; no drift adjustment or threshold relaxation is inferred from that target alone. [physical_checks.csv](physical_checks.csv) reports the residual tests for every final c arm.

## Reproduction and next work

The code change is in `run_supported_graph_inclusions.py` and `run_predictive_queue_inclusions.py`: predictive callers admit omitted curves, while the original calibration-only default remains. The bounded reconciled runner refreshes distinct identity validation before inclusion, and the numerical retry runner requires physical/exact checks to pass before changing optimizers. Run `reconcile_predictive_inclusion_sources.py`, then `run_reconciled_predictive_inclusions.py`, then `retry_predictive_numerical_failures.py` with the immutable study/output paths in the saved protocols. The report records the historical first pass separately from the current runner, which now requires distinct revalidation upfront.

The updated [1,630-row ledger](annotation_ledger.csv) links the eight fresh annotations and final trials without overwriting historical single-curve/group evidence. [remaining_omitted_candidates.json](remaining_omitted_candidates.json) freezes the next 45 candidates; they still require distinct identity validation, inclusion and exact replay. The older calibration-participating annotations remain a separate larger workstream. The remaining physical failure should be revisited with independent receiver/satellite witnesses, not repeated optimization.

Fourteen focused regression tests passed, including omitted-curve routing, partial-overlap exclusion, distinct-holdout validation and rejection of numerical retries when physical/ownership checks fail. No production deployment, new ALGO version, threshold relaxation or full-dataset benefit is claimed. [Execution receipts](executions.csv), [source hashes](sources.json), and [compact evidence](evidence.json.gz) accompany this iteration.
'''
    (out/'README.md').write_text(text)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('study','previous','output'):p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
