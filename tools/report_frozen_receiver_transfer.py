"""Publish the receiver-feedback ablation with complete per-fold evidence."""
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
from debug_fast_graph_unassociated import read, write
from report_predictive_track_annotation import table


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);figs=out/'figures';figs.mkdir()
    sources={};evidence={}
    def load(path):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        r=read(path);evidence[str(path)]=r;return r
    def csvout(name,rows):
        if not rows:return
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    cohort=load(args.study/'protocol.json');rows=[];qualification=[];executions=[];gallery=[]
    for job in cohort['jobs']:
        tid=job['track_id'];terminal=load(args.study/(tid+'-terminal.json'))
        executions.append(dict(scan=job['label'],status=terminal['status'],seconds=terminal['seconds'],reason=terminal.get('reason')))
        if terminal['status']!='complete':continue
        r=load(args.study/tid/'result.json');load(args.study/tid/'protocol.json')
        for fold in r['folds']:
            for model,pair in fold['models'].items():
                for arm,v in pair.items():
                    base=fold['models']['original'][arm]
                    for mode,s in v['scores'].items():
                        a=s['score'];b=base['scores'][mode]['score']
                        rows.append(dict(scan=job['label'],track_id=tid,seed=fold['seed'],model=model,arm=arm,mode=mode,
                            held_points=v['held_points'],rms_hz=a['rms_hz'],baseline_rms_hz=b['rms_hz'],
                            score_delta=a['negative_twice_log_density']-b['negative_twice_log_density'],
                            existing_score_delta=v['existing_score']['negative_twice_log_density']-base['existing_score']['negative_twice_log_density'],
                            phase_s=s['phase_mean_s'],boundary_mass=s['phase_boundary_mass'],elevation_deg=s['minimum_elevation_deg'],
                            calibration_phase_change_s=v['final_phase_change_s'],
                            objective_replay_delta=v['objective_replay_delta'],conditional_score_replay_delta=v['conditional_score_replay_delta']))
        for model in ('receiver_hz','receiver_fractional'):
            for mode in ('ordinary','frozen_receiver','no_target_training'):
                selected=[v for v in rows if v['track_id']==tid and v['model']==model and v['mode']==mode]
                qualification.append(dict(scan=job['label'],model=model,mode=mode,
                    comparisons=len(selected),score_improved=sum(v['score_delta']<=0 for v in selected),
                    rms_improved=sum(v['rms_hz']<=v['baseline_rms_hz'] for v in selected),
                    worst_score_delta=max(v['score_delta'] for v in selected),
                    worst_rms_delta_hz=max(v['rms_hz']-v['baseline_rms_hz'] for v in selected),
                    predictive_screen_pass=bool(len(selected)==6 and all(v['score_delta']<=0 and
                        v['rms_hz']<=v['baseline_rms_hz'] and v['existing_score_delta']<=0 and
                        v['boundary_mass']<=.05 and v['elevation_deg']>=0 and v['calibration_phase_change_s']<=.01 for v in selected))))
        fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        for col,arm in enumerate(('c0','fitted_c')):
            for model,color in [('original','black'),('receiver_hz','#4477aa'),('receiver_fractional','#cc3311')]:
                for mode,style in [('ordinary',':'),('frozen_receiver','-')]:
                    local=[v for v in rows if v['track_id']==tid and v['model']==model and v['arm']==arm and v['mode']==mode]
                    label=model+' / '+mode
                    axs[0,col].plot(range(3),[v['rms_hz'] for v in local],marker='o',ls=style,c=color,label=label)
                    axs[1,col].plot(range(3),[v['score_delta'] for v in local],marker='o',ls=style,c=color,label=label)
            axs[0,col].set(title=arm,ylabel='Held target RMS (Hz)')
            axs[1,col].set(ylabel='Predictive score change vs original model',xlabel='Randomized partition')
            axs[1,col].axhline(0,c='grey',lw=.5)
            for ax in axs[:,col]:ax.grid(alpha=.2);ax.set_xticks(range(3),[str(f['seed']) for f in r['folds']],rotation=20)
            axs[0,col].legend(fontsize=6)
        fig.suptitle(job['label']+' — blocking target-to-receiver uncertainty feedback')
        filename=tid+'_scores.png';fig.savefig(figs/filename,dpi=140);plt.close(fig)
        gallery.append(f"### {job['label']} predictive comparison\n\n![Predictive comparison](figures/{filename})\n")
        fig,axs=plt.subplots(3,2,figsize=(12,9),layout='constrained')
        for row,fold in enumerate(r['folds']):
            for col,arm in enumerate(('c0','fitted_c')):
                ax=axs[row,col]
                for model,color in [('original','black'),('receiver_hz','#4477aa'),('receiver_fractional','#cc3311')]:
                    v=fold['models'][model][arm];s=v['scores']['frozen_receiver']['score'];order=np.argsort(v['held_times_s'])
                    ax.plot(np.array(v['held_times_s'])[order],np.array(s['held_residual_hz'])[order],'.-',c=color,label=model)
                ax.axhline(0,c='grey',lw=.5);ax.grid(alpha=.2)
                ax.set(title=f"{arm} / seed {fold['seed']}",xlabel='Scan time (s)',ylabel='Held residual (Hz)');ax.legend(fontsize=7)
        fig.suptitle(job['label']+' — frozen-receiver predictions; held points do not fit any parameters')
        filename=tid+'_residuals.png';fig.savefig(figs/filename,dpi=140);plt.close(fig)
        gallery.append(f"### {job['label']} held residuals\n\n![Held residuals](figures/{filename})\n")
    csvout('scores.csv',rows);csvout('qualification.csv',qualification);csvout('execution.csv',executions)
    concise=[v for v in qualification if v['mode']=='frozen_receiver']
    summary=dict(executions=executions,frozen_receiver_screen_passes=sum(v['predictive_screen_pass'] for v in concise),
        maximum_objective_replay_delta=max(v['objective_replay_delta'] for v in rows),
        maximum_conditional_score_replay_delta=max(v['conditional_score_replay_delta'] for v in rows),
        new_position_fits=False,no_production_change=True)
    write(out/'summary.json',summary);write(out/'sources.json',sources)
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(evidence,f)
    (out/'gallery.md').write_text('# Frozen-receiver validation figures\n\n'+'\n'.join(gallery))
    text=f'''# Receiver-feedback ablation on five rejected curves

The [previous receiver-ramp experiment](../2026_10_29_independent_receiver_ramps/README.md) excluded the target satellite from calibration, but Gaussian predictive conditioning still updated receiver uncertainty using target training points. This experiment blocks that update at each fixed satellite phase. It replays all five cases, three models, three randomized block partitions and both c arms. No GPS or future TLE enters fitting or selection. Original identities and aliases remain frozen; this is not renewed identity validation.

## What is frozen

Write the target prediction covariance as `B + F`, where `B` contains independent satellite orbital modes, a 300 Hz track-bias prior and observation noise, and `F` is the receiver posterior covariance projected onto target timestamps. Receiver coefficients and their marginal covariance come entirely from other satellite families. With target training indices t and held indices h, `K = B_ht inv(B_tt)`:

```
held mean = m_h + K (y_t - m_t)
held covariance = B_hh - K B_th
                + F_hh - K F_th - F_ht K.T + K F_tt K.T
```

This integrates the unchanged receiver distribution after conditioning satellite nuisance terms separately for each receiver realization. Target observations cannot reduce the receiver marginal variance. If there is no satellite nuisance and only one phase, target training changes neither the held mean nor its receiver variance; an explicit regression test checks this.

Phase weights still use training likelihood marginalized over receiver uncertainty. The phase distribution is then factorized from the original receiver marginal: this is a **modular approximation**, not an exact joint Bayesian posterior or proof of hardware causation. Target training may identify satellite phase, orbital modes and bias. We also compute a stronger `no_target_training` diagnostic that uses the causal phase prior without any target training frequencies. Its uncertainty is intentionally broad; it is not an identity acceptance rule.

## Results

{table(concise,['scan','model','score_improved','rms_improved','worst_score_delta','worst_rms_delta_hz','predictive_screen_pass'])}

Each count is out of six matched comparisons (three partitions × two c arms). Lower density scores and RMS are better. The unchanged diagnostic screen additionally requires existing-family held scores not to worsen, phase convergence ≤0.01 s, visibility and boundary mass ≤0.05. The screen is not a calibrated population false-association bound. A failure identifies a weakness to investigate; it does not prove the curve is not a satellite.

[Every comparison](scores.csv), [all diagnostic screens](qualification.csv), [execution receipts](execution.csv), and [all figures](gallery.md) include unfavorable results. Original objective and ordinary predictive-score replays differ by at most {summary['maximum_objective_replay_delta']:.6g} and {summary['maximum_conditional_score_replay_delta']:.6g}, respectively. No position fits are rerun: previously reported position gains remain conditional on their earlier full-fit checks and are not new results of this validation.

## What this changes about the earlier promising results

The extra checks narrow the conclusion. AUTO-c0dd2487 improves target prediction with receiver feedback blocked, under both correction models, and its earlier full fits pass. However, [renewed satellite competition](satellite_competition.md) leaves its identity below the existing conditional-score margin threshold. The [joint-evidence diagnostic](joint_evidence.md) investigates why an alternative with very poor training evidence remains competitive on one held partition. It proposes a scoring hypothesis; it does not change acceptance.

AUTO-8d229584 retains strong support for satellite 100017 under renewed competition, but its corrected frozen-receiver RMS worsens in one of the three partitions (both c arms). Its earlier position improvement therefore remains provisional. AUTO-d9185bf9 passes the receiver-transfer screen but still has the previously documented orbital-support and old-track full-fit failures. AUTO-7ec14096 remains pinned to the phase boundary despite lower RMS; AUTO-453faf4c worsens on one held partition. The additive-Hz and RF-proportional results remain similar, so these cases do not distinguish the physical receiver mechanism.

**Neither of the two earlier full-fit success cases is ready for promotion after all of these new checks.** This is progress in locating the bottleneck, not a new dataset-wide position gain. The graph assessment ledger remains 744/1,630; this iteration investigates existing cases rather than adding annotations.

## Reproduction and scope

`probe_frozen_receiver_transfer.py --previous .../independent-receiver-ramps-v1 --output .../frozen-receiver-transfer-v1` runs five bounded workers, with 600 seconds per case. The original training protocol, causal catalogue, 25×25 km regional-center start, 5 phase-refresh rounds ×48 iterations, 150 Hz training noise, 0.025 s prediction phase grid, 12 s randomized blocks and 2 s guards are unchanged. Calibration checkpoints save the actual final phase reference and keep mask for subsequent exact replay. Receiver ramp priors remain exploratory: 50 Hz per 10 s continuous increment, additive-Hz or RF-proportional.

The tests cover analytical latent integration, the zero-receiver-uncertainty limit, target feedback prevention, absence of held-data leakage, covariance validity and unchanged existing predictor behavior. Evidence and [source hashes](sources.json) accompany this report. New-cohort tests and competing satellite identities are required before production promotion. No production behavior or ALGO version changes here.
'''
    (out/'README.md').write_text(text)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
