"""Publish a bounded graph inventory iteration and native ambiguity audit."""
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
from debug_fast_graph_unassociated import read, write
from leo.analysis.research.grouped_prediction import identity_consensus
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir()
    repo=Path(__file__).resolve().parents[1];sources={};evidence={}
    def load(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        r=read(path);evidence[str(path)]=r;return r
    def csvread(path):
        path=Path(path);sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return list(csv.DictReader(path.open()))
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    queue=args.study/'systematic-annotation-v1'
    ledger=csvread(repo/'reports/2026_10_29_flagged_native_inventory/annotation_ledger.csv')
    byid={r['track_id']:r for r in ledger};batch=[]
    for attempt in args.attempts:
        load(queue/attempt/'protocol.json')
        for row in load(queue/attempt/'selected.json'):
            tid=row['track_id'];terminal=load(queue/attempt/(tid+'-terminal.json'))
            if terminal['status']!='complete':raise ValueError('incomplete annotation; retain as execution limitation')
            path=queue/tid/'result.json';r=load(path);load(path.parent/'protocol.json')
            a=identity_consensus(r['folds'],score_name=r.get('identity_score_name','joint'))
            byid[tid].update(state=a['status'],norad=a.get('norad'),minimum_margin=a.get('minimum_margin'),
                annotation_source=str(path),partition_policy='distinct timestamps',
                geometry_only_early_exit=r.get('geometry_only_early_exit',False),
                distinct_schedule_ready=not r.get('geometry_only_early_exit',False))
            batch.append(dict(scan=row['label'],track_id=tid,points=row['points'],status=a['status'],norad=a.get('norad'),minimum_margin=a.get('minimum_margin')))
    csvout('annotation_ledger.csv',ledger);csvout('batch_annotations.csv',batch)
    trials=[];gallery=[]
    for folder in args.inclusions:
        protocol=load(folder/'protocol.json')
        for job in protocol['jobs']:
            tid=job['track_id'];terminal=load(folder/(tid+'-terminal.json'))
            if terminal['status']!='complete':raise ValueError('inclusion execution incomplete')
            trial=load(folder/tid/'target_0.json');control=load(folder/tid/'control.json');load(folder/tid/'protocol.json')
            fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for col,arm in enumerate(('c0','fitted_c')):
                v=trial['arms'][arm];c=control['arms'][arm];d=v['targets'][0];target=d['component'];gate=d['gate'];res=gate['conditional_residual_gate']
                failed_old=[q['component'] for q in v['gates']['tracks'] if not q['compatible'] and q['component']!=target]
                failed_pred=[q['component'] for q in v['linear_gates'] if not q['compatible']]
                trials.append(dict(scan=job['label'],track_id=tid,arm=arm,norad=job['annotation']['norad'],passes=trial['paired_valid'],
                    control_passes=control['paired_valid'],before_km=error(c),after_km=error(v),added=v['added_points'],lost=v['lost_points'],
                    target_passes=gate['compatible'],target_RMS_hz=res['rms_hz'],target_diagnostics=json.dumps(res['diagnostics'],sort_keys=True),
                    failed_old_curved=';'.join(failed_old),failed_old_predictive=';'.join(failed_pred),phase_change_s=v['final_phase_change_s']))
                t=d['times_s'];axs[0,col].scatter(t,np.array(d['CFO_hz'])/1000,s=12,label='GLRT with fixed alias')
                axs[0,col].plot(t,np.array(d['predicted_CFO_hz'])/1000,label='Causal orbit + receiver',c='#cc3311')
                axs[1,col].plot(t,d['residual_hz'],'.-',ms=3);axs[1,col].axhline(0,c='black',lw=.5)
                axs[0,col].set(title=arm,ylabel='CFO (kHz)');axs[1,col].set(xlabel='Scan time (s)',ylabel='Residual (Hz)',title=f"RMS {res['rms_hz']:.1f} Hz; target pass {gate['compatible']}")
                axs[0,col].legend(fontsize=8)
                for ax in axs[:,col]:ax.grid(alpha=.2)
            fig.suptitle(f"{job['label']} / {target} → {job['annotation']['norad']}\nWhole-track inclusion {'PASSES' if trial['paired_valid'] else 'REJECTED'}; existing evidence must also remain compatible")
            fig.savefig(figs/(tid+'.png'),dpi=135);plt.close(fig)
            gallery.append(f"### {job['label']} / {tid}\n\n![CFO and residual](figures/{tid}.png)\n")
    csvout('position_trials.csv',trials)
    witness_rows=[];witness_gallery=[]
    if args.witnesses:
        witness_evidence=load(args.witnesses/'result.json')
        for item in witness_evidence['results']:
            fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
            for arm,v in item['arms'].items():
                for name,g in v['groups'].items():
                    witness_rows.append(dict(scan=item['scan'],track_id=item['track_id'],arm=arm,group=name,
                        supported_bins=len(g['bins']),correlation=g['correlation'],control_objective_delta=v['control_objective_delta']))
            v=item['arms']['fitted_c'];target=v['target']
            for ax,(name,g) in zip(axs.flat,v['groups'].items(),strict=True):
                ax.plot(target['times_s'],target['residual_hz'],'.-',c='#cc3311',ms=3,lw=.7,alpha=.6,label='Target after proposed inclusion')
                for w in g['witnesses']:
                    ax.scatter(w['times_s'],w['residual_hz'],s=5,c='0.65',alpha=.4)
                bins=g['bins']
                ax.plot([b['time_s'] for b in bins],[b['target_hz'] for b in bins],'o-',c='#cc3311',label='Target 5 s bin median')
                ax.plot([b['time_s'] for b in bins],[b['witness_hz'] for b in bins],'s-',c='#4477aa',label='Independent-family control median')
                rho='unavailable' if g['correlation'] is None else f"{g['correlation']:.2f}"
                ax.set(title=f"{name}: {len(bins)} supported bins, r={rho}",xlabel='Scan time (s)',ylabel='Residual (Hz)');ax.grid(alpha=.2);ax.axhline(0,c='black',lw=.5)
            axs[0,0].legend(fontsize=7)
            fig.suptitle(f"{item['scan']} / independent satellites only; fitted-c\nControl residuals exclude target family; ≥2 witness families and ≥3 points per bin")
            fig.savefig(figs/(item['track_id']+'_witnesses.png'),dpi=140);plt.close(fig)
            witness_gallery.append(f"### {item['scan']}\n\n![Independent receiver witnesses](figures/{item['track_id']}_witnesses.png)\n")
        csvout('receiver_witnesses.csv',witness_rows)
        (out/'witness_gallery.md').write_text('# Independent-family residual comparisons\n\n'+'\n'.join(witness_gallery))
    # Audit stored predictions without changing their means, covariance or scores.
    native=csvread(repo/'reports/2026_10_29_native_all_large_policy/all_large_annotations.csv');ambiguous=[];folds=[]
    for row in native:
        if row['status']!='ambiguous_identity':continue
        r=load(Path(row['source'])/'result.json');load(Path(row['source'])/'protocol.json');score=r['identity_score_name'];rr=[]
        for fold in r['folds']:
            for arm in ('c0','fitted_c'):
                ordered=sorted(fold['proposals'],key=lambda q:q['arms'][arm]['scores'][score]['negative_twice_log_density'])
                best,second=ordered[:2];a,b=[q['arms'][arm] for q in (best,second)];sa,sb=[v['scores'][score] for v in (a,b)]
                rr.append(dict(scan=row['scan'],branch_id=row['branch_id'],points=int(row['points']),seed=fold['seed'],arm=arm,
                    winner=best['norad'],runner_up=second['norad'],margin=sb['negative_twice_log_density']-sa['negative_twice_log_density'],
                    winner_RMS_hz=sa['rms_hz'],runner_up_RMS_hz=sb['rms_hz'],
                    winner_sigma_hz=float(np.median(sa['prediction_sigma_hz'])),runner_up_sigma_hz=float(np.median(sb['prediction_sigma_hz'])),
                    winner_phase_s=a['target_phase_training_mean_s'],runner_up_phase_s=b['target_phase_training_mean_s']))
        folds.extend(rr);ambiguous.append(min(rr,key=lambda q:q['margin']))
    csvout('ambiguity_weakest_partition.csv',ambiguous);csvout('ambiguity_all_partitions.csv',folds)
    fig,axs=plt.subplots(1,2,figsize=(13,5),layout='constrained');x=np.arange(len(ambiguous))
    labels=[r['scan'].replace('DS24-','')+' / '+r['branch_id'][:4] for r in ambiguous]
    axs[0].plot(x,[r['winner_RMS_hz'] for r in ambiguous],'o',label='Winning candidate')
    axs[0].plot(x,[r['runner_up_RMS_hz'] for r in ambiguous],'s',label='Runner-up')
    axs[0].plot(x,[r['winner_sigma_hz'] for r in ambiguous],'_',label='Median predictive σ (winner)')
    axs[0].set_ylabel('Held residual RMS / predictive σ (Hz)');axs[0].legend(fontsize=8)
    axs[1].bar(x,[r['margin'] for r in ambiguous]);axs[1].axhline(10,c='black',ls='--',label='Required advantage');axs[1].legend();axs[1].set_ylabel('Runner-up score − winning score')
    for ax in axs:ax.set_xticks(x,labels,rotation=90);ax.grid(axis='y',alpha=.2)
    fig.suptitle('All 17 ambiguous native proposals: weakest partition across both c arms\nLow residual alone does not establish a unique satellite identity; no score changes here')
    fig.savefig(figs/'native_ambiguity.png',dpi=140);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
    for arm,marker in [('c0','o'),('fitted_c','s')]:
        rr=[r for r in trials if r['arm']==arm]
        ax.plot(range(len(rr)),[1000*(r['after_km']-r['before_km']) for r in rr],marker,ls='none',label=arm)
    names=[r['scan']+(' [pass]' if r['passes'] else ' [rejected]') for r in trials if r['arm']=='fitted_c']
    ax.set_xticks(range(len(names)),names,rotation=30,ha='right');ax.set_ylabel('Proposed position-error change (m)');ax.axhline(0,c='black',lw=.6);ax.legend();ax.grid(alpha=.2)
    ax.set_title('Independent whole-track inclusion trials; negative is better\nRejected trial endpoints are diagnostic, not accepted results')
    fig.savefig(figs/'graph_position_changes.png',dpi=140);plt.close(fig)
    summary=dict(batch_tracks=len(batch),batch_outcomes=dict(Counter(r['status'] for r in batch)),
        original_inventory=len(ledger),assessed=sum(bool(r['annotation_source']) for r in ledger),inclusion_trials=len(trials)//2,
        passing_trials=sum(r['passes'] for r in trials if r['arm']=='fitted_c'),ambiguous_native=len(ambiguous),no_production_change=True)
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    (out/'gallery.md').write_text('# Graph inclusion diagnostics\n\n'+'\n'.join(gallery))
    md=f"""# Large-track recovery: next graph batch and remaining native ambiguity

The [joint native recovery policy](../2026_10_29_native_all_large_policy/README.md) adds 1,101 unique points across 27 of 93 available DS24 scans. Fitted-c coverage increases 72.070% → 72.584%; mean error changes 1.475 → 1.472 km, with unchanged 1.190 km median. Nine missing DS24 exports remain outside that cohort. This iteration advances the broader graph-track inventory and examines why strong-looking native curves can still lack a unique satellite ID.

## Original graph inventory

The next **{len(batch)}** frozen graph annotations completed: {summary['batch_outcomes']}. The ledger now records **{summary['assessed']} / {len(ledger)}** assessed entries. These are graph tracks from the wider recording inventory, separate from the 93 native DS24 proposals. Assessments are conditional on the frozen graph, incumbent associations and searched causal catalogue; supported identity is not an inclusion authorization.

{table(batch,['scan','points','status','norad','minimum_margin'])}

## Carry identities through to position

All five supported engine-member nominations from the preceding eight-track batch receive matched original-model inclusion trials. **{summary['passing_trials']} / {summary['inclusion_trials']} pass.** Trials keep the original noise model, physical priors, existing observations, regional start, five phase-refresh rounds and 48 iterations per round. Both c arms use the same target identity and observations. No failed old association may be silently removed. Original observations and causal candidates are unchanged.

{table(trials,['scan','arm','passes','before_km','after_km','added','lost','target_passes','target_RMS_hz'])}

![Position effects](figures/graph_position_changes.png)

An identity can win randomized held-block comparisons and still fail the full shared fit: the winning candidate is relative to competitors, while inclusion also requires absolute residual quality and consistency with existing curves. The [complete trial table](position_trials.csv) records target diagnostics, failed old curved/predictive components, phase convergence and point loss. The [CFO/residual gallery](gallery.md) shows every inclusion trial. Rejected errors and point counts remain diagnostic and are never included in accepted coverage.

## Evidence for a receiver discrepancy

The matched controls were replayed without changing their fits, and compared against each proposed target's residuals. Witnesses contain only originally retained curved tracks from **other satellites**, excluding the target's entire family. Five-second bins require at least two witness families and three witness points. This is a descriptive check, not a new acceptance rule or an independent position trial. Predictive-only witness curves are not included in this first audit.

AUTO-d9185bf9 is informative: the rejected RX1 CH6 target's binned residuals correlate at about **0.90** with other satellite families on RX1's other band, across eight supported bins. The corresponding RX2 comparison is about **−0.25** over eleven bins, with visibly different time coverage. RX1's independent witnesses show the negative excursion near 22–28 s and positive residuals near 32–43 s; RX2 witnesses remain much closer to zero. This supports testing a receiver-common time-varying frequency discrepancy before changing the target satellite's orbit. Shared calibration and different temporal coverage prevent interpreting this as proof of receiver hardware error.

![RX1 versus RX2 independent witnesses](figures/d1c38aa3c6a00ccc5b41_witnesses.png)

Other scans differ. AUTO-453faf4c has same-receiver/same-band correlation about 0.83 across six bins, but RX2 also has correlated structure; AUTO-8d229584 lacks bins with two independent witness families, so this test cannot identify its cause. The [full witness gallery](witness_gallery.md) and [numeric table](receiver_witnesses.csv) retain both c arms, all groups and unsupported cases. A follow-up correction must be learned from other families alone, tested on held families/blocks, and propagated through matched position fits; no receiver correction is accepted here.

## Why 17 native proposals remain ambiguous

Every ambiguous proposal has a consistent winning identity but lacks the required score advantage of 10 in at least one of the three randomized block partitions and two c arms. We report the weakest partition without changing its score. The predictive-only model fixes white-noise variance at `2 × 150² Hz²` (about 212 Hz standard deviation), then adds calibration/orbit uncertainty and a 300 Hz track-bias prior. Conditioning on training observations reduces correlated uncertainty but retains this white-noise term. Consequently a visually cleaner winner can have only a small predictive advantage.

![Native ambiguity](figures/native_ambiguity.png)

For DS24-0014's 82-point proposal, fitted-c held RMS is about 26 Hz for 69509 versus 95 Hz for 67952 in the decisive partition; the score advantage is only about 2.5. Other partitions strongly exclude their tested alternatives. The runner-up uses about +13.8 s phase versus −1.7 s for 69509. These are competing physical explanations under the current priors, not proof that either identity is correct. DS24-0089's 61-point proposal has a harder partition: 69255 gives about 31 Hz versus 48 Hz for 53833, with advantage about 0.71. Different tracks therefore face different degrees of ambiguity.

The covariance scale is a plausible bottleneck, not a validated correction. Reducing it because a chosen satellite fits well would risk circular confidence. The next controlled experiment should estimate a receiver/band noise distribution using training-only independent evidence, retain a model-discrepancy term, rerun all competitors with the same randomized partitions, and test whether discrimination and calibration improve together. A second experiment should pool nonoverlapping cross-channel evidence with shared satellite phase/orbit and receiver covariance, counting repeated points only once. Scores from overlapping branches must never be summed as independent votes. Candidate unions across partitions should be retained so a near-degenerate alternative is tested throughout.

## Audit and limits

New annotations randomize whole 12 s blocks with 2 s guards and three distinct timestamp-selected holdout sets. GPS is used only by this report's position-error calculation at the previously confirmed evaluation site; it does not select hypotheses. No future TLE, new RF collection, gate relaxation, production change or ALGO promotion is involved. Annotation jobs have 600 s caps and 16 workers; the five inclusion jobs have 600 s caps and five workers. This is a bounded iteration, not completion of the full 1,630-track objective.

Reproduce annotations with `run_annotation_inventory.py run --limit 24 --workers 16 --distinct-partitions`; inclusion with `run_supported_graph_inclusions.py --attempts attempt-14 --workers 5`; then run `report_graph_recovery_iteration.py` with the frozen queue and inclusion directories. [Full graph ledger](annotation_ledger.csv), [all native ambiguity partitions](ambiguity_all_partitions.csv), [source hashes](sources.json), and [compressed evidence](evidence.json.gz) retain provenance. No new likelihood or optimizer behavior is introduced by the runner or report.
"""
    (out/'README.md').write_text(md);print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--attempts',nargs='+',required=True);p.add_argument('--inclusions',type=Path,nargs='+',required=True)
    p.add_argument('--witnesses',type=Path,required=True)
    run(p.parse_args())
