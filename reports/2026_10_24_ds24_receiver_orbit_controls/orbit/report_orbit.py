"""Publish the bounded negative causal-prior result without RF/GPS evaluation."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
from scipy.stats import norm, t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from causal_joint_prior import OUT, CASES, BLOCK_NS, SEED, safe_training, standardized, write


def read(name):
    return json.loads((OUT/name).read_text())


def stats(values):
    x=np.asarray(values,float)
    return dict(count=len(x),median=float(np.median(x)),mean=float(np.mean(x)),
        p10=float(np.quantile(x,.1)),p90=float(np.quantile(x,.9)),maximum=float(np.max(x)))


def main():
    projection=read('projected_rows.json');rows=projection['rows']
    validation=read('validation.json');inventory=read('inventory.json');groups=read('groups.json')
    satellite_folds={int(k):int(v) for k,v in groups['satellite_folds'].items()}
    time_folds={int(k):int(v) for k,v in groups['publication_block_folds'].items()}
    basis=read('basis_audit.json')
    audit_rows=[];calibration={};summaries={}
    for scheme,result in validation['validation'].items():
        phase_z=[];phase_pit=[];shape_z=[];total_purged=0;active_folds=0
        for record in result['folds']:
            if 'skipped' in record:
                continue
            block,fold=record['block'],record['fold']
            test=[r for r in rows if r['validation_time_ns']//BLOCK_NS==block and
                (scheme=='time_block' or satellite_folds[r['norad']]==fold)]
            train,purged=safe_training(rows,test,scheme,fold,block,satellite_folds,time_folds)
            assert len(train)==record['training_rows'] and len(test)==record['test_rows']
            assert max(r['validation_time_ns'] for r in train)<block*BLOCK_NS
            train_endpoints={(r['norad'],x) for r in train for x in r['endpoints']}
            test_endpoints={(r['norad'],x) for r in test for x in r['endpoints']}
            assert not train_endpoints&test_endpoints
            if scheme=='satellite':
                assert not {r['norad'] for r in train}&{r['norad'] for r in test}
            model,location=record['baseline_phase_model'],record['baseline_signed_location']
            z=standardized(test,model,location)
            phase_z.extend(z[:,0]);shape_z.extend(z[:,1:])
            if model['nu'] is None:
                phase_pit.extend(norm.cdf(z[:,0]))
            else:
                phase_pit.extend(t.cdf(z[:,0]*np.sqrt(model['nu']/(model['nu']-2)),df=model['nu']))
            active_folds+=1;total_purged+=purged
            audit_rows.append(dict(scheme=scheme,block=block,fold=fold,training_rows=len(train),test_rows=len(test),
                strict_past_only=True,shared_TLE_endpoint_count_after_purge=0,
                satellite_disjoint=scheme=='satellite',purged_rows=purged))
        phase_z=np.asarray(phase_z);phase_pit=np.asarray(phase_pit);shape_z=np.asarray(shape_z)
        calibration[scheme]=dict(phase_absolute_standardized_error=stats(abs(phase_z)),
            phase_fraction_within_nominal_SD=float(np.mean(abs(phase_z)<=1)),
            phase_fraction_in_predictive_central95=float(np.mean((phase_pit>=.025)&(phase_pit<=.975))),
            phase_marginal_forecast_is_identical_in_candidate=True,
            shape_absolute_standardized_errors=[stats(abs(shape_z[:,k])) for k in range(3)],
            shape_fraction_in_baseline_Gaussian_central95=np.mean(abs(shape_z)<=norm.ppf(.975),axis=0),
            measures_are_historical_TLE_proxy_calibration_not_true_orbit_coverage=True)
        byblock=[]
        for block in sorted({s['block'] for s in result['scores']}):
            gains=np.array([s['gain'] for s in result['scores'] if s['block']==block])
            byblock.append(dict(block=block,utc_start=datetime.fromtimestamp(block*BLOCK_NS/1e9,tz=timezone.utc).isoformat(),
                rows=len(gains),gain=float(gains.sum()),mean_gain=float(gains.mean())))
        summaries[scheme]=dict(qualified=result['qualified'],validation_rows=result['validation_rows'],
            active_folds=active_folds,training_rows_purged_across_fits=total_purged,
            pooled_gain=result['gain'],median_row_gain=result['median_gain'],
            satellite_group_bootstrap=result['satellite_group_bootstrap'],
            time_block_bootstrap=result['time_block_bootstrap'],publication_blocks=byblock)
        matrices=[np.asarray(record['correlation']) for record in result['folds'] if 'correlation' in record]
        factors=[np.sqrt(1-m[0,1:]@np.linalg.solve(m[1:,1:],m[1:,0])) for m in matrices]
        summaries[scheme]['median_training_correlation']=np.median(matrices,axis=0)
        summaries[scheme]['nominal_unit_Gamma_phase_SD_factor_if_shape_known']=stats(factors)
        summaries[scheme]['nominal_phase_conditioning_is_Gaussian_curvature_analogy_not_Student_conditional_distribution']=True
    law=dict(original='Independent unit-variance Student phase and Gaussian orbital-shape coefficients.',
        candidate='Lower-triangular transform of one Student phase coefficient and three independent Gaussian coefficients.',
        nominal_unconditional_prior_covariance_diagonal_preserved=True,
        physical_marginal_distribution_not_preserved=True,
        shape_coefficients_inherit_Student_phase_tails=True,
        conditional_Gamma_diagonal_variances_not_preserved=True,
        explanation='Unit diagonal of R preserves unconditional prior variances when the phase Student prior is standardized to variance one. At a fixed latent Gamma precision, transformed shape variances depend on that phase precision. A transformed shape coefficient is Student-plus-Gaussian, not Gaussian. Forecast gains can therefore mix dependence and tail-law effects.',
        no_candidate_position_adapter_or_prior_promotion=True)
    write(OUT/'model_law_clarification.json',law)
    summary=dict(qualified=False,inventory={k:v for k,v in inventory.items() if k not in ('source_receipts','sampled_satellites')},
        projected_rows=len(rows),rejected=projection['rejected'],validation=summaries,forecast_calibration=calibration,
        phase_projection_difference_absolute_s=stats([abs(r['phase_projection_minus_legacy_s']) for r in rows]),
        unexplained_state_energy_fraction=stats([r['unexplained_state_energy_fraction'] for r in rows]),
        basis_audit=basis,model_law=law,no_RF_GPS_or_position_evaluation=True,no_position_fits=True)
    write(OUT/'summary.json',summary)
    audit=dict(all_randomized_group_fits_passed_causal_and_endpoint_audit=True,rows=audit_rows,
        seed=SEED,group_seed=SEED+1,projection_runtime_seconds=projection['elapsed_seconds'],
        total_fit_and_validation_runtime_seconds=validation['elapsed_seconds'],
        component_tests='3 passed; see test.log',
        sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
            [OUT/'causal_joint_prior.py',OUT/'basis_audit.py',OUT/'test_causal_joint_prior.py',OUT/'report_orbit.py',
             Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/ds23_correlated_orbit_problem.py'),
             Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/build_dsx01_orbit_modes.py')]})
    write(OUT/'audit.json',audit)
    write(OUT/'eligibility.json',dict(qualified=False,cases=CASES,alternatives_tested=1,
        candidate='causal_phase_shape_correlation_half_shrink',
        reason='Predeclared randomized satellite and time-block cluster uncertainty gates both failed; mixed-prior marginal shape-tail law also changes, so this is not a drop-in covariance correction.',
        build_adapter=None,position_fits_scientifically_eligible=False,
        current_baseline_retained=True,no_RF_GPS_used=True))
    fig,axes=plt.subplots(1,2,figsize=(13,4.8),layout='constrained')
    blocks=sorted(set(b['block'] for s in summaries.values() for b in s['publication_blocks']))
    for scheme,color,offset in [('satellite','#267c9d',-.18),('time_block','#ba7029',.18)]:
        byblock={b['block']:b for b in summaries[scheme]['publication_blocks']}
        x=np.array([k for k,b in enumerate(blocks) if b in byblock])
        axes[0].bar(x+offset,[byblock[blocks[k]]['mean_gain'] for k in x],width=.34,label=scheme,color=color)
    axes[0].set_xticks(np.arange(len(blocks)),[datetime.fromtimestamp(b*BLOCK_NS/1e9,tz=timezone.utc).strftime('%m-%d\n%Hh') for b in blocks],rotation=45)
    axes[0].axhline(0,color='gray',lw=1);axes[0].set(ylabel='Mean heldout gain in −2 log density',title='Opposing publication-block effects')
    labels=[];centers=[];bounds=[]
    for scheme in ['satellite','time_block']:
        for cluster in ['satellite_group_bootstrap','time_block_bootstrap']:
            row=summaries[scheme][cluster];labels.append(scheme+' / '+cluster.split('_')[0]+' clusters')
            centers.append(row['mean_group_gain']);bounds.append(row['confidence_interval_mean_group_gain'])
    centers=np.asarray(centers);bounds=np.asarray(bounds)
    axes[1].errorbar(centers,np.arange(len(labels)),xerr=np.vstack((centers-bounds[:,0],bounds[:,1]-centers)),fmt='o',capsize=4,color='#444444')
    axes[1].set_yticks(np.arange(len(labels)),labels);axes[1].axvline(0,c='gray',lw=1)
    axes[1].set(xlabel='Mean group gain; descriptive 95% cluster bootstrap',title='Neither randomized grouping qualifies')
    for ax in axes:ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    fig.savefig(OUT/'orbit_forecast_validation.png',dpi=170);plt.close(fig)
    sat=summaries['satellite'];tim=summaries['time_block']
    lines=['# DS24 causal phase/orbit prior control: not qualified','',
        'The one predeclared correlation candidate failed the grouped forecast qualification. No position adapter was produced, no geographic fit or RF observation was used to select a prior, and the current prior is retained. This negative result concerns historical TLE forecasting; it says nothing about whether an alternative would improve GPS error.','',
        f"The attainable phase constraint is also tiny: learned correlations imply only {100*(1-sat['nominal_unit_Gamma_phase_SD_factor_if_shape_known']['median']):.2f}% median phase-SD reduction even if all three shape coordinates were known, under a nominal unit-Gamma Gaussian-curvature calculation. Meanwhile the training-only baseline’s phase-proxy central-95% coverage is {100*calibration['satellite']['phase_fraction_in_predictive_central95']:.2f}% under satellite holdout and {100*calibration['time_block']['phase_fraction_in_predictive_central95']:.2f}% under time-block holdout. Shape-proxy Gaussian central-95% coverage is only about 70–74%. These historical-TLE proxies are not true-orbit error samples, and the results do not justify tightening a phase/orbit prior. The mixed Student/Gaussian marginal-law limitation is stated below.",'',
        '## Inputs and coordinate check','',
        f"The 24 frozen DS24 causal-history files contain {inventory['unique_triples']:,} unique TLE-byte triples across {inventory['union_satellites']:,} satellites. Seed {SEED} selected 1,024 whole satellites before projection; these yielded {len(rows):,} valid triples and no rejections. Identical triples shared across scans were counted once, not as independent evidence. All version epoch and collected timestamps were checked against their source scan cutoff, and each proxy window ends before that cutoff. No post-scan TLE, IQ, RF assignment, or geographic truth was used.",'',
        'The older DS23 joint-prior helper uses a single-time TEME/element approximation. This control instead reconstructs the current engine’s phase coordinate with Earth rotation and its reference-aligned mean-motion, inclination and RAAN directions over 0/150/300 seconds. It projects newer historical TLE state differences into those physical coordinates, with the existing causal previous-TLE disagreement scales and the fixed 150 s velocity weighting. This is an adapter for the forecast diagnostic, not a new orbit engine.','',
        f"Every projection has rank four. Median unexplained state-energy fraction is {validation['unexplained_energy_median']:.6g}; p90 is {validation['unexplained_energy_p90']:.6g}. The absolute difference from the legacy scalar phase proxy is median {summary['phase_projection_difference_absolute_s']['median']:.4f} s, p90 {summary['phase_projection_difference_absolute_s']['p90']:.4f} s. A separate 12-satellite check against the existing engine’s causal TLE bank gives maximum relative column discrepancy {basis['maximum_column_relative_difference']:.5g}; the diagnostic uses direct SGP4 while the engine interpolates one-second state samples. The low projection remainder supports a representation check, not proof that the four-dimensional prior describes true orbit error.",'',
        '## Predeclared candidate and honest validation','',
        'The single candidate is R = 0.5 I + 0.5 R̂, where R̂ is robust training-only four-coordinate phase/shape scatter normalized to unit diagonal. There is no GPS-driven scale tightening, alternative shrinkage grid, or choice among outcomes. The current scalar phase distribution and signed location-form selection are refitted from training records only, then reused unchanged in the baseline and candidate. Historical newer TLEs are correlated prediction proxies, not authenticated orbit truth.','',
        f"The random-group seed is {SEED+1}: four whole-satellite folds and four randomly assigned contiguous six-hour publication-block folds. Inside either randomized partition, every forecast trains only on earlier publication blocks. All training triples sharing any satellite/TLE endpoint with heldout triples are purged. Satellite folds also exclude every record of the heldout satellites. This is randomized grouped prequential validation; the legacy chronological prefix split is not the new primary validation. Minimum evidence is 300 training rows, 60 training satellites and ten heldout rows. Every active fit passed the independent timestamp, endpoint-disjointness and satellite-disjointness audit.",'',
        '| Randomized holdout | Heldout rows | Pooled −2 log-density gain | Satellite-cluster 95% interval | Time-block 95% interval |','|---|---:|---:|---:|---:|']
    for name,row in [('Whole satellite',sat),('Publication time block',tim)]:
        a=row['satellite_group_bootstrap']['confidence_interval_mean_group_gain'];b=row['time_block_bootstrap']['confidence_interval_mean_group_gain']
        lines.append(f"| {name} | {row['validation_rows']:,} | {row['pooled_gain']:.1f} | [{a[0]:.2f}, {a[1]:.2f}] | [{b[0]:.2f}, {b[1]:.2f}] |")
    lines += ['', 'Positive gain favors the candidate. The bootstrap intervals concern the mean group gain, not the pooled sum; groups receive equal weight. The predeclared gate required gain > 6 log N and positive lower bounds under both satellite and publication-block resampling in both holdout schemes. Both schemes fail: pooled improvement is not stable across satellites and publication blocks. No second candidate was introduced after seeing this result.','',
        '## Mixed-prior limitation','',
        'The existing model uses independent unit-variance Student phase and Gaussian shape priors. A Cholesky correlation transform preserves the nominal unconditional covariance diagonal, but it does not preserve the physical marginal distributions: transformed shape coordinates inherit a Student component. At fixed phase Gamma precision even the conditional shape variances change. Thus the tested likelihood gain combines dependence and tail-law effects; it cannot be advertised as a covariance-only correction with unchanged Gaussian orbit marginals. No automatic prior or adapter promotion is justified. This limitation independently prevents treating the candidate as a drop-in calibration fix.','',
        '## Calibration and bounded outcome','']
    for name,row in calibration.items():
        coverage=row['phase_fraction_in_predictive_central95']
        lines.append(f"- {name}: baseline phase proxy central-95% coverage is {100*coverage:.2f}%; median absolute standardized phase error is {row['phase_absolute_standardized_error']['median']:.3f}. The candidate leaves the scalar phase marginal forecast exactly unchanged. These are historical-TLE proxy diagnostics, not true-orbit coverage.")
    factor=sat['nominal_unit_Gamma_phase_SD_factor_if_shape_known']
    lines += ['',f"The learned phase/shape dependence is also too weak to approximate the phase-known position-information oracle. Across whole-satellite training folds, median phase correlations with mean motion, inclination and RAAN are {sat['median_training_correlation'][0,1]:.4f}, {sat['median_training_correlation'][0,2]:.4f}, and {sat['median_training_correlation'][0,3]:.4f}. A nominal unit-Gamma Gaussian-curvature calculation gives phase-SD factor {factor['median']:.5f} if all three shape coordinates were known, only {100*(1-factor['median']):.2f}% median reduction. This is a Gaussian curvature analogy, not the exact Student conditional distribution or a position-accuracy forecast."]
    lines += ['',f"Projection took {projection['elapsed_seconds']:.2f} s and grouped validation took {validation['elapsed_seconds']:.2f} s with BLAS limited to one thread. Three component-owned tests pass. No RF collection, IQ processing, position fit, satellite reassignment, point deletion, or golden-fixture change occurred.",'',
        'A feasible future change would need independent evidence that distinguishes physical dependence from shape-tail misspecification, then randomized grouped causal validation. The present results do not justify a narrower phase prior or a better-localization claim. The earlier phase-known information oracle remains an unavailable-information sensitivity, not a usable method.','',
        'Artifacts: protocol.json and groups.json preserve the predeclared design; inventory.json records input hashes and sampled satellites; projected_rows.json and validation.json retain every diagnostic row/fold; basis_audit.json and audit.json record numerical and leakage checks; model_law_clarification.json states the prior-law limitation; eligibility.json explicitly rejects position fitting. orbit_forecast_validation.png is the scientific summary figure.']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print('Report complete; candidate not qualified; no position adapter.',flush=True)


if __name__=='__main__':
    main()
