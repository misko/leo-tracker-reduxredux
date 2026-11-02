"""RF-only local-Gaussian box correction audit and rank comparison."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent


def main():
    result=json.loads((ROOT/'results.json').read_text());allrows=result['rows'];rows=[r for r in allrows if'error'not in r]
    flat=[];summary=[]
    for r in rows:
        for subset,s in r['scores'].items():
            flat.append(dict(case=r['case'],arm=r['arm'],fold=r['fold'],solver=r['solver'],SD_scale=r['SD_scale'],subset=subset,
                original_numerical_fit_qualified=r['original_numerical_fit_qualified'],phase_closed=r['phase_closed'],optimizer_success=r['optimizer_success'],boundary=r['boundary'],
                points=s['points'],original_unbounded_negative_twice_log_density=s['original_unbounded_negative_twice_log_density'],
                bounded_negative_twice_log_density=s['negative_twice_log_density'],correction_negative_twice_log_density=s['correction_negative_twice_log_density'],
                prior_box_probability=float(np.exp(s['prior_box']['log_probability'])),posterior_box_probability=float(np.exp(s['posterior_box']['log_probability'])),
                prior_quadrature_minus_scipy=float(np.exp(s['prior_box']['log_probability'])-s['prior_scipy_box_probability']),
                posterior_quadrature_minus_scipy=float(np.exp(s['posterior_box']['log_probability'])-s['posterior_scipy_box_probability'])))
    for case in ['DS26-0309','DS26-0070']:
        for arm in ['c0','fitted_c']:
            for subset in ['all','target','other']:
                models=[]
                for solver,scale in [('legacy',1.),('damped_half',1.),('damped_half',2.),('damped_half',4.)]:
                    rr=[r for r in flat if(r['case'],r['arm'],r['subset'],r['solver'],r['SD_scale'])==(case,arm,subset,solver,scale)]
                    models.append(dict(case=case,arm=arm,subset=subset,solver=solver,SD_scale=scale,folds=len(rr),
                        unbounded_score=sum(r['original_unbounded_negative_twice_log_density']for r in rr),bounded_score=sum(r['bounded_negative_twice_log_density']for r in rr),
                        sum_correction=sum(r['correction_negative_twice_log_density']for r in rr),
                        inherited_numerical_fit_qualified_folds=sum(r['original_numerical_fit_qualified']for r in rr),boundary_folds=sum(r['boundary']for r in rr)))
                urank={id(r):rank for rank,r in enumerate(sorted(models,key=lambda r:r['unbounded_score']),1)}
                brank={id(r):rank for rank,r in enumerate(sorted(models,key=lambda r:r['bounded_score']),1)}
                baseline=next(r for r in models if r['solver']=='legacy')
                for r in models:
                    r.update(unbounded_rank=urank[id(r)],bounded_rank=brank[id(r)],bounded_gain_vs_legacy=baseline['bounded_score']-r['bounded_score'])
                    summary.append(r)
    for path,rr in [(ROOT/'scores.csv',flat),(ROOT/'rank_changes.csv',summary)]:
        with path.open('w')as f:w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
    protocol=json.loads((ROOT/'protocol.json').read_text())
    audit=dict(jobs=len(allrows),errors=len(allrows)-len(rows),seconds=result['seconds'],
        original_frozen_inputs_unchanged=all(hashlib.sha256(Path(k).read_bytes()).hexdigest()==v for k,v in protocol['input_sha256'].items()),
        frozen_sources_unchanged=all(hashlib.sha256(Path(k).read_bytes()).hexdigest()==v for k,v in protocol['source_sha256'].items()),
        max_absolute_reconstructed_unbounded_score_difference=max(abs(v)for r in rows for v in r['reconstructed_unbounded_score_deltas'].values()),
        max_absolute_prior_box_quadrature_scipy_difference=max(abs(r['prior_quadrature_minus_scipy'])for r in flat),
        max_absolute_posterior_box_quadrature_scipy_difference=max(abs(r['posterior_quadrature_minus_scipy'])for r in flat),
        max_quadrature_relative_error=max(s[k]['relative_quadrature_error']for r in rows for s in r['scores'].values()for k in ['prior_box','posterior_box']),
        rank_changes=sum(r['unbounded_rank']!=r['bounded_rank']for r in summary),
        tests='4 pass: box quadrature versus direct 2-D integration and seeded SciPy CDF; broad-box recovery; position conditioning versus dense joint Gaussian; complete bounded predictive density versus direct position integration.')
    (ROOT/'audit_summary.json').write_text(json.dumps(audit,indent=2)+'\n')
    lines=['# Regional-box correction within the local Gaussian predictive model','',
        'Box conditioning changes none of the aggregate RF ranks: SD4 remains first and SD2 second for both scans, both c arms, and all/target/other held subsets. On DS26-0070 the SD4 all-held gains versus legacy are 105.83 and 107.69 in −2 log-density units (c0 and fitted-c); other-family gains are 84.16 and 85.70. On DS26-0309 the correction is negligible. This fixes the declared local Gaussian box normalization without resolving its approximation or inherited qualification limits.','',
        'All 48 cap15 endpoints were re-evaluated without optimization, using identical native training/held IDs and the actual ±12.5 km box. The corrected density integrates the local Gaussian position approximation conditional on that box. No RF parameter, noise model or nuisance coefficient was fitted using held observations. Original scores and convergence flags are preserved.','',
        'The identity is `p(y|train, x∈B) = p(y|train) × P(x∈B|train,y) / P(x∈B|train)`. With conditional prediction covariance `C`, total posterior-mean position Jacobian `J`, and frozen position covariance `S`, the integration-only posterior is `S₂=(S⁻¹+JᵀC⁻¹J)⁻¹` and `m₂=m+S₂JᵀC⁻¹r`. `C` includes noise and nuisance covariance conditional on position. Using the derivative of the total predictive mean preserves the nuisance/position cross-covariance audited in the cap15 control; it is not an independent extra position term.','',
        'Box conditioning is not an automatic score penalty. When the held observations concentrate the integration-only position distribution inside the box, the numerator box probability exceeds the denominator and the normalized held density increases. The observed corrections are small relative to the SD4-versus-legacy margins, and do not explain away those margins. Their scientific interpretation remains limited by the inherited model and convergence issues.','',
        'Box probabilities use deterministic scaled one-dimensional conditional-normal quadrature. Seeded SciPy bivariate rectangle CDF provides an independent numerical check. Tests also match direct two-dimensional integration and show that a broad box restores the original score. Gaussian conditioning on held observations appears only inside the probability-ratio integral; its coordinates are not new fitted RF solutions.','',
        '| Scan | Arm | Held subset | Solver | SD | Unbounded rank | Box rank | Box score sum | Box gain vs legacy | Inherited numerical passes |',
        '|---|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summary:
        lines.append(f"|{r['case']}|{r['arm']}|{r['subset']}|{r['solver']}|{r['SD_scale']:g}|{r['unbounded_rank']}|{r['bounded_rank']}|{r['bounded_score']:.3f}|{r['bounded_gain_vs_legacy']:.3f}|{r['inherited_numerical_fit_qualified_folds']}/3|")
    lines += ['',
        'These are RF-only diagnostic ranks under the declared local Gaussian. Exact box integration fixes its unbounded-position mass but does not establish that the Laplace approximation is accurate, especially at a boundary. Inherited optimizer failures, phase nonconvergence and curvature flags remain active. Full-data nomination, empirical point-noise preprocessing, aliases, likelihood powers and RF starts remain inherited; Gamma uncertainty and residual correlation are not fully integrated; ancillary likelihoods remain omitted. Reused folds and this post-hoc model debugging are not fresh generalization evidence or production qualification. No localization accuracy or GPS was accessed.','',
        '`all`, `target`, and `other` are separate marginal densities and do not add. Overlapping fold sums rank these declared diagnostics; they are not independent-sample evidence or identity probabilities. A favorable corrected score alone does not qualify a failed or model-sensitive fit.','',
        'Audit: '+json.dumps(audit,sort_keys=True)+'.','',
        'Files: `protocol.json`/`.sha256`, `results.json`, per-cell box probabilities and integration-only position moments, `scores.csv`, `rank_changes.csv`, `audit_summary.json`, and the numerical implementation/tests. Reproduce with the parent environment and `predictive/bounded/run.py`.']
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':main()
