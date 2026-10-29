"""Report provisional native witnesses, common-step fits and annotation progress."""
import argparse
from collections import Counter
import csv,gzip,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from leo.analysis.research.grouped_prediction import identity_consensus


def run(args):
    s=args.study;root=s/'receiver-gap-ds24-0070-v1';out=args.output;out.mkdir(exist_ok=False);figs=out/'figures';figs.mkdir();evidence={};sources={}
    def load(p):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=r;return r
    def save_csv(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    for path,name in [(root/'raw_gap.png','raw_gap.png'),(root/'witnesses/witness_candidates.png','witness_candidates.png')]:
        shutil.copy2(path,figs/name);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    raw=load(root/'raw_points.json');wr=load(root/'witnesses/result.json');load(root/'witnesses/protocol.json');nominations=load(root/'automatic_events.json');replay=load(root/'automatic_events_replay.json')
    load(root/'prototypes-terminal.json');load(root/'prototypes/protocol.json')
    preflight=load(s/'distinct-preflight-smoke-v1/result.json');load(s/'distinct-preflight-smoke-v1/protocol.json')
    if not preflight['geometry_only_early_exit'] or preflight['folds']:raise ValueError('preflight did not skip fitting')
    if nominations['rows']!=replay['rows']:raise ValueError('automatic nomination replay changed')
    inv=load(s/'all-large-track-recovery/21e7f1fcf62970be/inventory.json');total=inv['summary'][0]['total_GLRT'];trials={};rows=[];targets=[]
    for cohort in ['prototypes-v2','automatic-prototypes']:
        load(root/(cohort+'-terminal.json'));load(root/cohort/'protocol.json')
        for p in sorted((root/cohort).glob('*.json')):
            r=load(p)
            if 'arms' not in r:continue
            name=p.stem
            if name in trials:
                for arm,v in r['arms'].items():
                    if abs(v['negative_twice_elbo']-trials[name]['arms'][arm]['negative_twice_elbo'])>1e-5:raise ValueError('duplicate control replay mismatch')
                continue
            trials[name]=r
            for arm,v in r['arms'].items():
                rows.append(dict(method=name,arm=arm,position_error_km=error(v),paired_checks=r['paired_valid'],added=v['added_points'],lost=v['lost_points'],
                    proposed_percent=100*len(v['proposed_associated_ids'])/total,target_in_fit=name!='matched_control',
                    events_hz=v['event_amplitudes_hz'],witness_objective=v['witness_conditional_objective'],witnesses_used_for_position=v['witnesses_used_for_position'],
                    witness_calibration_change=v['witness_coefficients_max_difference']))
                for t in v['targets']:
                    if t['gate']:
                        g=t['gate'];targets.append(dict(method=name,arm=arm,component=t['component'],passes=g['compatible'],
                            RMS_hz=g['conditional_residual_gate']['rms_hz'],**g['conditional_residual_gate']['diagnostics']))
    previous=load(s/'distinct-partition-family-67906-v1/inclusion/control.json')
    for arm,v in trials['matched_control']['arms'].items():
        if abs(v['negative_twice_elbo']-previous['arms'][arm]['negative_twice_elbo'])>1e-5:raise ValueError('matched control changed')
    save_csv('position_trials.csv',rows);save_csv('target_checks.csv',targets)
    witness_rows=[]
    for r in wr['rows']:
        a,b=r['fixed_family_top'][0],r['free_phase_top'][0]
        witness_rows.append(dict(branch=r['track']['key'],arm=r['arm'],points=len(r['track']['times']),existing_family=a['norad'],shared_RMS_hz=a['RMS_hz'],
            shared_offset_hz=a['offset_hz'],free_phase_family=b['norad'],free_phase_RMS_hz=b['rms_hz'],free_phase_s=b['phase_s']))
    save_csv('witness_candidates.csv',witness_rows)
    names=['matched_control','targets_no_event','targets_step65','targets_steps65_95','targets_steps65_95_predictive_witnesses','automatic_top2','automatic_all','automatic_all_predictive_witnesses']
    fig,axs=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        rr=[next(r for r in rows if r['method']==n and r['arm']==arm) for n in names]
        for i,r in enumerate(rr):ax.scatter(i,r['position_error_km'],c='#4477aa' if r['paired_checks'] else '#cc3311',marker='o' if r['paired_checks'] else 'x',s=60)
        ax.axhline(rr[0]['position_error_km'],c='black',ls='--');ax.set_xticks(range(len(rr)),[n.replace('_','\n') for n in names],fontsize=7);ax.set(title=arm,ylabel='Evaluation position error (km)');ax.grid(axis='y',alpha=.2)
    fig.suptitle('DS24-0070: better residual fit and more points do not imply better position\nCircles pass existing checks; crosses fail; all proposals remain research-only')
    fig.savefig(figs/'position_errors.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(2,1,figsize=(12,7),sharex=True,layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        for name,color in [('graph_only','#777777'),('with_provisional_witnesses','#4477aa')]:
            rr=sorted([r for r in nominations['rows'][arm][name] if r['receiver']==1],key=lambda r:r['time_s'])
            ax.plot([r['time_s'] for r in rr],[r['gain'] for r in rr],color=color,label=name)
            chosen=[r for r in rr if r['candidate']];ax.scatter([r['time_s'] for r in chosen],[r['gain'] for r in chosen],s=20,c=color)
        ax.axhline(rr[0]['search_penalty'],c='black',ls='--',label='Search penalty');ax.set(title=arm,ylabel='Proposal gain');ax.grid(alpha=.2);ax.legend(fontsize=8)
    axs[-1].set_xlabel('Candidate event time (s)');fig.suptitle('General receiver-event nomination: markers require positive same-sign support from two families')
    fig.savefig(figs/'automatic_events.png',dpi=145);plt.close(fig)
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    for col,arm in enumerate(['c0','fitted_c']):
        before=trials['targets_no_event']['arms'][arm];after=trials['automatic_all']['arms'][arm]
        for k,t in enumerate(before['targets']):
            other=after['targets'][k];color=plt.cm.tab10(k);label=t['component'].split('-RX')[-1].split('-RF')[0]
            axs[0,col].plot(t['times_s'],t['residual_hz'],'.--',alpha=.35,c=color)
            axs[0,col].plot(other['times_s'],other['residual_hz'],'.-',c=color,label='RX'+label)
        for k,t in enumerate(before['witnesses']):
            other=after['witnesses'][k];color=plt.cm.tab10(k)
            axs[1,col].plot(t['times_s'],t['residual_hz'],'.--',alpha=.35,c=color)
            axs[1,col].plot(other['times_s'],other['residual_hz'],'.-',c=color,label=t['component']+' / '+str(t['norad']))
        axs[0,col].set_title(arm+' / large target curves');axs[1,col].set_title('Witnesses withheld from position and calibration')
        for ax in axs[:,col]:ax.axhline(0,c='black',lw=.8);ax.set(xlabel='Scan time (s)',ylabel='Residual (Hz)');ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.suptitle('Dotted: no events. Solid: automatically nominated receiver events.\nWitness curves have one profiled bias for diagnostics; mean/covariance score retains bias uncertainty.')
    fig.savefig(figs/'residual_transfer.png',dpi=145);plt.close(fig)
    family_rows=[]
    for arm in ['c0','fitted_c']:
        for tau in [42.,66.,94.]:
            r=next(r for r in nominations['rows'][arm]['with_provisional_witnesses'] if r['receiver']==1 and r['time_s']==tau)
            for f in r['families']:family_rows.append(dict(arm=arm,time_s=tau,**f))
    save_csv('event_family_evidence.csv',family_rows)
    old_path=Path(__file__).resolve().parents[1]/'reports/2026_10_29_distinct_track_validation/annotation_ledger.csv';sources[str(old_path)]=hashlib.sha256(old_path.read_bytes()).hexdigest();ledger=list(csv.DictReader(old_path.open()));batch=[]
    q=s/'systematic-annotation-v1';selected=load(q/'attempt-13/selected.json');load(q/'attempt-13/protocol.json');ids={r['track_id'] for r in selected}
    for row in ledger:
        row.update(partition_policy='',geometry_only_early_exit='')
        if row['track_id'] not in ids:continue
        receipt=q/'attempt-13'/(row['track_id']+'-terminal.json');execution=load(receipt)['status'] if receipt.exists() else 'pending_or_running'
        p=q/row['track_id']/'result.json'
        if p.exists():
            r=load(p);pr=load(p.parent/'protocol.json');a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            row.update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(p),
                partition_policy='distinct timestamps',geometry_only_early_exit=r.get('geometry_only_early_exit',False),distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
        batch.append(dict(track_id=row['track_id'],scan=row['label'],execution=execution,status=row['state'],early_exit=row['geometry_only_early_exit']))
    save_csv('annotation_ledger.csv',ledger);save_csv('inventory_batch.csv',batch)
    summary=dict(inventory_total=len(ledger),inventory_assessed=sum(bool(r['annotation_source']) for r in ledger),batch_execution=dict(Counter(r['execution'] for r in batch)),
        native_witness_points=27,large_target_points=113,no_production_change=True,automatic_nomination_replay_matches=True,
        maximum_witness_calibration_change=max(r['witness_calibration_change'] for r in rows))
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    display=[dict(method=r['method'],arm=r['arm'],error_km=r['position_error_km'],added=r['added'],lost=r['lost'],proposed_percent=r['proposed_percent'],passes=r['paired_checks']) for r in rows]
    scores=[dict(method=r['method'],arm=r['arm'],witness_score=r['witness_objective'],used_in_position=r['witnesses_used_for_position']) for r in rows]
    text=f'''# DS24-0070: native witnesses resolve a calibration coverage gap

The [previous investigation](../2026_10_29_distinct_track_validation/README.md) found two large curves consistently nominating satellite 67906 but failing residual checks. This iteration finds additional native GLRT branches in the missing RX1 interval and tests shared receiver corrections. Two automatic event proposals allow both large curves to pass the existing checks with **131 proposed additional points in each c arm and no old losses**. This is a research retention result: position error does not improve, and the short witness labels and event-selection procedure are not independently validated for production.

## Evidence outside the original graph

DS24-0070 is the same recording as DS25-0051. Its source export has {total} GLRT winners. The shaded interval has no retained other-family RX1 calibration observations, but it is not empty of measurements. Gray points are associated, red unassociated graph points, blue outside the graph.

![Raw native GLRT](figures/raw_gap.png)

Four branches were explicitly delineated from this plot before the causal catalogue screen. Their time/frequency windows and exact observation IDs are archived. This manual discovery step is not yet a systematic branch finder. The early CH3 graph fragment nominates a new family and is excluded from witness use. Three other branches, 27 points total, agree between an existing shared-family prediction and a complete-causal-catalogue/free-phase screen: CH3 during 61–76 s and CH4 during 54–62 s nominate 65647; the lower CH4 branch nominates 69190. Both families already have support elsewhere in this scan. Short arcs can still be ambiguous; these are provisional identities, not confirmed satellites.

{table(witness_rows,list(witness_rows[0]))}

![Witness orbit fits](figures/witness_candidates.png)

## Controlled receiver hypotheses

Start with the same 25 × 25 km regional box and existing inferred priors, at the regional center (37.906, -122.545). Keep causal TLEs, fixed aliases and satellite nominations, original noise weights, five phase refreshes, 48 position iterations, and matched c=0/fitted-c arms. Add an RX1 step proportional to RF frequency with Gaussian prior SD 200 Hz at 11.5 GHz. Initial diagnostic times were 65 and 95 s, read from residuals, not from evaluation error. The evaluation-only site is 37.849061591561885, -122.48574968092912.

Short witnesses never enter calibration normal equations. The first tests withhold them from position fitting too, then evaluate their joint conditional density with shared calibration covariance. Separate variants let them influence position through predictive likelihood only. At a fixed endpoint, the maximum recorded calibration-coefficient change when attaching witnesses is {summary['maximum_witness_calibration_change']:.1f}; moving position can still change the curved-data posterior. The unchanged control and no-event target fit replay earlier objectives within 1e-5. An initial trial stopped on missing legacy graph indices for appended native observations; the corrected implementation restricts legacy postfit extension to the original graph, with witnesses counted only through explicit predictive entries. The failed execution receipt is archived.

{table(display,list(display[0]))}

![Position results](figures/position_errors.png)

“Added” and coverage are proposal memberships, including proposals rejected by checks. Even passing proposals are not deployed or added to production totals. GPS at the previously confirmed site is used only for this error table. The two automatic events give fitted-c error about 0.821 km versus 0.809 km for the matched control. The no-event target fit has smaller error but fails residual checks; choosing it because of GPS would be invalid.

## General event nomination

The reusable array-only detector scans 10–290 s at 2 s spacing for both receivers. It removes a per-curve affine component for proposal scoring only, requires at least three points on each side, uses fixed 150 Hz observation noise and a 200 Hz event prior, and applies a search penalty 2 log(number of time/receiver opportunities). A proposal requires positive same-sign marginal support from at least two distinct satellite families, not merely two channels of one family. The proposal does not calibrate from those removed affine terms.

The c0 proposals, shared unchanged across both arms, nominate 66 s, 94 s and 42 s in descending gain with 10 s minimum separation. We test the top two and all three (predeclared maximum three). Without the new branches, 66 s fails the two-family rule; with the provisional 65647 witness it becomes a candidate. No evaluation position or error enters this selection. The generic driver exactly replays the original nomination arrays.

![Automatic event scores](figures/automatic_events.png)

**Cross-family evidence is suggestive, not strong identification of a physical receiver step.** The supporting family at 66 s has only about 0.21 marginal gain under this affine-eliminated proposal score; 67906 supplies most of the gain. Supporting families at 42 and 94 s contribute about 1.7 and 1.45. The positive-gain rule is deliberately a discovery filter, not an acceptance confidence threshold or calibrated probability. Events, branches and identities were investigated on this scan; the witness test is conditional and not a blind end-to-end validation. Timing errors or other common RX1 discrepancies remain alternative explanations.

{table(family_rows,list(family_rows[0]))}

## Transfer to the separate-satellite witnesses

The first step improves the conditional witness score by about 19–20 units relative to the no-event target fit even when witness points are excluded from position and calibration. This uses the full covariance and log determinant, not only RMS. Lower scores are better within these matched observations. Scores for variants using witnesses in position are in-sample for position and explicitly marked.

{table(scores,list(scores[0]))}

![Target and witness residuals](figures/residual_transfer.png)

This explains how shared receiver discrepancies can cause apparently good satellite curves to be dropped. It does not demonstrate a more accurate location: additional fitted freedom can recover observations while weakening or shifting the position constraint. The next validation should nominate events using one set of whole families or random guarded blocks, evaluate untouched families/blocks, and compare receiver-frequency versus timing-error models with the same candidate budget. A scan-wide automatic native-branch extractor is still needed to replace the four diagnostic windows.

## Systematic inventory progress

The inventory contains {len(ledger)} large graph tracks, with {summary['inventory_assessed']} explicit annotation outcomes in this snapshot. A new 24-case bounded batch uses the distinct timestamp-only schedule directly. It preserves existing claims and recordings. If three distinct usable target holdouts cannot be found in the frozen 67-seed pool, it records insufficient support before satellite fitting; it does not weaken temporal guards or label a timeout as a valid identity. Existing protocols remain unchanged, and the new per-attempt policy is recorded explicitly.

Batch execution snapshot: {summary['batch_execution']}. The full goal remains active; a coherent untracked native curve is still outside the graph-track inventory until explicitly inventoried. No ALGO version or production model is promoted here.

The real-data preflight check on DS24-0015 track b7bed1110f091b43184e returns insufficient geometry in {preflight['seconds']:.2f} seconds, with zero satellite-fit folds. Its previous execution reached the 600-second cap under the older schedule. These are different validation schedules, not a matched inference-speed benchmark. Twenty-nine focused tests passed, including synthetic multi-family events, opposite-sign counterexamples, witness non-calibration/duplicate-ID checks and timestamp-only partition scheduling.

Reproduction tools: `investigate_receiver_gap_witnesses.py`, `nominate_shared_receiver_events.py`, `probe_receiver_gap_recovery.py`, and `report_receiver_gap_recovery.py`. The exact input paths, observation IDs, frozen hypotheses, commands and execution receipts are archived. See [position trials](position_trials.csv), [target checks](target_checks.csv), [family event evidence](event_family_evidence.csv), [ledger](annotation_ledger.csv), [batch](inventory_batch.csv), [source hashes](sources.json), and [compressed evidence](evidence.json.gz).
'''
    (out/'README.md').write_text(text)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
