"""Append causal identity competition to the frozen-receiver report."""
import argparse
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
from report_predictive_track_annotation import table


def joint_report(args):
    out=args.report;sources={};evidence={};summary=[];rows=[];executions=[];figures=[]
    def load(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    for job in load(args.study/'protocol.json')['jobs']:
        tid=job['track_id'];terminal=load(args.study/(tid+'-terminal.json'))
        executions.append(dict(scan=job['label'],status=terminal['status'],seconds=terminal['seconds'],reason=terminal.get('reason')))
        if terminal['status']!='complete':continue
        r=load(args.study/tid/'result.json');load(args.study/tid/'protocol.json');load(args.study/tid/'replay.json')
        for model,folds in r['models'].items():
            annotation=identity_consensus(folds,score_name='joint_target')
            summary.append(dict(scan=job['label'],model=model,selected_norad=annotation['norad'],
                diagnostic_consensus=annotation['status'],minimum_joint_margin=annotation['minimum_margin'],
                unchanged_conditional_status=r['annotations'][model]['status'],
                maximum_cut_replay_delta=r['maximum_frozen_score_replay_delta']))
            for fold in folds:
                original=next(p for p in fold['proposals'] if p['norad']==r['original_norad'])
                for p in fold['proposals']:
                    for arm,v in p['arms'].items():
                        s=v['scores'];base=original['arms'][arm]['scores']
                        rows.append(dict(scan=job['label'],model=model,seed=fold['seed'],arm=arm,norad=p['norad'],
                            training_delta=s['ordinary_conditional']['training_negative_twice_log_density']-base['ordinary_conditional']['training_negative_twice_log_density'],
                            ordinary_held_delta=s['ordinary_conditional']['negative_twice_log_density']-base['ordinary_conditional']['negative_twice_log_density'],
                            cut_held_delta=s['target']['negative_twice_log_density']-base['target']['negative_twice_log_density'],
                            joint_delta=s['joint_target']['negative_twice_log_density']-base['joint_target']['negative_twice_log_density'],
                            conditional_phase_s=v['target_phase_mean_s'],boundary_mass=v['target_phase_boundary_mass'],
                            joint_decomposition_error=abs(s['joint_target']['negative_twice_log_density']-s['ordinary_conditional']['negative_twice_log_density']-
                                s['ordinary_conditional']['training_negative_twice_log_density'])))
        fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        seeds=[f['seed'] for f in r['models']['receiver_hz']]
        candidates=sorted({v['norad'] for v in rows if v['scan']==job['label']})
        for col,arm in enumerate(('c0','fitted_c')):
            for norad in candidates:
                local=[v for v in rows if v['scan']==job['label'] and v['model']=='receiver_hz' and v['arm']==arm and v['norad']==norad]
                for row,key in enumerate(('training_delta','cut_held_delta')):
                    axs[row,col].plot([seeds.index(v['seed']) for v in local],[v[key] for v in local],'o-',label=str(norad))
            axs[0,col].set(title=arm,ylabel='Training evidence penalty vs original nominee')
            axs[1,col].set(ylabel='Conditional held score penalty',xlabel='Randomized partition')
            axs[1,col].axhline(10,c='grey',ls='--',label='existing margin threshold')
            for ax in axs[:,col]:ax.set_xticks(range(3),[str(s) for s in seeds],rotation=20);ax.grid(alpha=.2);ax.legend(fontsize=7)
        fig.suptitle(job['label']+' — evidence discarded by conditional-only comparison\nAdditive-Hz correction; all models included in CSV')
        path='figures/'+tid+'_training_evidence.png';fig.savefig(out/path,dpi=140);plt.close(fig);figures.append(f'![{job["label"]} evidence decomposition]({path})')
    for name,data in [('joint_evidence_summary.csv',summary),('joint_evidence_scores.csv',rows),('joint_evidence_execution.csv',executions)]:
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator='\n');w.writeheader();w.writerows(data)
    write(out/'joint_evidence_sources.json',sources)
    with gzip.open(out/'joint_evidence.json.gz','wt') as f:json.dump(evidence,f)
    (out/'joint_evidence.md').write_text(f'''# Why a poor competing satellite can have a similar held score

The [renewed candidate comparison](satellite_competition.md) keeps 66109 as the winner for AUTO-c0dd2487 but marks it ambiguous: the weakest frozen-receiver held-score margin is only about 2.7, below the existing threshold of 10. In that partition the 62429 alternative has RMS around 174 Hz versus 108 Hz for 66109. Both alternatives 62429 and 67177 push their conditional phase to the ±15 s search boundary. The winner stays near −1.9 s.

The conditional scoring rule answers whether a candidate predicts withheld points **after being allowed to explain its training points**. Its normalization removes the marginal evidence of the training points. A candidate requiring highly improbable training behavior can therefore remain competitive on a particular held block. This is a limitation of this recovery-validation statistic; the experiment does not establish that every production association failure has this cause. Candidate-family exclusion and prediction mode also differ from earlier curved-track annotations.

## Exact joint-evidence diagnostic

For the same candidate union, calibration fits, partitions, aliases, priors and search budgets, also compute the ordinary Gaussian-mixture density of all target **training plus held points** (guard points remain excluded). Every target point remains absent from receiver calibration. Receiver uncertainty and satellite nuisance parameters are integrated under their priors/posteriors from the independent calibration; no target receiver refit is performed.

```
joint negative twice log density
    = training negative twice log density
    + ordinary conditional-held negative twice log density
```

We independently evaluate the left side and verify the equality to 1e-5. The modular frozen-receiver score is not substituted into this identity: it factorizes phase and receiver uncertainty and is a different prediction rule. The frozen scores, aliases and candidate sets replay the preceding experiment exactly within 1e-5. A synthetic test demonstrates how identical conditional held distributions can hide very different training evidence.

{table(summary,['scan','model','selected_norad','diagnostic_consensus','minimum_joint_margin','unchanged_conditional_status','maximum_cut_replay_delta'])}

These are diagnostic consensus results under an alternative score, **not new accepted identities**. The existing conditional acceptance remains unchanged. Nomination used target training points, so the joint evidence is not independent validation of the candidate-search procedure and its margins are not calibrated identity probabilities. No cross-partition likelihoods are multiplied or summed; the same observations recur across partitions. A general rule needs validation on unresolved and incorrect candidates before adoption, with matched c=0/fitted-c and receiver-transfer checks retained.

{chr(10).join(figures)}

For AUTO-c0dd2487's weak first partition, additive-Hz fitted-c, the 62429 alternative's training penalty is about 484 score units, despite only about 2.7 units of frozen held-score separation. This explains why the conditional-only rule can understate the physical evidence against that competitor. It does not justify removing phase bounds or blindly accepting every curve.

The [complete decomposition](joint_evidence_scores.csv), [execution receipts](joint_evidence_execution.csv), and [source hashes](joint_evidence_sources.json) preserve every model and both c arms. No new position fit, production change, or ALGO promotion is made. The next controlled prototype should use training-only compatibility/physical-prior evidence to screen candidates, followed by independent held predictions, or a clearly specified full-curve marginal-evidence rule with externally validated false-association behavior.
''')
    print(json.dumps(summary,indent=2))


