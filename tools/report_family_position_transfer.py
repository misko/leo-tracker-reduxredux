"""Report conditional family-transfer scores without choosing a promotion gate."""
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
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.grouped_prediction import identity_consensus
from report_inventory_experiments import error
from report_predictive_track_annotation import table
from report_systematic_annotation import compact_evidence


def run(args):
    s=args.study;out=args.output;out.mkdir(parents=True,exist_ok=False);figures=out/'figures';figures.mkdir()
    sources={};evidence={}
    def load(p):
        p=Path(p);sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();r=read(p);evidence[str(p)]=r;return r
    inputs=[s/'family-transfer-ds24-0047-v1/result.json',*sorted((s/'family-transfer-cohort-v1').glob('*/result.json'))]
    rows=[];family_rows=[];summary=[];gridrows=[]
    for p in inputs:
        r=load(p);pr=load(p.parent/'protocol.json');tag=p.parent.name
        gp=s/'family-transfer-grid-ds24-0047-v1/result.json' if tag=='family-transfer-ds24-0047-v1' else s/'family-transfer-grid-cohort-v1'/tag/'result.json'
        extended=s/'family-transfer-grid-extended-v1'/tag/'result.json'
        if extended.exists():gp=extended
        final_grid=s/'family-transfer-grid-final-v2'/tag/'result.json'
        if final_grid.exists():gp=final_grid
        refined=load(gp);lookup={(v['fold'],v['variant'],v['arm'],v['norad']):v for v in refined['rows']}
        for v in refined['rows']:
            gridrows.append(dict(scan=r['job']['label'],target=r['targets'][0]['norad'],**v))
        trial=Path(pr['source_trial']);control=load(trial/'control.json');target=load(trial/'new_family.json')
        for arm in ['c0','fitted_c']:
            gains=[];warnings=0;nonconverged=0
            for fold in r['folds']:
                k=fold['split']['fold'];c=fold['variants']['control'][arm];t=fold['variants']['plus_target'][arm];gg=[];errors=[]
                warnings+=sum(not v['optimizer_success'] for v in [c,t])
                for a,b in zip(c['held_families'],t['held_families'],strict=True):
                    assert a['norad']==b['norad'] and a['points']==b['points']
                    ac=lookup[k,'control',arm,a['norad']];bt=lookup[k,'plus_target',arm,a['norad']]
                    gain=(ac['score']-bt['score'])/a['points'];gg.append(gain)
                    # Observed last refinement change, not a mathematical error bound.
                    sensitivity=(abs(ac['steps'][-1]['change'])+abs(bt['steps'][-1]['change']))/a['points'];errors.append(sensitivity)
                    nonconverged+=sum(not z['converged'] for z in [ac,bt])
                    family_rows.append(dict(scan=r['job']['label'],target=r['targets'][0]['norad'],arm=arm,fold=k,
                        held_family=a['norad'],held_points=a['points'],gain=gain,last_grid_sensitivity=sensitivity,
                        coarse_gain=(a['negative_twice_log_density']-b['negative_twice_log_density'])/a['points'],
                        grids_converged=ac['converged'] and bt['converged']))
                gains.append(float(np.mean(gg)))
                rows.append(dict(scan=r['job']['label'],target=r['targets'][0]['norad'],arm=arm,fold=k,
                    mean_family_per_point_gain=gains[-1],last_grid_sensitivity=float(np.mean(errors)),
                    control_error_km=error(c),target_error_km=error(t),
                    control_optimizer=c['optimizer_success'],target_optimizer=t['optimizer_success'],
                    control_phase_change_s=c['final_phase_change_s'],target_phase_change_s=t['final_phase_change_s']))
            summary.append(dict(scan=r['job']['label'],target=r['targets'][0]['norad'],arm=arm,
                mean_fold_gain=float(np.mean(gains)),positive_folds=sum(g>0 for g in gains),fold_gains=gains,
                optimizer_warnings=warnings,grid_nonconverged_scores=nonconverged,
                full_control_error_km=error(control['arms'][arm]),full_target_error_km=error(target['arms'][arm]),
                full_trial_passed=target['paired_valid'],full_control_passed=control['paired_valid'],
                added_points=target['arms'][arm]['added_points'],source=str(p)))
    def csvfile(name,rr):
        with (out/name).open('x') as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]),lineterminator='\n');w.writeheader();w.writerows(rr)
    csvfile('transfer_summary.csv',summary);csvfile('fold_scores.csv',rows);csvfile('family_scores.csv',family_rows)
    groups=list(dict.fromkeys((v['scan'],v['target']) for v in summary));names=[f'{a}\n{b}' for a,b in groups]
    fig,axs=plt.subplots(2,1,figsize=(14,8),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        for k,color in enumerate(['#4477aa','#ee6677','#228833']):
            rr=[next(v for v in rows if (v['scan'],v['target'])==g and v['arm']==arm and v['fold']==k) for g in groups]
            ax.errorbar(np.arange(len(groups))+(k-1)*.17,[v['mean_family_per_point_gain'] for v in rr],
                yerr=[v['last_grid_sensitivity'] for v in rr],fmt='o',color=color,label=f'Random fold {k}',capsize=3)
        ax.axhline(0,c='black',lw=.8);ax.set_xticks(range(len(groups)),names);ax.set(ylabel='Held-score gain per point\n(equal family weights)',title=arm);ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Positive favors recovered track; bars show last grid change, not confidence intervals')
    fig.savefig(figures/'held_family_transfer.png',dpi=150);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(13,6),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c'],strict=True):
        for i,g in enumerate(groups):
            v=next(v for v in summary if (v['scan'],v['target'])==g and v['arm']==arm)
            ax.scatter(v['mean_fold_gain'],v['full_target_error_km']-v['full_control_error_km'],
                c='#ee6677' if v['full_trial_passed'] else '#4477aa',marker='x' if v['optimizer_warnings'] else 'o')
            ax.annotate(str(i+1),(v['mean_fold_gain'],v['full_target_error_km']-v['full_control_error_km']),xytext=(4,4),textcoords='offset points')
        ax.axhline(0,c='black',lw=.8);ax.axvline(0,c='black',lw=.8);ax.grid(alpha=.2)
        ax.set(title=arm,xlabel='Mean held-score gain (positive better)',ylabel='Full-fit error change (km; positive worse)')
    fig.suptitle('Independent-family score is conditional and does not certify absolute position accuracy\nRed: previous paired residual gates passed; ×: a validation endpoint reported optimizer failure')
    fig.savefig(figures/'transfer_vs_position.png',dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5),layout='constrained')
    delta=np.array([abs(v['gain']-v['coarse_gain']) for v in family_rows]);ax.hist(np.log10(np.maximum(delta,1e-12)),bins=25)
    ax.set(xlabel='log10 |refined − coarse held-score gain| per point',ylabel='Held-family comparisons',title='Phase integration sensitivity at fixed endpoints');ax.grid(alpha=.2)
    fig.savefig(figures/'phase_grid_sensitivity.png',dpi=150);plt.close(fig)
    previous=Path(__file__).resolve().parents[1]/'reports/2026_10_29_new_family_predictive_inclusion/annotation_ledger.csv'
    sources[str(previous)]=hashlib.sha256(previous.read_bytes()).hexdigest();prior={v['track_id']:v for v in csv.DictReader(previous.open())}
    q=s/'systematic-annotation-v1';protocol=load(q/'protocol.json');ledger=[]
    for v in protocol['rows']:
        row=dict(prior[v['track_id']]);row['scopes']='; '.join(v['scopes'])
        if not row.get('annotation_source'):
            folder=Path(v['known_validation']) if v['known_validation'] else q/v['track_id'];p=folder/'result.json'
            if p.exists():
                rr=load(p);a=identity_consensus(rr['folds'],score_name=rr.get('identity_score_name','joint'))
                row.update(state=a['status'],norad=a['norad'],minimum_margin=a.get('minimum_margin'),annotation_source=str(p))
            else:
                receipts=sorted(q.glob('attempt-*/'+v['track_id']+'-terminal.json'))
                if receipts:row['state']='execution_'+load(receipts[-1])['status']
        ledger.append(row)
    csvfile('annotation_ledger.csv',ledger);states=Counter(v['state'] for v in ledger);assessed=sum(bool(v.get('annotation_source')) for v in ledger)
    ds=[v for v in ledger if 'DS24' in v['scopes']];ds_assessed=sum(bool(v.get('annotation_source')) for v in ds)
    display=[]
    for i,g in enumerate(groups):
        cc=[next(v for v in summary if (v['scan'],v['target'])==g and v['arm']==a) for a in ['c0','fitted_c']]
        display.append(dict(case=i+1,scan=g[0],satellite=g[1],added=cc[0]['added_points'],
            c0_error=f"{cc[0]['full_control_error_km']:.3f} → {cc[0]['full_target_error_km']:.3f}",
            fitted_error=f"{cc[1]['full_control_error_km']:.3f} → {cc[1]['full_target_error_km']:.3f}",
            positive_folds=f"{cc[0]['positive_folds']}/3; {cc[1]['positive_folds']}/3",
            optimizer_warnings=f"{cc[0]['optimizer_warnings']}; {cc[1]['optimizer_warnings']}",
            previous_gates=cc[0]['full_trial_passed']))
    unresolved=sum(not v['converged'] for v in gridrows)
    text=f'''# Random whole-family position-transfer validation

This iteration tests whether adding a recovered satellite curve improves predictions of other satellite families. It does not authorize a production change. All ten completed new-family proposals are included, including previously rejected proposals; no case was selected using GPS error.

The inventory snapshot has **{assessed:,}/{len(ledger):,} assessed tracks**, including **{ds_assessed}/{len(ds)} in DS24**. Assessed includes ambiguous, mismatched and insufficient-partition outcomes. It does not mean recovered or confirmed. The ledger retains every pending and failed job.

## Findings

The tests do not establish a reliable position-inclusion rule. Small average predictive gains can coexist with worse absolute position. DS24-0047 remains the clearest counterexample: the new family passes the existing residual checks, but moves the full-data fitted-c estimate from about 1.33 km to 2.42 km error. Its position-transfer gains vary across random family partitions. The preceding influence analysis traced this to motion along a weakly constrained position direction; a better target frequency fit alone did not imply better location.

Neither positive average score nor a majority vote among held families should be promoted as a new acceptance gate from these examples. They are exploratory diagnostics. A large coherent curve can be real and still have weak or biased absolute-position information under the current nuisance and orbit model.

## Matched full-fit results and new validation

Full-fit errors below come from the preceding matched inclusion trials. Validation refits use the separate training-only protocol described below. Positive-fold counts are given as c=0; fitted-c. Optimizer warnings count final endpoints among six validation fits per arm. Added points are proposals before acceptance.

{table(display,list(display[0]))}

![Conditional prediction by random fold](figures/held_family_transfer.png)

![Prediction versus position accuracy](figures/transfer_vs_position.png)

## Reproducible protocol

1. Freeze the original graph, incumbent identities, aliases, retained memberships and proposed new family. This is conditional validation, not a fresh end-to-end satellite search.
2. With seed 20261029, randomly assign whole active curved satellite families to three folds. All receivers, channels and times belonging to the same family stay together. Each family is withheld once. No chronological holdout is used.
3. Remove held families and all existing predictive-only rows from training. Use fixed 150 Hz measurement noise and unit family weights; learn the hierarchical noise precision on training observations only. This intentionally differs from the production full-data noise preprocessing.
4. For each fold, run control and plus-target variants with both c=0 and fitted-c. Start at the same regional center, with a 25 × 25 km box, five phase-refresh rounds and matching L-BFGS-B budgets (48 iterations, 240 evaluations per round). No GPS is used in fitting, selection or scoring.
5. The target contributes its exact causal phase-mixture likelihood, integrating three physical orbital modes and receiver uncertainty. The target does not update the receiver calibration mean used to predict held families. This isolates transfer through the position contribution under the existing no-linear-calibration policy.
6. Predict each withheld family using its original retained points, a shared causal phase prior and three orbital modes across its tracks. Integrate phase over ±15 s. Score = −2 log predictive density. Gain = control score minus plus-target score, divided by held points; average equally over families within each fold, then over folds.
7. Evaluate GPS error only afterwards, using 37.849061591561885, −122.48574968092912. The regional center is 37.906, −122.545. All TLE-based inference is causal.

## Numerical checks

At every saved endpoint, replay the training objective and require agreement within 1e−5. Recompute held-family phase integration at 0.05 s instead of 0.1 s; if the absolute score changes by more than 0.01, refine to 0.025 s. Cases still unresolved receive further checks at 0.0125 s, 0.00625 s and 0.003125 s. **{unresolved}/{len(gridrows)} endpoint-family scores remain above that last-step tolerance.** This is a convergence diagnostic, not a rigorous error bound. Figure bars show the observed last grid change, not statistical confidence intervals. Position optimization and the target likelihood were not rerun on the finer grid.

![Phase-grid sensitivity](figures/phase_grid_sensitivity.png)

## Limits and next work

Held-family scores are marginal composite scores; families can share receiver errors, so their sum is not a joint independent likelihood. Position uncertainty is not integrated. The three folds have overlapping training data and are not independent replications. Frozen identities, aliases, graph selection, receiver basis and model-support choices remain conditional inputs. Several endpoints report optimizer failure; all are retained in the tables and are not treated as certified solutions.

The next inclusion test should distinguish satellite identity evidence from absolute-position leverage, propagate uncertainty along weak position directions, and use a joint model when adding multiple new families so shared receiver uncertainty is counted once. Numerical optimization warnings and receiver-versus-orbit discrepancies need separate diagnosis. These results do not justify forcing tracks into localization or adjusting priors using the known site.

The annotation queue continues with bounded on-disk jobs. The full state counts are {dict(states)}. The inventory covers existing large graph tracks, not every untracked GLRT curve or missing export. Previously reported exact-phase corrections to annotations are retained.

## Artifacts and validation

- [Complete annotation ledger](annotation_ledger.csv)
- [Transfer summary](transfer_summary.csv), [fold scores](fold_scores.csv), [family scores](family_scores.csv)
- [Evidence archive](evidence.json.gz), [source SHA-256 manifest](sources.json). Repetitive observation IDs and history arrays are represented by counts and hashes; raw source files remain on the study volume.
- [Previous inclusion report](../2026_10_29_new_family_predictive_inclusion/README.md)

Implementation: `family_folds` in the research analysis component; `validate_family_position_transfer.py`, `batch_family_transfer.py`, `refine_family_transfer.py`, and this report generator in tools. The focused suite passes 17 tests. Component tests cover whole-family separation/reproducibility and absence of active target-family calibration, including duplicate conditioning protection and the existing dense Gaussian oracle. A regression test verifies that legacy phase replay preserves cached converged scores: an initial refinement continuation was stopped after discovering a cache-variable collision; it produced no final result and is excluded. The corrected continuation supplies the final grid scores. No production deployment or ALGO promotion is made here.
'''
    (out/'README.md').write_text(text)
    write(out/'sources.json',sources);write(out/'summary.json',dict(assessed=assessed,total=len(ledger),ds24_assessed=ds_assessed,ds24_total=len(ds),states=dict(states),grid_unconverged=unresolved,results=summary))
    with gzip.open(out/'evidence.json.gz','wt') as f:json.dump(compact_evidence(evidence),f,separators=(',',':'))
    print(json.dumps(dict(assessed=assessed,ds24_assessed=ds_assessed,cases=len(inputs),grid_unconverged=unresolved)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);p.add_argument('--output',type=Path,required=True);run(p.parse_args())
