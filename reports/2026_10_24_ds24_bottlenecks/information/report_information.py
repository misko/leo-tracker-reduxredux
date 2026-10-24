"""Descriptive report after RF-only local diagnostics; evaluation GPS only here."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from prototype_dsx01_continuous_position import CENTER, latlon

HERE = Path(__file__).resolve().parent
HALF = Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
GPS_EVALUATION_ONLY = (37.849061591561885, -122.48574968092912)
FULL = 'curved_plus_predictive_fixed_Gamma_surrogate'


def read(path):
    return json.loads(path.read_text())


def encode(x):
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, np.generic):
        return x.item()
    raise TypeError(type(x).__name__)


def stats(values):
    x = np.asarray(values, float)
    return dict(mean=float(np.mean(x)), median=float(np.median(x)), minimum=float(np.min(x)),
        maximum=float(np.max(x)), p10=float(np.quantile(x, .1)), p90=float(np.quantile(x, .9)))


def angle(a, b):
    return float(np.degrees(np.arccos(np.clip(abs(np.asarray(a)@b), 0., 1.))))


def main():
    source = read(HERE/'all_cases.json')['rows']
    # With no predictive tracks the surrogate is exactly the curved design.
    for case in source:
        for record in case['arms'].values():
            if record[FULL] is None:
                record[FULL] = record['curved']
    summary = {}
    evaluation = []
    paired = [r for r in csv.DictReader((HALF/'tables/paired_errors.csv').open()) if r['method']=='baseline']
    errors = {(r['case'], r['arm']):r for r in paired}
    # Exact inverse of the engine's affine east/north -> lat/lon map. The
    # information matrices are in these engine km coordinates, not geodesic km.
    truth_xy = np.array([(GPS_EVALUATION_ONLY[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),
        (GPS_EVALUATION_ONLY[0]-CENTER[0])*111.0])
    np.testing.assert_allclose(latlon(truth_xy), GPS_EVALUATION_ONLY, rtol=0, atol=1e-12)
    for arm in ['c0', 'fitted_c']:
        records = [r['arms'][arm] for r in source]
        byvariant = {}
        for variant in ['curved', FULL]:
            rows = [s[variant] for s in records]
            result = dict(local_major_sigma_km=stats([r['all']['principal_sigma_km'][0] for r in rows]),
                nuisance_known_major_sigma_km=stats([r['all_nuisance_known']['principal_sigma_km'][0] for r in rows]),
                retained_trace_fraction=stats([r['fraction_trace_information_retained'] for r in rows]),
                subset_major_sigma_km={k:stats([r['subsets'][k]['principal_sigma_km'][0] for r in rows]) for k in rows[0]['subsets']},
                freeze_major_sigma_km={k:stats([r['freeze_controls'][k]['principal_sigma_km'][0] for r in rows if k in r['freeze_controls']]) for k in rows[0]['freeze_controls']},
                noise_control_major_sigma_km={k:stats([r['fixed_nuisance_prior_noise_controls'][k]['principal_sigma_km'][0] for r in rows]) for k in rows[0]['fixed_nuisance_prior_noise_controls']},
                noise_control_sigma_reduction={k:stats([1-r['fixed_nuisance_prior_noise_controls'][k]['principal_sigma_km'][0]/r['all']['principal_sigma_km'][0] for r in rows]) for k in rows[0]['fixed_nuisance_prior_noise_controls']},
                band_weak_axis_separation_deg=stats([angle(r['subsets']['low']['weak_axis_east_north'],r['subsets']['high']['weak_axis_east_north']) for r in rows]),
                receiver_weak_axis_separation_deg=stats([angle(r['subsets']['rx1']['weak_axis_east_north'],r['subsets']['rx2']['weak_axis_east_north']) for r in rows]),
                families_low_high_shared=stats([r['families_low_high_shared'] for r in rows]),
                families_rx1_rx2_shared=stats([r['families_rx1_rx2_shared'] for r in rows]),
                group_max_abs_weak_correlations={k:stats([r['correlations']['groups'][k]['maximum_absolute_weak_axis_correlation'] for r in rows if k in r['correlations']['groups']]) for k in rows[0]['correlations']['groups']})
            for subset in ['low','high','rx1','rx2']:
                result['full_sigma_reduction_vs_'+subset] = stats([1-r['all']['principal_sigma_km'][0]/r['subsets'][subset]['principal_sigma_km'][0] for r in rows])
            byvariant[variant] = result
        hs = [s['actual_objective_half_Hessian_step_0p2'] for s in records]
        summary[arm] = dict(variants=byvariant, actual_half_Hessian_minimum_eigenvalue=stats([s['eigenvalues'][0] for s in hs]),
            actual_Hessian_step_relative_change=stats([s['actual_objective_Hessian_relative_change'] for s in records]),
            replay_absolute_objective_gap=stats([abs(s['replay_objective_difference']) for s in records]),
            derivative_relative_change=stats([s['finite_difference_relative_change'] for s in records]))
        for parent, s in zip(source, records):
            error = np.asarray(s['endpoint_east_north_km'])-truth_xy
            info = np.asarray(s[FULL]['all']['information_hz_weighted_per_km2'])
            actual_half_hessian = np.asarray(s['actual_objective_half_Hessian_step_0p2']['negative_twice_elbo_Hessian_divided_by_two'])
            q = float(error@info@error)
            qh = float(error@actual_half_hessian@error)
            evaluation.append(dict(case=parent['case'], arm=arm, evaluated_error_east_north_km=error,
                persisted_evaluation_error_km=float(errors[parent['case'],arm]['all_channels']),
                apparent_squared_Mahalanobis_fixed_Gamma_surrogate=q,
                apparent_squared_Mahalanobis_actual_half_Hessian=qh,
                chi2_2_survival_reference_only=float(np.exp(-q/2)),
                no_calibrated_confidence_or_coverage_claim=True))
        erows=[r for r in evaluation if r['arm']==arm]
        summary[arm]['evaluation_only'] = dict(
            apparent_squared_Mahalanobis_fixed_Gamma=stats([r['apparent_squared_Mahalanobis_fixed_Gamma_surrogate'] for r in erows]),
            apparent_squared_Mahalanobis_actual_Hessian=stats([r['apparent_squared_Mahalanobis_actual_half_Hessian'] for r in erows]),
            count_below_chi2_2_95_reference=sum(r['apparent_squared_Mahalanobis_fixed_Gamma_surrogate']<=5.991464547 for r in erows),
            count_below_chi2_2_99_reference=sum(r['apparent_squared_Mahalanobis_fixed_Gamma_surrogate']<=9.210340372 for r in erows),
            chi2_2_95_reference=5.991464547, chi2_2_99_reference=9.210340372,
            descriptive_only_no_calibrated_confidence_claim=True)
    summary['paired_c_effect'] = dict(
        mean_RMS_hz_c0=float(np.mean([r['arms']['c0']['RMS_hz'] for r in source])),
        mean_RMS_hz_fitted_c=float(np.mean([r['arms']['fitted_c']['RMS_hz'] for r in source])),
        RMS_hz_fitted_minus_c0=stats([r['arms']['fitted_c']['RMS_hz']-r['arms']['c0']['RMS_hz'] for r in source]),
        full_major_sigma_ratio_fitted_over_c0=stats([r['arms']['fitted_c'][FULL]['all']['principal_sigma_km'][0]/r['arms']['c0'][FULL]['all']['principal_sigma_km'][0] for r in source]),
        evaluation_error_mean_km={a:float(np.mean([float(r['all_channels']) for r in paired if r['arm']==a])) for a in ['c0','fitted_c']})
    (HERE/'summary.json').write_text(json.dumps(summary, default=encode, indent=2)+'\n')
    (HERE/'evaluation_only.json').write_text(json.dumps(dict(rows=evaluation,GPS_evaluation_only=GPS_EVALUATION_ONLY,
        engine_center_latlon=CENTER, evaluation_truth_engine_east_north_km=truth_xy,
        error_coordinates='Exact inverse of prototype_dsx01_continuous_position.latlon: north scale111.0, east scale111.32*cos(CENTER latitude).',
        objective_Hessian_conditioning='Persisted phase-linearization reference held fixed; nuisance coefficients and Gamma variables reoptimized. Not fully phase-refreshed nonlinear curvature.'),default=encode,indent=2)+'\n')
    # Scientific figures are standalone files; plotted SDs are conditional local diagnostics.
    fig, grid=plt.subplots(2,2,figsize=(12,10),layout='constrained')
    axes=grid.ravel()
    fitted=[r['arms']['fitted_c'][FULL] for r in source]
    calibrated=[r['arms']['fitted_c']['curved'] for r in source]
    for name,color in [('low','#247ba0'),('high','#c47c17'),('rx1','#7f70ad'),('rx2','#58924c')]:
        axes[0].scatter([r['subsets'][name]['principal_sigma_km'][0] for r in calibrated],
            [r['all']['principal_sigma_km'][0] for r in calibrated],label=name,c=color,s=22,alpha=.7)
    axes[0].plot([0,1.8],[0,1.8],':',c='gray');axes[0].set(xlabel='Subset major local SD (km)',ylabel='All curved data major local SD (km)',title='Curved calibration: extra band / RX helps');axes[0].legend(fontsize=8)
    categories=['all_nuisance_known','phase_and_orbit','phase','orbit','receiver_all','all']
    for rows,color,label,offset in [(calibrated,'#247ba0','Curved only',-.15),(fitted,'#c47c17','+ predictive Gaussian surrogate',.15)]:
        arrays=[]
        for category in categories:
            arrays.append([r[category]['principal_sigma_km'][0] if category in ['all','all_nuisance_known'] else r['freeze_controls'][category]['principal_sigma_km'][0] for r in rows])
        artists=axes[1].boxplot(arrays,positions=np.arange(1,7)+offset,widths=.25,showfliers=False,patch_artist=True)
        for box in artists['boxes']:box.set_facecolor(color);box.set_alpha(.7)
        axes[1].plot([],[],c=color,label=label)
    axes[1].set_xticks(np.arange(1,7),['All known','Phase + orbit','Phase','Orbit','RX all','All uncertain']);axes[1].legend(fontsize=8)
    axes[1].tick_params(axis='x',rotation=45);axes[1].set(yscale='log',ylabel='Major local SD (km)',title='Oracle nuisance-freezing controls')
    for a,color in [('c0','#777777'),('fitted_c','#168b91')]:
        erows=[r for r in evaluation if r['arm']==a]
        axes[3].scatter([r['apparent_squared_Mahalanobis_fixed_Gamma_surrogate'] for r in erows],
            [r['persisted_evaluation_error_km'] for r in erows],s=25,c=color,label=a)
    axes[3].axvline(5.991464547,c='gray',ls=':',label='χ²₂ 95% reference')
    axes[3].set(xlabel='Apparent squared Mahalanobis error',ylabel='Evaluation error (km)',title='Reference comparison; no confidence calibration');axes[3].legend(fontsize=8)
    for rows,color,label in [(calibrated,'#247ba0','Curved only'),(fitted,'#c47c17','+ predictive Gaussian surrogate')]:
        multipliers=[1,4,100]
        values=[[r['all']['principal_sigma_km'][0] for r in rows],
            [r['fixed_nuisance_prior_noise_controls']['sigma_half_weights_times4']['principal_sigma_km'][0] for r in rows],
            [r['fixed_nuisance_prior_noise_controls']['sigma_tenth_weights_times100']['principal_sigma_km'][0] for r in rows]]
        axes[2].plot(multipliers,[np.median(v) for v in values],'o-',c=color,label=label)
    axes[2].set(xscale='log',xlabel='Hypothetical point-noise precision multiplier',ylabel='Median major local SD (km)',title='Frequency precision alone, fixed nuisance priors');axes[2].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2)
    fig.savefig(HERE/'position_information.png',dpi=170);plt.close(fig)
    f=summary['fitted_c']['variants'][FULL]
    c=summary['c0']['variants'][FULL]
    primary=summary['fitted_c']['variants']['curved']
    lines=['# DS24 information bottleneck: matched observations and identities','',
        'All 24 common DS24 cases were replayed at the persisted all-channel cavity solution in both c = 0 and fitted-c arms. Every channel/RX subset retains the same all-data endpoint, candidate identities, aliases, point mask, geometry, noise Gamma precision, nuisance prior and causal TLE inputs. This is not a rerun of the independently fitted channel halves. GPS enters only evaluation_only.json and this report. No RF collection or post-scan TLE was used.','',
        '## Measured result','',
        f"The primary calibration-only diagnostic uses exactly the curved observations that update the current algorithm's nuisance coefficients. For fitted c its median local major-axis SD is {primary['local_major_sigma_km']['median']:.3f} km; freezing every nuisance gives {1000*primary['nuisance_known_major_sigma_km']['median']:.2f} m. Only {100*primary['retained_trace_fraction']['median']:.5f}% of raw position-information trace survives nuisance elimination. Freezing phase alone gives {primary['freeze_major_sigma_km']['phase']['median']:.3f} km; freezing phase + orbit gives {primary['freeze_major_sigma_km']['phase_and_orbit']['median']:.3f} km; freezing all receiver terms gives {primary['freeze_major_sigma_km']['receiver_all']['median']:.3f} km. This is local information conditional on the supplied model and Gamma variables, not a fundamental CRLB or calibrated uncertainty.",'',
        f"A separate curved-plus-predictive Gaussian surrogate has median major local SD {f['local_major_sigma_km']['median']:.3f} km and all-nuisance-known value {1000*f['nuisance_known_major_sigma_km']['median']:.2f} m. This surrogate includes predictive rows through a joint fixed-Gamma Gaussian marginal and is not permission to update calibration from those rows. The actual algorithm's linear rows remain predictive-only. Five cases have no predictive entries, so the two diagnostics coincide there.",'',
        '| Same full-solution data slice | Curved major local SD (km) | Curved reduction from adding remaining data | + predictive Gaussian surrogate SD (km) |','|---|---:|---:|---:|']
    for name in ['low','high','rx1','rx2']:
        lines.append(f"| {name} | {primary['subset_major_sigma_km'][name]['median']:.3f} | {100*primary['full_sigma_reduction_vs_'+name]['median']:.1f}% | {f['subset_major_sigma_km'][name]['median']:.3f} |")
    lines += [f"| all | {primary['local_major_sigma_km']['median']:.3f} | — | {f['local_major_sigma_km']['median']:.3f} |",'',
        'Every subset satisfied the positive-semidefinite information ordering: adding a band or receiver helps at fixed identities/masks. This need not improve each independently refitted endpoint: those runs can change associations, masks, robust weights and prior compromises.','',
        '| Unavailable-information oracle | Curved major local SD (km) | + predictive Gaussian surrogate SD (km) |','|---|---:|---:|']
    for name in ['phase','orbit','phase_and_orbit','receiver_offsets','receiver_drifts','receiver_smooth','receiver_all','rf_c','all_fragment_bias']:
        lines.append(f"| Freeze {name} | {primary['freeze_major_sigma_km'][name]['median']:.3f} | {f['freeze_major_sigma_km'][name]['median']:.3f} |")
    lines += ['',f"In the primary curved-only diagnostic, the median maximum absolute correlation of the weak position axis with an individual phase coefficient is {primary['group_max_abs_weak_correlations']['phase']['median']:.3f}; with an orbit coefficient {primary['group_max_abs_weak_correlations']['orbit']['median']:.3f}; with c {primary['group_max_abs_weak_correlations']['rf_c']['median']:.3f}. Correlations and oracle controls indicate confounding, not that those nuisance values are known or may safely be fixed in inference.",'',
        '## More precise frequency measurements at the same nuisance priors','',
        '| Hypothetical point-noise change | Curved major local SD (km) | Curved median reduction | + predictive Gaussian surrogate SD (km) |','|---|---:|---:|---:|']
    for name,label in [('sigma_half_weights_times4','σ / 2; precision × 4'),('sigma_tenth_weights_times100','σ / 10; precision × 100')]:
        lines.append(f"| {label} | {primary['noise_control_major_sigma_km'][name]['median']:.3f} | {100*primary['noise_control_sigma_reduction'][name]['median']:.1f}% | {f['noise_control_major_sigma_km'][name]['median']:.3f} |")
    lines += ['', 'These are fixed-Gamma counterfactuals, with unchanged observations and nuisance priors. They do not establish that an estimator or waveform can attain those frequency errors. The observed bottleneck is compared directly with the much stronger oracle phase/orbit constraints above.','',
        '## c = 0 versus fitted c','',
        f"The full major local SD median is {c['local_major_sigma_km']['median']:.3f} km for c = 0 and {f['local_major_sigma_km']['median']:.3f} km for fitted c. The median per-case fitted/c0 SD ratio is {summary['paired_c_effect']['full_major_sigma_ratio_fitted_over_c0']['median']:.4f}. The mean curved RMS changes from {summary['paired_c_effect']['mean_RMS_hz_c0']:.3f} to {summary['paired_c_effect']['mean_RMS_hz_fitted_c']:.3f} Hz; the separately evaluated mean position error changes from {summary['paired_c_effect']['evaluation_error_mean_km']['c0']:.3f} to {summary['paired_c_effect']['evaluation_error_mean_km']['fitted_c']:.3f} km. Frequency fit improvement therefore did not improve mean location here.",'',
        '## Geometry and physical interpretation','',
        f"For curved calibration data the median weak-axis separation between independently nuisance-profiled low/high slices is {primary['band_weak_axis_separation_deg']['median']:.1f}°; between RX1/RX2 slices {primary['receiver_weak_axis_separation_deg']['median']:.1f}°. These are local information-ellipse axes, not antenna boresights. Median counts of shared candidate families are {primary['families_low_high_shared']['median']:.1f} across bands and {primary['families_rx1_rx2_shared']['median']:.1f} across receivers. Including predictive rows gives angle medians {f['band_weak_axis_separation_deg']['median']:.1f}° / {f['receiver_weak_axis_separation_deg']['median']:.1f}° and shared-family counts {f['families_low_high_shared']['median']:.1f} / {f['families_rx1_rx2_shared']['median']:.1f}. Thus the additional measurements often constrain the same family phase/orbit variables.",'',
        'The LT3D-004B station authority and operations note establish a nominal 40° included feed-axis angle, 20° outward tilt per holder, and 120 mm CAD neck-center separation. They explicitly leave installed RF boresights, base pose, phase centers, polarization roll and directed ENU phase-center baseline unmeasured; physical connector/software RX mapping is provisional. A level base would imply nominal axis elevation 70°. Antenna orientation weights which signals are visible; it is not a measured satellite bearing. The present frequency model uses one site location for both receivers and contains no antenna-bearing, measured gain-pattern, TDOA or interferometric phase observation. Two similarly located feeds therefore do not produce a two-station triangulation baseline merely because their nominal boresights differ.','',
        'Physical metadata sources: /home/mouse9911/gits/leo-tracker-reduxredux/docs/operations/radio20-lt3d-004b-20261001.md and /home/mouse9911/gits/leo-tracker-reduxredux/deploy/station/gauss-r20-lt3d-004b-20261001-v1.json. The metadata authority is prospective and is not, on its own, verification of a capture-bound companion for every DS24 recording. The /srv/bulk/leo/capture-pose/gauss-r20-lt3d-004b-20261001-v1 directory was not readable in this session (permission denied), so companion-level bindings were not independently verified.','',
        '## Numerical and evaluation checks','',
        f"All 48 arm/endpoints passed persisted-objective replay (maximum absolute gap {max(summary[a]['replay_absolute_objective_gap']['maximum'] for a in ['c0','fitted_c']):.8g}; guarded absolute < 1e-3 and relative < 1e-8 tolerance). Position derivatives at 20/40 m agreed to maximum relative {max(summary[a]['derivative_relative_change']['maximum'] for a in ['c0','fitted_c']):.3g}. Stable ridge-projection information agreed with independent augmented QR at <1e-8 relative. Profiled negative-twice-ELBO Hessians, divided by two, were checked at 0.1/0.2 km with the persisted phase-linearization reference held fixed and nuisance coefficients/Gamma variables reoptimized. They are not fully phase-refreshed nonlinear curvature. Maximum relative step change is {max(summary[a]['actual_Hessian_step_relative_change']['maximum'] for a in ['c0','fitted_c']):.3g}; minimum eigenvalue across all arms is {min(summary[a]['actual_half_Hessian_minimum_eigenvalue']['minimum'] for a in ['c0','fitted_c']):.3f} per km².",'',
        'The evaluation error vector uses the exact inverse of the engine map prototype_dsx01_continuous_position.latlon at CENTER: north scale 111.0 km/degree, east scale 111.32 × cos(CENTER latitude) km/degree. This keeps Mahalanobis errors in exactly the same position-coordinate units as the information matrices. Separately reported scalar geographic errors are retained from the existing evaluation table.','',
        f"For fitted c, the descriptive apparent squared Mahalanobis error has median {summary['fitted_c']['evaluation_only']['apparent_squared_Mahalanobis_fixed_Gamma']['median']:.2f}, range {summary['fitted_c']['evaluation_only']['apparent_squared_Mahalanobis_fixed_Gamma']['minimum']:.2f}–{summary['fitted_c']['evaluation_only']['apparent_squared_Mahalanobis_fixed_Gamma']['maximum']:.2f}. {summary['fitted_c']['evaluation_only']['count_below_chi2_2_95_reference']}/24 are below the χ²₂ 95% reference 5.99 and {summary['fitted_c']['evaluation_only']['count_below_chi2_2_99_reference']}/24 below the 99% reference 9.21. These are descriptive comparisons, not coverage tests: the covariance is conditional, identities were selected, Gamma/prior scales are model assumptions, and cases may share systematic or orbital errors. A true site not coinciding with the likelihood maximum alone does not prove model error.",'',
        '## Code and evidence','',
        '- diagnose_information.py: persisted-input replay, finite differences, nuisance projection, same-point band/RX subsets, counterfactual noise precision and actual objective Hessian.',
        '- test_information.py: independent augmented-QR agreement, data/freezing monotonicity and exactly confounded precision-saturation identities.',
        '- Per-case JSON plus all_cases.json: all 24 cases × both c arms; curved-only and curved-plus-predictive fixed-Gamma surrogate results, oracle controls, top correlations and numerical checks.',
        '- summary.json, evaluation_only.json, position_information.png: aggregates, evaluation-only comparisons and scientific figure.',
        '- Repository model pointers: tools/dsx01_joint_marginal.py (common-site Doppler and hardware/phase/orbit columns); tools/ds23_predictive_linear.py (predictive linear covariance and 300 Hz biases); tools/build_dsx01_orbit_modes.py (causal physical orbit scales); tools/ds23_position_information.py (independent QR projection).','',
        'The fixed-Gamma surrogate freezes covariance derivatives and does not fully reproduce the nonlinear robust likelihood. The separately computed objective Hessian includes nuisance-coefficient/Gamma reoptimization and covariance-volume effects while holding the persisted phase-linearization reference fixed; it is not fully phase-refreshed nonlinear curvature. Oracle freezing controls are diagnostics, not proposed changes to scientifically necessary nuisance uncertainty.']
    (HERE/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary['fitted_c'],indent=2))


if __name__ == '__main__':
    main()
