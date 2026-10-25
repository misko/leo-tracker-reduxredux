"""Report conditional held-family prediction; no geographic truth inputs."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from heldout import HERE, CASES, MODELS, ARMS, SCALES
from matched_controls import write, digest


def save_csv(path, rows):
    with path.open('w') as stream:
        out = csv.DictWriter(stream, fieldnames=list(rows[0]))
        out.writeheader();out.writerows(rows)


def report():
    protocol = json.loads((HERE/'protocol.json').read_text())
    results = [json.loads((HERE/'results'/f'{case}_fold{fold}.json').read_text()) for case in CASES for fold in range(3)]
    complete = [r for r in results if r['status']=='complete']
    movement, own, endpoints = [], [], []
    for result in complete:
        case, fold = result['case'], result['fold']
        for arm, analysis in result['arms'].items():
            fits, scores = analysis['fits'], analysis['crossover']
            delta = np.asarray(fits['sharedRF50']['endpoint_east_north_km'])-fits['baseline']['endpoint_east_north_km']
            endpoints.append(dict(case=case, fold=fold, arm=arm,
                baseline_east_km=fits['baseline']['endpoint_east_north_km'][0],
                baseline_north_km=fits['baseline']['endpoint_east_north_km'][1],
                shared_east_km=fits['sharedRF50']['endpoint_east_north_km'][0],
                shared_north_km=fits['sharedRF50']['endpoint_east_north_km'][1],
                movement_east_km=delta[0], movement_north_km=delta[1], movement_km=float(np.linalg.norm(delta))))
            for scale in SCALES:
                for predictor in MODELS:
                    a, b = [scores[predictor][endpoint]['scores'][str(scale)] for endpoint in MODELS]
                    movement.append(dict(case=case, fold=fold, arm=arm, predictor=predictor,
                        native_sigma_multiplier=scale, primary=scale==SCALES[1],
                        movement_support_gain=a['negative_twice_log_density']-b['negative_twice_log_density'],
                        quadratic_gain=a['quadratic']-b['quadratic'], logdet_gain=a['logdet']-b['logdet'],
                        baseline_endpoint_loss=a['negative_twice_log_density'], shared_endpoint_loss=b['negative_twice_log_density'],
                        baseline_endpoint_mean_RMS_hz=a['mean_prediction_RMS_hz'], shared_endpoint_mean_RMS_hz=b['mean_prediction_RMS_hz'],
                        held_dimensions=a['dimensions'], movement_km=float(np.linalg.norm(delta))))
                a, b = [scores[model][model]['scores'][str(scale)] for model in MODELS]
                own.append(dict(case=case, fold=fold, arm=arm, native_sigma_multiplier=scale,
                    primary=scale==SCALES[1], own_model_gain=a['negative_twice_log_density']-b['negative_twice_log_density'],
                    quadratic_gain=a['quadratic']-b['quadratic'], logdet_gain=a['logdet']-b['logdet'],
                    baseline_mean_RMS_hz=a['mean_prediction_RMS_hz'], shared_mean_RMS_hz=b['mean_prediction_RMS_hz'],
                    held_dimensions=a['dimensions']))
    save_csv(HERE/'movement_support.csv', movement)
    save_csv(HERE/'own_model_prediction.csv', own)
    save_csv(HERE/'train_endpoints.csv', endpoints)
    aggregate = []
    for case in CASES:
        for arm in ARMS:
            for predictor in MODELS:
                for scale in SCALES:
                    rows = [r for r in movement if r['case']==case and r['arm']==arm and r['predictor']==predictor and r['native_sigma_multiplier']==scale]
                    aggregate.append(dict(case=case, arm=arm, predictor=predictor, native_sigma_multiplier=scale,
                        complete_folds=len(rows), total_movement_support_gain=sum(r['movement_support_gain'] for r in rows),
                        positive_folds=sum(r['movement_support_gain']>0 for r in rows),
                        total_quadratic_gain=sum(r['quadratic_gain'] for r in rows), total_logdet_gain=sum(r['logdet_gain'] for r in rows)))
    save_csv(HERE/'movement_summary.csv', aggregate)
    convergence_sensitivity=[]
    for arm in ARMS:
        for predictor in MODELS:
            for scale in SCALES:
                rows=[r for r in movement if r['case']=='DS24-0095' and r['fold']!=2 and r['arm']==arm
                    and r['predictor']==predictor and r['native_sigma_multiplier']==scale]
                convergence_sensitivity.append(dict(case='DS24-0095', arm=arm, predictor=predictor,
                    native_sigma_multiplier=scale, excluded_zero_based_fold=2, retained_folds=len(rows),
                    movement_support_gain=sum(r['movement_support_gain'] for r in rows)))
    save_csv(HERE/'convergence_sensitivity.csv', convergence_sensitivity)
    primary = [r for r in movement if r['primary']]
    fig, axes = plt.subplots(2,2, figsize=(12,7), sharey=True)
    for i,case in enumerate(CASES):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j]
            for k,predictor in enumerate(MODELS):
                rows=[r for r in primary if r['case']==case and r['arm']==arm and r['predictor']==predictor]
                ax.bar(np.array([r['fold'] for r in rows])+(k-.5)*.32,[r['movement_support_gain'] for r in rows],.3,label=predictor)
            ax.axhline(0,color='black',lw=.8);ax.set_xticks(range(3),['Fold 1','Fold 2','Fold 3'])
            ax.set_title(f'{case} {arm}');ax.set_ylabel('Movement support gain')
            if case=='DS24-0095' and arm=='fitted_c':
                ax.text(.02,.96,'Baseline fold 3 phase change: 0.0150 s > 0.01 s\nRetained in primary totals',
                    transform=ax.transAxes,va='top',fontsize=8,bbox=dict(facecolor='white',alpha=.85,edgecolor='.7'))
    axes[0,0].legend();fig.suptitle('Held CFO Gaussian moment prediction: native sigma ×√2\nSame predictor, full joint covariance; positive favors RF50 position')
    fig.tight_layout();fig.savefig(HERE/'movement_support.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4.5))
    labels=[];values=[]
    for row in own:
        if row['primary']:
            labels.append(f"{row['case'][-4:]} F{row['fold']+1} {row['arm']}");values.append(row['own_model_gain'])
    ax.bar(range(len(values)),values);ax.axhline(0,color='black',lw=.8)
    ax.set_xticks(range(len(values)),labels,rotation=55,ha='right');ax.set_ylabel('Own-model predictive gain')
    ax.set_title('Own-model held density mixes receiver covariance, mean and movement\nGaussian moment prediction, native sigma ×√2')
    fig.tight_layout();fig.savefig(HERE/'own_model_prediction.png',dpi=160);plt.close(fig)
    max_phase=max(v['phase_refresh_changes_s'][-1] for r in complete for a in r['arms'].values() for q in a['crossover'].values() for v in q.values())
    max_precision=max(f['training_final_log_precision_change'] for r in complete for a in r['arms'].values() for f in a['fits'].values())
    phase_failures=[dict(case=r['case'], fold=r['fold'], arm=arm, model=model,
        final_phase_change_s=f['final_phase_change_s']) for r in complete for arm,a in r['arms'].items()
        for model,f in a['fits'].items() if f['final_phase_change_s']>.01]
    summary=dict(status='complete' if len(complete)==6 else 'partial', folds_complete=len(complete),
        position_fits=sum(len(a['fits']) for r in complete for a in r['arms'].values()),
        score_vectors=sum(sum(len(p) for p in a['crossover'].values()) for r in complete for a in r['arms'].values()),
        maximum_fold_seconds=max(r['seconds'] for r in results), maximum_training_precision_change=max_precision,
        maximum_fixed_position_phase_change_s=max_phase, original_phase_criterion_failures=phase_failures,
        movement_summary=aggregate, convergence_sensitivity=convergence_sensitivity,
        protocol_sha256=digest(HERE/'protocol.json'), result_files=[dict(path=str(HERE/'results'/f"{r['case']}_fold{r['fold']}.json"),sha256=digest(HERE/'results'/f"{r['case']}_fold{r['fold']}.json")) for r in results])
    write(HERE/'summary.json',summary)
    lines=['# Whole-family position-sensitive holdout', '',
        'Under this conditional score, held-family CFO prediction supports the RF50 movement in 0017 in aggregate and favors the baseline position in 0095. Within the RF50 predictor, the fitted-c movement gains are **+16.724** and **−5.807** respectively; the baseline predictor gives **+5.636** and **−11.031**. The aggregate signs persist in c=0 and at both predeclared noise sensitivities. Individual folds disagree, and these two previously selected cases cannot establish a transferable selection rule.', '',
        'The headline is held CFO support for moving from the baseline train-only endpoint to the RF-scaled shared-RX1 train-only endpoint, under the same predictor. Positive values favor the movement. These are conditional Gaussian **moment** predictive scores using native per-ID sigma ×√2, not exact original Student/Gamma densities or geographic accuracy.', '',
        '| Scan | c arm | Predictor | Fold1 | Fold2 | Fold3 | Sum | Positive folds |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for case in CASES:
        for arm in ARMS:
            for predictor in MODELS:
                rows=[r for r in primary if r['case']==case and r['arm']==arm and r['predictor']==predictor]
                values=[r['movement_support_gain'] for r in rows]
                lines.append(f"| {case} | {arm} | {predictor} | "+' | '.join(f'{v:.3f}' for v in values)+f" | {sum(values):.3f} | {sum(v>0 for v in values)}/3 |")
    lines += ['', '![Movement support](movement_support.png)', '',
        'The three folds are one seeded random disjoint whole-family partition, not three independent experiments. Each held vector jointly includes all its original active curved and predictive factors across both receivers and all channels. The sums combine fold-wise conditional validation scores; training sets overlap. Nonadditive family marginal diagnostics are saved separately inside each result and never substituted for the joint score.', '',
        '| Scan | c arm | Predictor | Native sigma ×1 | Native sigma ×√2 | Native sigma ×2 |',
        '|---|---|---|---:|---:|---:|']
    for case in CASES:
        for arm in ARMS:
            for predictor in MODELS:
                rows=[r for r in aggregate if r['case']==case and r['arm']==arm and r['predictor']==predictor]
                lines.append(f'| {case} | {arm} | {predictor} | '+' | '.join(f"{r['total_movement_support_gain']:.3f}" for r in rows)+' |')
    lines += ['', 'The complete [movement table](movement_support.csv) separates quadratic from log-determinant gains. Both terms are retained. The [train endpoints](train_endpoints.csv) contain only fitted regional east/north coordinates; this report has no geographic reference.', '',
        '![Own-model prediction](own_model_prediction.png)', '',
        'The separate [own-model table](own_model_prediction.csv) compares baseline prediction at its baseline endpoint with RF50 prediction at its RF50 endpoint. This combines added covariance, changed receiver mean and changed location; it cannot by itself establish support for the movement.', '',
        'Own-model fitted-c gains are much larger: +267.279 for 0017 and +135.298 for 0095. Thus both scans benefit from the receiver model in this conditional predictive metric, while the same-predictor crossover distinguishes their location movement. Raw held prior-mean RMS values retain the unknown target phase and fragment offsets and are not estimates of measurement noise. The score integrates their covariance rather than fitting target nuisance values.', '',
        '## Construction and leakage controls', '',
        'Frozen cases are DS24-0017 and DS24-0095, selected previously for opposing geographic effects. No geographic reference enters these new fits, scores, fold assignments, model choices or thresholds. Seed 2026102503 plus numeric case suffix defines three reproducible whole-family folds. Original observations, IDs, satellite labels, aliases, powers, causal prior means/scales and 25×25 km bounds are retained. Each fold removes every held curved factor through the point mask and every held predictive entry from the training problem. All frozen graph rows and physical-mode support stay present for stable coordinate support, an explicit inherited-graph condition.', '',
        'Both models and both c arms start at the regional center and use five phase-refresh rounds with at most 48 position steps per round. Held phases remain at their causal prior means in every training and scoring round. The crossover recalculates training-only nuisance posteriors with five fixed-position phase refreshes at both endpoints; it adds no position optimization. Predictive training factors influence position, while their values never update curved calibration, phase coefficients or Gamma precision.', '',
        'At each held endpoint, the mean uses the curved-training nuisance posterior. The covariance carries its full joint coefficient covariance, conditional on training variational Gamma precisions and original generalized-likelihood powers. All held-local training feature columns must be exactly zero. Held phase mean stays causal and its standardized variance is explicitly reset to 1, rather than the unused mean-field Student precision. Held orbit coefficients retain Gaussian prior variance 1. Each original held curved fragment retains a 300 Hz Gaussian constant, and every held predictive fragment gets its own 300 Hz Gaussian constant. Full shared covariance couples all target points and families.', '',
        'Native frozen per-ID sigmas are used unchanged, multiplied by√2 to match E[1/tau]=2 for an unseen Gamma(2,2) noise precision. Sensitivities ×1 and ×2 were frozen before fitting. No target nuisance or Gamma precision is estimated from target CFO. However, native sigmas, graph membership, labels, aliases, masks, powers and mode support were previously selected or estimated with full RF data. The evaluation is conditional on these inherited inputs and is not a fully external holdout.', '',
        'The held Student phase and Gamma noise tails are approximated by Gaussian covariance moments; the training nuisance covariance is conditional on variational precisions. Linear orbital/phase geometry uses the causal held phase mean and does not integrate nonlinear phase curvature. Fitted train-only position is a plug-in point: its uncertainty and search selection are not integrated. These limitations preclude interpreting the score as exact model evidence, an identity proof, a geographic accuracy estimate or a promotion rule.', '',
        '## Verification and reproducibility', '',
        f"Completed {summary['position_fits']}/24 position fits and {summary['score_vectors']}/48 joint crossover vectors; longest case/fold {summary['maximum_fold_seconds']:.2f} s under the 240 s cap. Maximum training final log-precision change {max_precision:.3g}; maximum final fixed-position phase-reference change {max_phase:.4g} s. Work used at most two processes with one BLAS/OMP/MKL thread each.", '',
        '**One original phase convergence criterion fails and is retained:** DS24-0095, fold 3 (zero-based fold 2), fitted-c baseline has final train-fit phase-reference change 0.0150179 s, above the original 0.01 s limit. All fixed-position crossover phase refreshes finish below 0.01 s. No extra fitting rounds or tuned rescue were added. These are raw diagnostic fits; original residual adoption gates were not used to select folds or emit an accepted policy.', '',
        'A labeled [convergence sensitivity](convergence_sensitivity.csv) excludes that entire 0095 fold consistently for both predictors, both c arms and all three noise scales. At the primary scale, the remaining c=0 gains are −7.989 (baseline predictor) and −6.573 (RF50 predictor); fitted-c gains are −8.596 and −7.140. All sensitivity aggregate signs remain negative. This exclusion is not the primary result and supplies no replacement fit.', '',
        'Five focused component tests check dense joint Gaussian agreement, the effect of shared covariance, retention of position-sensitive shapes, fold factor removal, and held-CFO redaction. The redaction test perturbs all held curved/predictive values by 12,345 Hz with frozen graph/noise, verifies identical training objective/coefficients/precisions/residuals at a point, and verifies one identical 8-step bounded optimization trajectory for DS24-0017/fold 0/sharedRF50/fitted-c. This test is not claimed to replay all 24 fits.', '',
        'The [protocol](protocol.json), [input manifest](input_manifest.json), raw results and NPZ arrays bind exact IDs, immutable scales and source dependencies. Run freeze.py only before a new explicitly versioned batch; the production runner refuses to overwrite existing evidence and verifies input, protocol and source seals at start/end. No RF collection, QNAP write, golden fixture update or runtime production change was made.', '',
        'Reproduction: use .venv/bin/python -B; PYTHONPATH=/tmp/algo03-feasible-deps:src:tools:/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025/evaluation:/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025/receiver; set OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1. Run heldout.py --case CASE --fold 0 (or 1/2) with at most two simultaneous processes, then report.py. Results are a bounded conditional diagnostic. No threshold was tuned and neither case selects a policy.', '']
    (HERE/'FINDINGS.md').write_text('\n'.join(lines))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    report()
