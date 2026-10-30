"""Publish bidirectional family prediction, candidate challenge and batch four."""
import argparse,csv,gzip,hashlib,json,shutil
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read,write
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence
from report_predictive_covariance_transfer import compact_replays


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir();s=args.study;hashes={};evidence={}
    def load(path):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=compact_replays(compact_evidence(r));return r
    def csvout(name,rows):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)),lineterminator='\n');w.writeheader();w.writerows(rows)
    def save(fig,name):fig.savefig(out/'figures'/name,dpi=145);plt.close(fig)
    results=[]
    for version in (1,2):
        root=s/f'ch7-bidirectional-family-validation-v{version}';terminal=load(root/'execution.json')
        if terminal['status']!='complete':raise ValueError('family validation incomplete')
        load(root/'analysis/protocol.json');results.append(load(root/'analysis/result.json'))
    old,new=results;rows=[];tracks=[];grid=[];phase=[]
    for f,g in zip(new['folds'],old['folds'],strict=True):
        if f['seed']!=g['seed'] or f['split']!=g['split']:raise ValueError('quadrature comparison changed partition')
        for arm,v in f['arms'].items():
            scores=v['scores'];base=scores['family_to_family'];combined=scores['combined_to_family'];bias=v['bias_only_projection']
            rows.append(dict(seed=f['seed'],arm=arm,target_held_points=len(scores['family_to_target']['held_indices']),incumbent_held_points=len(base['held_indices']),
                family_to_target_RMS_hz=scores['family_to_target']['rms_hz'],target_bias_only_RMS_hz=bias['rms_hz'],target_bias_hz=bias['bias_hz'],
                target_only_RMS_hz=scores['target_to_target']['rms_hz'],combined_target_RMS_hz=scores['combined_to_target']['rms_hz'],
                incumbent_before_RMS_hz=base['rms_hz'],incumbent_after_RMS_hz=combined['rms_hz'],
                incumbent_density_gain=base['negative_twice_log_density']-combined['negative_twice_log_density']))
            for name,z in scores.items():
                prior=g['arms'][arm]['scores'][name]
                if z['held_indices']!=prior['held_indices']:raise ValueError('changed held observations')
                grid.append(dict(seed=f['seed'],arm=arm,score=name,density_change=z['negative_twice_log_density']-prior['negative_twice_log_density'],RMS_change_hz=z['rms_hz']-prior['rms_hz']))
                w=np.array(z['training_mixture_weights']);ph=np.linspace(-15,15,len(w));mu=w@ph
                phase.append(dict(seed=f['seed'],arm=arm,score=name,phase_mean_s=float(mu),phase_sigma_s=float(np.sqrt(w@(ph-mu)**2))))
            for t in v['per_incumbent_track']:
                a,b=t['scores']['family'],t['scores']['combined']
                tracks.append(dict(seed=f['seed'],arm=arm,component=t['component'],held_points=len(t['held_indices']),
                    before_RMS_hz=a['rms_hz'],after_RMS_hz=b['rms_hz'],density_gain=a['negative_twice_log_density']-b['negative_twice_log_density']))
    csvout('prediction_metrics.csv',rows);csvout('incumbent_tracks.csv',tracks);csvout('grid_sensitivity.csv',grid);csvout('phase_predictions.csv',phase)
    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained');x=np.arange(len(rows));labels=[str(r['seed'])+'\n'+r['arm'] for r in rows]
    for key,label in [('family_to_target_RMS_hz','Family only'),('target_bias_only_RMS_hz','Target constant bias only'),('combined_target_RMS_hz','Full conditional target training')]:axes[0,0].plot(x,[r[key] for r in rows],'o-',label=label)
    axes[0,0].set_ylabel('Target held RMS (Hz)');axes[0,0].legend(fontsize=8)
    for key,label in [('incumbent_before_RMS_hz','Without target training'),('incumbent_after_RMS_hz','With target training')]:axes[0,1].plot(x,[r[key] for r in rows],'o-',label=label)
    axes[0,1].set_ylabel('Incumbent held RMS (Hz)');axes[0,1].legend(fontsize=8)
    axes[1,0].bar(x,[r['incumbent_density_gain']/r['incumbent_held_points'] for r in rows]);axes[1,0].axhline(0,c='k',lw=.6);axes[1,0].set_ylabel('Held-family −2 log density gain / point\nPositive favors target training')
    for name,label in [('family_to_target','Family only'),('target_to_target','Target only'),('combined_to_target','Combined')]:
        lookup={(r['seed'],r['arm']):r for r in phase if r['score']==name}
        axes[1,1].plot(x,[lookup[r['seed'],r['arm']]['phase_mean_s'] for r in rows],'o-',label=label)
    axes[1,1].set_ylabel('Training phase mean (s)');axes[1,1].legend(fontsize=8)
    for ax in axes.flat:ax.set_xticks(x,labels,fontsize=7);ax.grid(alpha=.2)
    save(fig,'bidirectional_prediction.png')
    fig,axes=plt.subplots(3,2,figsize=(13,10),layout='constrained');times=np.array(new['times_s'])
    for fi,f in enumerate(new['folds']):
        for ci,receiver in enumerate(('RX1','RX2')):
            ax=axes[fi,ci];t=next(t for t in f['arms']['fitted_c']['per_incumbent_track'] if '-'+receiver+'-CH6-' in t['component']);tt=times[t['held_indices']]
            for name,label in [('family','Without CH7 training'),('combined','With CH7 training')]:ax.plot(tt,t['scores'][name]['held_residual_hz'],'o-',lw=.7,label=label)
            ax.axhline(0,c='k',lw=.5);ax.grid(alpha=.2);ax.set(title=f"Seed {f['seed']} / {receiver} CH6 / {len(tt)} held points",xlabel='Scan time (s)',ylabel='Held residual (Hz)');ax.legend(fontsize=7)
    save(fig,'held_ch6_residuals.png')
    members=[];offset=0
    for e in new['entries']:
        t=times[offset:offset+e['points']];offset+=e['points'];members.append(dict(component=e['component'],points=e['points'],role=e['role'],start_s=float(t.min()),end_s=float(t.max())))
    csvout('family_members.csv',members)
    wide_root=s/'ch7-wide-identity-challenge-v1';terminal=load(wide_root/'execution.json')
    if terminal['status']!='complete':raise ValueError('wide candidate challenge incomplete')
    wide=load(wide_root/'analysis/result.json');load(wide_root/'analysis/protocol.json')
    candidates=sorted({p['norad'] for f in wide['folds'] for p in f['proposals']});counts=[len(f['proposals']) for f in wide['folds']]
    batch=load(args.previous/'summary.json');ledger_path=args.previous/'annotation_ledger.csv';hashes[str(ledger_path)]=hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    ledger=list(csv.DictReader(ledger_path.open()))
    for r in ledger:
        if r['track_id']=='bfdf8ca6908647a6187d':r.update(shared_family_prediction_source=str(s/'ch7-bidirectional-family-validation-v2/analysis/result.json'),shared_family_prediction_status='unresolved: target training worsens held incumbent prediction in two of three folds in both c arms',wide_identity_source=str(wide_root/'analysis/result.json'))
    csvout('annotation_ledger.csv',ledger);shutil.copyfile(args.previous/'remaining_role_candidates.json',out/'remaining_role_candidates.json')
    scope=load(s/'reconciled-role-membership-scope-v4/b7c6003c563acefeef96.json');write(out/'target_membership_scope.json',scope)
    comparisons=list(csv.DictReader((args.previous/'comparisons.csv').open()));csvout('batch_position_comparisons.csv',comparisons)
    write(out/'summary.json',dict(batch=batch,shared_family_recovery_accepted=False,wide_identity=wide['annotation'],candidate_counts=counts,candidate_union=candidates,
        maximum_density_grid_change=max(abs(r['density_change']) for r in grid),maximum_RMS_grid_change_hz=max(abs(r['RMS_change_hz']) for r in grid),production_changed=False,goal_complete=False))
    write(out/'sources.json',hashes)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f,separators=(',',':'))
    (out/'README.md').write_text(f'''# Shared-family prediction: target self-prediction is insufficient

The 77-point AUTO-afec5a1f RX1 CH7 curve still favors satellite **59632** among the nominated causal candidates. A new bidirectional test exposes why that does not justify inclusion: target training improves its own prediction while degrading held observations on both receivers in two of three randomized partitions. The third partition improves. This is evidence of unresolved shared-model tension, not proof that the target or an incumbent identity is wrong.

## Receiver and position are trained without the challenged family

All 59632 observations are excluded from receiver and position calibration. All predictive-only rows are excluded from calibration as well. Each arm starts at the same 25 × 25 km regional box center and uses only other families' training blocks, fixed 150 Hz noise, unit confidence powers and existing causal priors. Graph construction and other family identities remain frozen conditioning assumptions. The same three distinct randomized scanwide 12-second block holdouts, with two-second guards, are replayed from the target annotation. This is conditional model validation, not a fresh end-to-end acquisition benchmark or a new position-error comparison.

One shared phase/orbit distribution and one receiver covariance connect the retained family observations; every track retains its own existing 300 Hz constant-bias prior. Target training may condition this joint predictive distribution but never changes the independently fitted calibration output. Held values enter scoring only.

{table(members,['component','points','role','start_s','end_s'])}

## Bidirectional held prediction

{table([r for r in rows if r['arm']=='fitted_c'],['seed','target_held_points','incumbent_held_points','target_bias_only_RMS_hz','combined_target_RMS_hz','incumbent_before_RMS_hz','incumbent_after_RMS_hz','incumbent_density_gain'])}

![Bidirectional prediction and phase behavior](figures/bidirectional_prediction.png)

Without any CH7 training, family-to-target RMS is about 1 kHz, much of it a constant offset; it must not be interpreted wholly as shape error. A diagnostic projection lets only the existing target constant bias update from target training values, leaving shared means and phase weights unchanged. Its fitted-c held RMS remains **520, 307 and 482 Hz**, versus **239, 96 and 333 Hz** with full conditional updates. This restricted projection is a diagnostic, not a normalized predictive density or an acceptance rule.

Full target conditioning worsens held-family RMS from **51→117 Hz** and **43→120 Hz** in the first two folds; the third improves **67→61 Hz**. Joint held-family density changes have the same signs in both c arms. Their magnitudes are modest and the folds share data, so no significance or calibrated false-association probability is claimed. Per-track scores are diagnostic marginals and are not summed as independent evidence.

![Held CH6 evidence on both receivers](figures/held_ch6_residuals.png)

The first two folds degrade CH6 prediction on both receivers. The third fold has only one held RX1 CH6 point, which limits that comparison. This pattern does not isolate a receiver-specific fault. A target-only held score can look adequate because target training estimates correlated nuisance terms; joint held-family prediction detects the resulting tradeoff.

## Candidate and numerical challenges

Raising the candidate cap from 3 to 12 yields **{counts} candidates per fold**, with union **{candidates}**. The nominator did not produce twelve distinct candidates in each fold; this is not exhaustive enumeration of every satellite. 59632 remains the winner in every fold and c arm, with minimum margin **{wide['annotation']['minimum_margin']:.2f}**. Candidate 53750 remains the nearest tested challenger. A broader cap alone does not resolve the family inconsistency.

Halving phase spacing from 0.1 to 0.05 s preserves the partitions and conclusions. The largest change in total held density score is **{max(abs(r['density_change']) for r in grid):.4f}** and the largest held RMS change is **{max(abs(r['RMS_change_hz']) for r in grid):.3f} Hz**. This is a sensitivity check, not a global numerical-error bound. Both runs and the wider search completed within their 600-second stage budgets.

## Inventory progress and scoped recovery

The [fourth predictive-role batch](../2026_10_30_predictive_role_reassessment_batch4/README.md) assesses another 16 curves: six supported identities, eight unstable, one ambiguous and one prediction mismatch. All acquisitions in this batch are verified fast recordings. All six supported curves receive full position trials. Two curves totaling **146 target points** qualify in separate matched trials; this is not one simultaneous solution or a dataset-wide gain. One otherwise-valid trial requires a matched Powell retry; all original outcomes are preserved. **{batch['remaining_role_candidates']} older-role cases remain**.

The other qualifying curve is AUTO-bf77eb5c / 59362, with **71 points**. Its error improves **1.111→0.861 km (c=0)** and **1.112→0.861 km (fitted-c)**, with no unvalidated incidental point gain. Every qualified and rejected comparison is preserved in [batch_position_comparisons.csv](batch_position_comparisons.csv).

The 75-point AUTO-f08da5cb / 63906 target passes RF, phase and exact ownership checks after that retry. Matched position errors improve **5.565→4.912 km (c=0)** and **5.824→4.927 km (fitted-c)**, still far from the localization goal. At the fitted-c endpoint, the standard extension step also discovers 28 RX2 CH4 points labeled 58528. Those points never entered the fit and have not received this target's independent annotation. The [membership-scope audit](target_membership_scope.json) therefore reports **75 validated candidate points in each arm**, retaining those 28 as unvalidated discoveries. No measurements, position objective or saved raw trial are changed. No 103-point validated recovery is claimed.

The [latest ledger](annotation_ledger.csv) preserves previous rejections and marks CH7's shared-family consistency unresolved. Both recoveries are research candidates, not production promotion or a dataset-wide accuracy gain. Next work should test independently supported channel/receiver model corrections and challenge incumbent family identities jointly; it should not loosen gates merely because a target predicts itself.

Nine focused tests pass, covering held-data isolation, family exclusion, exact point scope, Gaussian prediction and gate reporting. Source hashes, compressed evidence, grid changes and all c-arm metrics accompany this report. No future TLE or evaluation GPS enters these fits. The full annotation-and-inclusion goal remains active.
''')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','previous','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