def run(args):
    if args.joint:return joint_report(args)
    out=args.report;sources={};evidence={}
    def load(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();r=read(path);evidence[str(path)]=r;return r
    cohort=load(args.study/'protocol.json');rows=[];votes=[];details=[];executions=[];figures=[];transfer=[]
    for job in cohort['jobs']:
        tid=job['track_id'];terminal=load(args.study/(tid+'-terminal.json'))
        executions.append(dict(scan=job['label'],status=terminal['status'],seconds=terminal['seconds'],reason=terminal.get('reason')))
        if terminal['status']!='complete':continue
        r=load(args.study/tid/'result.json');load(args.study/tid/'protocol.json')
        for fold in r['models']['original']:load(args.study/tid/f"nominations-{fold['seed']}.json")
        for model,folds in r['models'].items():
            a=identity_consensus(folds,score_name='conditional_target')
            if a!=r['annotations'][model]:raise ValueError('identity consensus replay mismatch')
            boundaries=[p['arms'][arm]['target_phase_boundary_mass'] for f in folds for p in f['proposals']
                        if p['norad']==a['norad'] for arm in ('c0','fitted_c')]
            rows.append(dict(scan=job['label'],model=model,original_norad=r['original_norad'],selected_norad=a['norad'],
                status=a['status'],minimum_margin=a.get('minimum_margin'),
                maximum_boundary_mass=max(boundaries) if boundaries else None,
                candidate_counts='/'.join(str(len(f['proposals'])) for f in folds)))
            votes.extend(dict(scan=job['label'],model=model,**v) for v in a['votes'])
            if model!='original':
                score_delta=[];rms_delta=[]
                for fold,baseline in zip(folds,r['models']['original'],strict=True):
                    if fold['seed']!=baseline['seed']:raise ValueError('unmatched partitions')
                    target=next(p for p in fold['proposals'] if p['norad']==r['original_norad'])
                    old=next(p for p in baseline['proposals'] if p['norad']==r['original_norad'])
                    for arm in ('c0','fitted_c'):
                        s=target['arms'][arm]['scores']['target'];b=old['arms'][arm]['scores']['target']
                        score_delta.append(s['negative_twice_log_density']-b['negative_twice_log_density'])
                        rms_delta.append(s['rms_hz']-b['rms_hz'])
                transfer.append(dict(scan=job['label'],model=model,score_improved=sum(v<=0 for v in score_delta),
                    rms_improved=sum(v<=0 for v in rms_delta),worst_score_delta=max(score_delta),worst_rms_delta_hz=max(rms_delta)))
            for fold in folds:
                for p in fold['proposals']:
                    for arm,v in p['arms'].items():
                        score=v['scores']['target']
                        details.append(dict(scan=job['label'],seed=fold['seed'],model=model,arm=arm,norad=p['norad'],alias=p['alias'],
                            score=score['negative_twice_log_density'],rms_hz=score['rms_hz'],phase_s=v['target_phase_mean_s'],
                            phase_boundary_mass=v['target_phase_boundary_mass'],minimum_elevation_deg=v['minimum_target_elevation_deg'],
                            calibration_phase_change_s=v['final_phase_change_s']))
        fig,axs=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
        for col,arm in enumerate(('c0','fitted_c')):
            for model,color in [('original','black'),('receiver_hz','#4477aa'),('receiver_fractional','#cc3311')]:
                local=[v for v in votes if v['scan']==job['label'] and v['model']==model and v['arm']==arm]
                axs[col].plot(range(len(local)),[v['margin'] for v in local],'o-',c=color,label=model)
            axs[col].axhline(10,c='grey',ls='--',label='existing minimum margin')
            axs[col].set(title=arm,xlabel='Randomized partition',ylabel='Runner-up score minus winner score')
            axs[col].set_xticks(range(3),[str(f['seed']) for f in r['models']['original']],rotation=20)
            axs[col].grid(alpha=.2);axs[col].legend(fontsize=7)
        fig.suptitle(job['label']+' — fresh candidate union; every candidate family excluded from calibration')
        path='figures/'+tid+'_competition.png';fig.savefig(out/path,dpi=140);plt.close(fig)
        figures.append(f"![{job['label']} candidate margins]({path})")
    for name,data in [('competition_summary.csv',rows),('competition_votes.csv',votes),('competition_scores.csv',details),('competition_execution.csv',executions),('competition_transfer.csv',transfer)]:
        if not data:continue
        with (out/name).open('x') as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator='\n');writer.writeheader();writer.writerows(data)
    write(out/'competition_sources.json',sources)
    with gzip.open(out/'competition_evidence.json.gz','wt') as f:json.dump(evidence,f)
    text=f'''# Renewed satellite competition under receiver corrections

The two cases that passed the preceding ordinary conditional-prediction and full-fit checks are both included; their selection did not use GPS error. This includes AUTO-8d229584, whose improvement is less robust under the subsequent frozen-receiver ablation. These experiments diagnose identity, not production eligibility.

## Fair comparison

For each original randomized partition, replay the saved target-family-excluded calibration exactly and nominate the top three distinct candidates from the full causal bank under each receiver model. Nomination scans the existing regional 3×3 position grid plus trained positions and ±15 s phase search. Take the union across models, always include the original nominee, and retain that same union for both c arms and all models. Alias estimates use target training points under the original model and are frozen across arms and models.

Then **refit receiver calibration excluding the entire union of candidate satellite families**, including all their RX/channel tracks. This prevents an already-associated competitor from calibrating the receiver used to evaluate itself. Other incumbent identities remain fixed. Score every candidate using the frozen-receiver modular predictor, a 0.025 s causal phase grid, the original physical orbital priors, the same 150 Hz training-noise rule and the same target holdouts. No held frequency selects candidates, aliases, calibration or phase weights. Candidate search is broad but not exhaustive exact integration over every catalogue object; support remains conditional on this search and the other incumbent identities.

## Results

{table(rows,['scan','model','original_norad','selected_norad','status','minimum_margin','candidate_counts','maximum_boundary_mass'])}

Margins are differences in negative twice log predictive density, not identity probabilities. The existing consensus rule requires one winner across three randomized partitions and both c arms, all adequacy checks, and at least 10 units over the runner-up in every comparison. Boundary mass is reported separately. A supported identity does not authorize inclusion if receiver transfer or the full joint fit still fails.

The correction's target prediction benefit can also be checked after excluding the full competitor union. Counts below are out of six matched comparisons. AUTO-c0dd2487 preserves its improvement; AUTO-8d229584 retains its one-partition RMS regression. No held scores from other families are recomputed in this additional identity experiment, so this table is a target-only diagnostic, not a repeat of the full transfer screen.

{table(transfer,['scan','model','score_improved','rms_improved','worst_score_delta','worst_rms_delta_hz'])}

{chr(10).join(figures)}

See [every candidate score](competition_scores.csv), [individual votes](competition_votes.csv), [execution receipts](competition_execution.csv), and [source hashes](competition_sources.json). Training checkpoint replay is verified to 1e-5 objective units before nomination; no previous fit is silently treated as equivalent. Results use two bounded workers, at most 600 seconds per case. No new position estimates or production changes are made by this experiment.
'''
    (out/'satellite_competition.md').write_text(text)
    print(json.dumps(dict(results=rows,executions=executions),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--joint',action='store_true')
    run(p.parse_args())
