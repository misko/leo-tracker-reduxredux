"""Explicitly qualified cap15 diagnostics; no selection from held score alone."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.special import ndtr

ROOT=Path(__file__).resolve().parent


def main():
    result=json.loads((ROOT/'results.json').read_text());rows=result['rows'];good=[r for r in rows if 'error'not in r]
    summaries=[];flat=[];boxaudit=[]
    for r in good:
        sd=np.sqrt(np.diag(np.asarray(r['position_covariance_km2'])))
        x=np.asarray(r['x_km']);tail=ndtr((-12.5-x)/sd)+ndtr((x-12.5)/sd)
        boxaudit.append(dict(case=r['case'],arm=r['arm'],fold=r['fold'],solver=r['solver'],SD_scale=r['SD_scale'],
            boundary=r['boundary'],numerical_fit_qualified=r['numerical_fit_qualified'],
            outside_regional_box_probability_lower_bound=float(max(tail)),
            outside_regional_box_probability_upper_bound=float(min(1.,sum(tail))),
            posthoc_gaussian_box_tail_lower_bound_exceeds_5pct=bool(max(tail)>.05)))
    for r in good:
        for subset,score in r['scores'].items():
            flat.append(dict(case=r['case'],arm=r['arm'],fold=r['fold'],solver=r['solver'],SD_scale=r['SD_scale'],subset=subset,
                phase_closed=r['phase_closed'],optimizer_success=r['optimizer_success'],boundary=r['boundary'],
                position_curvature_floored=r['position_curvature_floored'],numerical_fit_qualified=r['numerical_fit_qualified'],
                unqualified_reasons=';'.join(r['unqualified_reasons']),**score))
    for case in ['DS26-0309','DS26-0070']:
        for arm in ['c0','fitted_c']:
            baseline={r['fold']:r for r in good if(r['case'],r['arm'],r['solver'],r['SD_scale'])==(case,arm,'legacy',1.)}
            for solver,scale in [('legacy',1.),('damped_half',1.),('damped_half',2.),('damped_half',4.)]:
                rr=[r for r in good if(r['case'],r['arm'],r['solver'],r['SD_scale'])==(case,arm,solver,scale)]
                if not rr:continue
                item=dict(case=case,arm=arm,solver=solver,SD_scale=scale,folds=len(rr),
                    phase_closed_folds=sum(r['phase_closed']for r in rr),optimizer_success_folds=sum(r['optimizer_success']for r in rr),
                    boundary_folds=sum(r['boundary']for r in rr),curvature_floor_folds=sum(r['position_curvature_floored']for r in rr),
                    numerical_fit_qualified_folds=sum(r['numerical_fit_qualified']for r in rr),
                    predictive_generalization_qualified=False)
                for subset in ['all','target','other']:
                    item[subset+'_sum_negative_twice_log_density']=sum(r['scores'][subset]['negative_twice_log_density']for r in rr)
                    item[subset+'_gain_vs_legacy']=sum(baseline[r['fold']]['scores'][subset]['negative_twice_log_density']-r['scores'][subset]['negative_twice_log_density']for r in rr)
                summaries.append(item)
    for path,rr in [(ROOT/'scores.csv',flat),(ROOT/'summary.csv',summaries),(ROOT/'position_box_audit.csv',boxaudit)]:
        with path.open('w')as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
    original=[]
    for case in ['DS26-0309','DS26-0070']:
        original+=json.loads((ROOT.parent/(case+'_results.json')).read_text())['rows']
    # Original result rows lack case; reconstruct from their scan-specific files.
    old={}
    for case in ['DS26-0309','DS26-0070']:
        for r in json.loads((ROOT.parent/(case+'_results.json')).read_text())['rows']:
            old[(case,r['arm'],r['fold'],r['solver'],r['SD_scale'])]=r
    formerly_closed=[r for r in good if old[(r['case'],r['arm'],r['fold'],r['solver'],r['SD_scale'])]['phase_closed']]
    protocol=json.loads((ROOT/'protocol.json').read_text())
    preserved={**protocol['original_results_sha256'],**protocol['original_protocol_sha256']}
    audit=dict(jobs=len(rows),errors=len(rows)-len(good),seconds=result['seconds'],
        original_frozen_artifacts_unchanged=all(hashlib.sha256(Path(k).read_bytes()).hexdigest()==v for k,v in preserved.items()),
        preregistered_sources_unchanged=all(hashlib.sha256(Path(k).read_bytes()).hexdigest()==v for k,v in protocol['source_sha256'].items()),
        dense_normalization_passes=sum(r['covariance_audit']['dense_normalization_pass']for r in good),
        maximum_absolute_dense_vs_lowrank_score_delta=max(abs(r['covariance_audit']['dense_minus_lowrank_negative_twice_log_density'])for r in good),
        negative_predictive_quadratics=sum(s['quadratic']< -1e-8 for r in good for s in r['scores'].values()),
        nonpositive_position_precision_cells=sum(min(r['position_precision_eigenvalues'])<=0 for r in good),
        curvature_floor_cells=sum(r['position_curvature_floored']for r in good),boundary_cells=sum(r['boundary']for r in good),
        numerical_fit_qualified_cells=sum(r['numerical_fit_qualified']for r in good),
        posthoc_cells_with_at_least_5pct_Gaussian_mass_outside_regional_box=sum(r['posthoc_gaussian_box_tail_lower_bound_exceeds_5pct']for r in boxaudit),
        original_phase_closed_cells=len(formerly_closed),
        originally_closed_maximum_absolute_score_change=max(abs(r['cap15_minus_cap8_negative_twice_log_density'])for r in formerly_closed),
        tests='Two original density/split tests plus two extended Gaussian covariance/Hessian tests pass.')
    (ROOT/'audit_summary.json').write_text(json.dumps(audit,indent=2)+'\n')
    lines=['# Uniform phase-cap15 conditional control','',
        'The larger phase cap closes all DS26-0070 damped SD2/SD4 fits, while its legacy control still closes only one fold per c arm. It does not resolve the position-posterior limitation: SD2 and SD4 fold 2 lie on the regional boundary in both arms. Every DS26-0070 SD4 fold places at least 9–50% of its untruncated position Gaussian outside the declared box. Its attractive held score therefore remains a diagnostic sensitivity, not reliable bounded-position posterior validation. DS26-0309 outcomes are unchanged, including its optimizer failures.','',
        'All 48 original model/arm/fold cells were rerun with phase cap 15. Native train/held IDs, guard groups, priors, empirical preprocessing, aliases, model cells, common RF start, and optimizer settings are unchanged. No original result was overwritten and no early-stopped result was reused. The frozen solver source exactly matches the SHA256 recorded by the original run. The separate protocol and source hashes were written before the cap15 outcomes, after the cap8 outcomes had been inspected. This is a controlled replication on reused folds, not new independent validation.','',
        'Held scores below are diagnostic even where numerical checks pass. Full-data nomination, point-noise preprocessing, likelihood powers, aliases and RF initialization persist; ancillary accepted-family/linear likelihoods remain omitted. Three overlapping random folds provide conditional development evidence, not independent generalization or production acceptance. Position accuracy and GPS were not accessed.','',
        '| Scan | Arm | Solver | SD | All-score gain vs legacy | Other-family gain | Phase closed | Optimizer success | Boundary | Numerically qualified |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f"|{r['case']}|{r['arm']}|{r['solver']}|{r['SD_scale']:g}|{r['all_gain_vs_legacy']:.3f}|{r['other_gain_vs_legacy']:.3f}|{r['phase_closed_folds']}/3|{r['optimizer_success_folds']}/3|{r['boundary_folds']}/3|{r['numerical_fit_qualified_folds']}/3|")
    lines += ['',
        'A numerically qualified row requires phase closure, successful position optimization, an interior regional solution, positive unfloored position curvature, and a positive normalized predictive covariance. Scores from unqualified rows are retained visibly; their improvement cannot be presented as validated prediction. Changing phase cap cannot cure a position optimizer termination or turn an untruncated boundary Laplace approximation into a valid bounded posterior. No additional starts or optimizer changes were introduced in this controlled comparison.','',
        'The covariance construction does not double count position and nuisance uncertainty in its local Gaussian interpretation. It uses `D + U Cov(beta|x,train) Uᵀ + J_mean Cov(x|train) J_meanᵀ`, where `J_mean` differentiates the total posterior predictive mean, including the training nuisance-mean response to position. The law of total covariance supplies these two terms; a component test matches their sum to the full joint Gaussian posterior covariance, including cross-correlations. Using only the orbital derivative while holding the nuisance posterior mean fixed would fail this test.','',
        'For a score expressed as −2 log density, the position precision is half its Hessian. The implementation restores both `log det(D + UUᵀ)` and `n log(2π)` in Hz units. Every cap15 all-held score was independently reconstructed with the full dense covariance. The diagonal noise plus shared nuisance and position covariance is positive definite when all noise SDs are positive; negative predictive quadratic forms and normalization disagreements are separately flagged. This algebraic audit does not calibrate the empirical noise model, missing Gamma uncertainty, nonlinear phase approximation or within-group residual correlation.','',
        'The original curvature floor is a heuristic based on the regional uniform-prior variance; it cannot justify a nonpositive Hessian. Any floor activation is therefore unqualified. A boundary cell is also unqualified because an untruncated Gaussian extends outside the allowed regional box. A better diagnostic held score at such a cell does not establish a generalizable model.','',
        'A separately labeled post-hoc box-tail audit also checks interior modes: marginal Gaussian tails give a lower bound (largest coordinate tail) and upper bound (sum of coordinate tails, capped at one) on posterior mass outside the 25 × 25 km regional box. A lower bound above 5% exposes a material truncated-prior mismatch even where the optimizer mode is interior. This diagnostic does not change the frozen scores or preregistered numerical flags; a passed numerical flag alone must not be read as calibrated Laplace coverage. See `position_box_audit.csv`.','',
        'Audit: '+json.dumps(audit,sort_keys=True)+'.','',
        'Artifacts: `protocol.json`/`.sha256`, unchanged-source `frozen_solver.py`, full per-job solver histories and covariance audits, `scores.csv`, `summary.csv`, `audit_summary.json`, and `results.json`. Reproduce with the same Python/environment as the parent predictive manifest and `.../extended/control.py`; tests are `.../extended/test_covariance.py`.']
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
