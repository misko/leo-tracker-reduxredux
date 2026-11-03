"""Report robust predictive controls, clock diagnostics and history limits."""

import csv
import hashlib
import shutil
import tarfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_robust_predictive_linear import OUT
from probe_ds23_predictive_linear import OUT as GAUSSIAN
from probe_ds23_height import OUT as HEIGHT
from probe_ds23_sample_clock import OUT as CLOCK
from prototype_dsx01_continuous_position import latlon
from report_algo01_ds23_sample import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha

METHODS=('baseline','gaussian','student_noise','student_noise_and_bias')
LABELS=('Curved-data incumbent','Gaussian linear prediction','Student noise','Student noise and bias')


def save_csv(name,rows):
    with (OUT/name).open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def ids(r):
    return [o for t in r['gates']['tracks'] for o in t['observation_ids']]


def run():
    protocol=read(OUT/'protocol.json');receipts=read(OUT/'execution.json');cases=sorted(protocol['cases'])
    assert len(cases)==20 and {r['case'] for r in receipts}==set(cases) and all(r['code']==0 for r in receipts)
    data={};positions=[];precision=[];failures=[];max_feedback=0.;max_precision_change=0.
    for receipt in receipts:
        case=receipt['case'];path=OUT/(case+'.json');assert sha(path)==receipt['result_sha256'];r=read(path);data[case]=r
        assert r['source_sha256']==sha(ROOT/'tools/probe_ds23_robust_predictive_linear.py')
        assert r['helper_sha256']==sha(ROOT/'tools/ds23_robust_predictive_linear.py') and r['no_GPS_used']
        assert r['gaussian_input_sha256']==sha(GAUSSIAN/(case+'.json'))
        g=read(GAUSSIAN/(case+'.json'));assert r['entries']==g['results']['all_linear']['entries']
        assert r['baseline_arms']==g['baseline_arms'] and r['mask']==g['mask'] and r['powers']==g['powers']
        old_ids=ids(r['baseline_arms']['c0']);new_ids=[o for e in r['entries'] for o in e['observation_ids']]
        assert len(old_ids)==len(set(old_ids)) and len(new_ids)==len(set(new_ids)) and not set(old_ids)&set(new_ids)
        for method in METHODS:
            v=None if method=='baseline' else g['results']['all_linear'] if method=='gaussian' else r['results'][method]
            pair=r['baseline_arms'] if v is None else v['policy_arms']
            for arm in ('c0','fitted_c'):
                trial=pair[arm] if v is None else v['arms'][arm]
                assert set(ids(trial))==set(old_ids)
                positions.append(dict(case=case,method=method,arm=arm,policy_error_km=position_error(pair[arm]['endpoint_latlon']),
                    raw_trial_error_km=position_error(trial['endpoint_latlon']),curved_RMS_hz=trial['RMS_hz'],
                    paired_valid=v is None or v['paired_valid'],new_points=0 if v is None else len(new_ids)))
                if method not in METHODS[2:]:continue
                assert {o for t in trial['linear_gates'] for o in t['observation_ids']}==set(new_ids)
                max_feedback=max(max_feedback,trial['calibration_replay_max_difference'])
                max_precision_change=max(max_precision_change,trial['predictive_final_precision_change'])
                for t in trial['linear_gates']:
                    precision.append(dict(case=case,method=method,arm=arm,component=t['component'],
                        noise_precision=t['predictive_noise_precision'],bias_prior_precision=t['predictive_bias_prior_precision'],
                        bias_posterior_mean_hz=t['predictive_bias_mean_hz'],RMS_hz=t['rms_hz'],compatible=t['compatible']))
                for kind,tracks in [('curved',trial['gates']['tracks']),('linear',trial['linear_gates'])]:
                    for t in tracks:
                        if not t['compatible']:failures.append(dict(case=case,method=method,arm=arm,kind=kind,component=t['component']))
            if method in METHODS[2:]:
                valid=all(all(t['compatible'] for t in a['gates']['tracks']+a['linear_gates']) and a['final_phase_change_s']<=.01
                    and a['predictive_final_precision_change']<=1e-4 for a in v['arms'].values())
                assert valid==v['paired_valid']
    assert max_feedback==0
    save_csv('positions.csv',positions);save_csv('predictive_precisions.csv',precision)
    if failures:save_csv('failed_components.csv',failures)
    summary={};table=['| Policy | c0 mean / median km | Fitted-c mean / median km | Paired valid /20 |','|---|---:|---:|---:|']
    for method,label in zip(METHODS,LABELS,strict=True):
        summary[method]={}
        for arm in ('c0','fitted_c'):
            values=[r['policy_error_km'] for r in positions if r['method']==method and r['arm']==arm]
            summary[method][arm]=dict(mean_km=float(np.mean(values)),median_km=float(np.median(values)))
        valid=20 if method=='baseline' else sum(next(r['paired_valid'] for r in positions if r['case']==case and r['method']==method) for case in cases)
        a,b=summary[method]['c0'],summary[method]['fitted_c']
        table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} | {valid} |")
    fig,axes=plt.subplots(2,1,figsize=(13,7),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for method,label in zip(METHODS,LABELS,strict=True):
            ax.plot(range(20),[next(r['policy_error_km'] for r in positions if r['case']==c and r['method']==method and r['arm']==arm) for c in cases],'.-',lw=1,label=label)
        ax.axhline(.5,c='crimson',ls='--',lw=1);ax.set(title=arm,ylabel='Position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=2)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('Robust predictive controls · fixed curved calibration data and added linear observations')
    fig.savefig(OUT/'position_errors.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
    precision_summary={}
    for method in METHODS[2:]:
        rows=[r for r in precision if r['method']==method and r['arm']=='c0']
        noise=[r['noise_precision'] for r in rows];bias=[r['bias_prior_precision'] for r in rows]
        axes[0].hist(noise,bins=np.geomspace(.01,10,36),histtype='step',lw=1.7,label=method)
        axes[1].scatter([abs(r['bias_posterior_mean_hz']) for r in rows],bias,s=10,alpha=.5,label=method)
        precision_summary[method]=dict(median_predictive_noise_precision=float(np.median(noise)),median_bias_prior_precision=float(np.median(bias)),
            raw_curves=len(rows),paired_failures=[c for c in cases if not data[c]['results'][method]['paired_valid']])
    axes[0].axvline(.5,c='black',ls=':',label='Gaussian control: precision 0.5');axes[0].set(xscale='log',xlabel='New-curve noise precision',ylabel='Curves (all raw trials)')
    axes[1].set(xscale='symlog',yscale='log',xlabel='Absolute predictive bias mean (Hz)',ylabel='Bias prior precision')
    for ax in axes:ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.suptitle('Robust tails also change central precision · c0 · failures retained')
    fig.savefig(OUT/'predictive_precision.png',dpi=160);plt.close(fig)

    clock_rows=[];clock_null=[];clock_replay=0.;clock_cases=['DS23-0257','DS23-0202']
    for case in clock_cases:
        r=read(CLOCK/(case+'.json'));assert r['no_GPS_used'] and r['no_extra_point_trimming']
        assert r['source_sha256']==sha(ROOT/'tools/probe_ds23_sample_clock.py') and r['helper_sha256']==sha(ROOT/'tools/ds23_sample_clock.py')
        for sigma,v in r['results'].items():
            assert v['paired_valid'];pair=v['arms']
            for arm,a in pair.items():
                assert set(ids(a))==set(ids(r['baseline_arms'][arm]))
                clock_rows.append(dict(case=case,sigma_ppm=int(sigma),arm=arm,error_km=position_error(a['endpoint_latlon']),
                    receiver1_ppm=a['clock_ppm'][0],receiver2_ppm=a['clock_ppm'][1],
                    RF_objective_change=a['negative_twice_elbo']-r['results']['0']['arms'][arm]['negative_twice_elbo']))
                clock_replay=max(clock_replay,a['exact_geometry_replay']['maximum_prediction_difference_hz'])
                if sigma=='0':clock_null.append(dict(case=case,arm=arm,
                    endpoint_difference_km=float(np.linalg.norm(np.array(a['endpoint_east_north_km'])-r['baseline_arms'][arm]['endpoint_east_north_km'])),
                    RF_objective_difference=a['negative_twice_elbo']-r['baseline_arms'][arm]['negative_twice_elbo']))
    save_csv('sample_clock.csv',clock_rows);save_csv('sample_clock_null.csv',clock_null)
    write(CLOCK/'protocol_receipt.json',dict(cases=clock_cases,clock_sigmas_ppm=[0,25,100],
        matched_c_original_observations_labels_aliases_priors=True,engineering_not_measured_hardware_sigmas=True,
        diagnostic_receipt_assembled_after_completed_pilots=True,observed_both_processes_terminal_exit_code=0,
        not_a_preregistered_full_cohort=True))
    fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
    for row,case in zip(axes,clock_cases,strict=True):
        for arm in ('c0','fitted_c'):
            selected=sorted([r for r in clock_rows if r['case']==case and r['arm']==arm],key=lambda r:r['sigma_ppm'])
            row[0].plot([r['sigma_ppm'] for r in selected],[r['error_km'] for r in selected],'.-',label=arm)
            row[1].plot([r['sigma_ppm'] for r in selected],[r['RF_objective_change'] for r in selected],'.-',label=arm)
        row[0].set(title=case,ylabel='Position error (km)');row[1].set(title='Normalized frequency objective',ylabel='Change from zero-clock control')
        for ax in row:ax.set_xlabel('Engineering clock prior SD (ppm)');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Coupled sample-clock frequency and time scaling · two diagnostic scans only')
    fig.savefig(OUT/'sample_clock.png',dpi=160);plt.close(fig)

    history=read(OUT/'stationary_history_diagnostic.json')
    assert history['no_GPS_used'] and history['source_sha256']==sha(ROOT/'tools/probe_ds23_stationary_history_diagnostic.py')
    for path,h in history['input_sha256'].items():assert sha(Path(path))==h
    history_rows=[];history_summary={};ht=['| Input policy | c0 prefix mean / median km | Fitted-c prefix mean / median km |','|---|---:|---:|']
    for method,label in zip(METHODS,LABELS,strict=True):
        history_summary[method]={}
        for arm,record in history['results'][method].items():
            errors=[]
            for r in record['estimates']:
                assert r['latest_input_utc_ns']==r['captured_utc_ns']
                error=position_error(latlon(r['position_east_north_km']));errors.append(error)
                history_rows.append(dict(method=method,arm=arm,case=r['case'],scans_used=r['scans_used'],captured_utc_ns=r['captured_utc_ns'],error_km=error))
            history_summary[method][arm]=dict(mean_km=float(np.mean(errors)),median_km=float(np.median(errors)))
        a,b=history_summary[method]['c0'],history_summary[method]['fitted_c']
        ht.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} |")
    save_csv('stationary_history_errors.csv',history_rows)
    replay=read(OUT/'history_gate_replay.json')
    assert replay['source_sha256']==sha(ROOT/'tools/probe_ds23_history_gate_replay.py')
    assert replay['history_input_sha256']==sha(OUT/'stationary_history_diagnostic.json') and replay['no_GPS_used']
    gate_rows=[];boundary=[]
    for r in replay['records']:
        assert r['gaussian_input_sha256']==sha(GAUSSIAN/(r['case']+'.json'))
        assert r['controls']['individual_null']['paired_valid']
        for name,v in r['controls'].items():
            for arm,raw in v['arms'].items():
                actual=v['policy_arms'][arm]
                before=r['incumbent_arms'][arm]
                assert set(ids(raw))==set(ids(before))
                gate_rows.append(dict(case=r['case'],control=name,arm=arm,paired_valid=v['paired_valid'],
                    raw_error_km=position_error(raw['endpoint_latlon']),policy_error_km=position_error(actual['endpoint_latlon']),
                    curved_RMS_hz=raw['RMS_hz'],incumbent_RMS_hz=before['RMS_hz']))
                if name!='stationary_prefix':continue
                for kind,tracks in [('curved',raw['gates']['tracks']),('linear',raw['linear_gates'])]:
                    for t in tracks:
                        d=t['conditional_residual_gate']['diagnostics'] if kind=='curved' else t['noise_screen']
                        ratios=dict(mean=d['mean_z']/3,slope=d['slope_z']/3,quadratic=d['quadratic_bic_gain']/10,
                            step=d['maximum_step_z']/4,lag1=abs(d['lag1_acf'])*np.sqrt(t['points'])/4)
                        worst=max(ratios,key=ratios.get)
                        if not d['noise_screen_pass']:
                            boundary.append(dict(case=r['case'],arm=arm,kind=kind,component=t['component'],
                                points=t['points'],worst_gate=worst,ratio_to_original_cutoff=ratios[worst],
                                mean_z=d['mean_z'],slope_z=d['slope_z'],quadratic_BIC_gain=d['quadratic_bic_gain'],
                                step_z=d['maximum_step_z'],lag1_acf=d['lag1_acf']))
    save_csv('history_gate_errors.csv',gate_rows);save_csv('history_failing_statistics.csv',boundary)
    checked_summary={arm:dict(mean_km=float(np.mean([r['policy_error_km'] for r in gate_rows if r['arm']==arm and r['control']=='stationary_prefix'])),
        median_km=float(np.median([r['policy_error_km'] for r in gate_rows if r['arm']==arm and r['control']=='stationary_prefix']))) for arm in ('c0','fitted_c')}
    checked_valid=sum(r['controls']['stationary_prefix']['paired_valid'] for r in replay['records'])
    earliest=min(history['results']['gaussian']['c0']['estimates'],key=lambda r:r['captured_utc_ns'])['case']
    first=next(r for r in replay['records'] if r['case']==earliest)
    for arm in ('c0','fitted_c'):
        np.testing.assert_array_equal(first['controls']['individual_null']['arms'][arm]['endpoint_east_north_km'],
            first['controls']['stationary_prefix']['arms'][arm]['endpoint_east_north_km'])
    fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for arm in ('c0','fitted_c'):
        actual=[next(r['policy_error_km'] for r in gate_rows if r['case']==case and r['control']=='stationary_prefix' and r['arm']==arm) for case in cases]
        raw=[next(r['raw_error_km'] for r in gate_rows if r['case']==case and r['control']=='stationary_prefix' and r['arm']==arm) for case in cases]
        axes[0].plot(range(20),raw,':',lw=1,label=arm+' raw prefix')
        axes[0].plot(range(20),actual,'.-',lw=1,label=arm+' after paired gates')
    axes[0].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=60)
    axes[0].set(ylabel='Position error (km)',title='Current-scan evidence cannot be skipped');axes[0].legend(fontsize=7);axes[0].grid(alpha=.2)
    for k,r in enumerate(boundary):
        axes[1].scatter(k,r['ratio_to_original_cutoff'],c='tab:blue' if r['arm']=='c0' else 'tab:orange',s=25)
    axes[1].scatter([],[],c='tab:blue',label='c0');axes[1].scatter([],[],c='tab:orange',label='fitted-c')
    axes[1].legend(fontsize=8)
    axes[1].axhline(1,c='black',ls='--',lw=1)
    axes[1].set_xticks(range(len(boundary)),[r['case'].split('-')[1]+' '+r['worst_gate'] for r in boundary],rotation=70,fontsize=7)
    axes[1].set(ylabel='Failing statistic / original cutoff',title='Borderline noise tests; no thresholds changed');axes[1].grid(alpha=.2)
    fig.savefig(OUT/'history_gate_replay.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        record=history['results']['gaussian'][arm];order=[r['case'] for r in record['estimates']]
        for method,label in [('gaussian','Prefix median: Gaussian prediction'),('baseline','Prefix median: curved incumbent')]:
            ax.plot(range(20),[next(r['error_km'] for r in history_rows if r['case']==case and r['method']==method and r['arm']==arm) for case in order],'.-',label=label)
        ax.plot(range(20),[next(r['policy_error_km'] for r in positions if r['case']==case and r['method']=='gaussian' and r['arm']==arm) for case in order],'.:',c='.6',label='Individual Gaussian result')
        ax.axhline(.5,c='crimson',ls='--',lw=1);ax.set(title=arm,ylabel='Position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in order],rotation=45)
    fig.suptitle('Stationary-site diagnostic: chronological prefixes only · no motion model or physical gate replay')
    fig.savefig(OUT/'stationary_history.png',dpi=160);plt.close(fig)
    write(OUT/'summary.json',dict(position=summary,predictive_precision=precision_summary,
        clock_cases=clock_cases,clock_maximum_exact_replay_difference_hz=clock_replay,
        stationary_history_diagnostic=history_summary,gate_checked_stationary_diagnostic=checked_summary,
        history_paired_gate_passes=checked_valid,goal_half_km_met=False,no_default_promotion=True))
    write(OUT/'validation.json',dict(all20_robust_processes_terminal_success=True,all80_robust_trial_ID_sets_verified=True,
        calibration_mean_and_precisions_feedback_max_difference=max_feedback,maximum_predictive_precision_change=max_precision_change,
        all_source_and_baseline_hashes_match=True,all12_clock_arms_pass_original_gates=True,
        owned_tests_robust=5,owned_tests_clock=4,owned_tests_stationary_history=3,
        all20_individual_fixed_position_nulls_pass=True,earliest_prefix_equals_individual_null=True,
        current_scan_replay_preserves_IDs_and_paired_evidence=True,
        GPS_only_in_reporter=True,history_is_not_a_validated_position_algorithm=True,reporter_sha256=sha(Path(__file__))))
    shutil.copyfile(HEIGHT/'causal_receipt_audit.json',OUT/'causal_receipt_audit.json')
    body='''# DS23: robust linear prediction, sample clocks and stationary-history diagnostics

The robust models do not improve both mean and median. Retain the earlier
Gaussian linear-prediction prototype as the comparison reference; no ALGO01
default is changed. All results here are twenty development scans or explicitly
smaller diagnostics, not validation across all 413 DS23 recordings.

TABLE

![Position errors on all scans](position_errors.png)

Every scan remains in every denominator. If either c arm fails an original
curved gate, a new linear gate, phase refresh or predictive-precision convergence,
the pair falls back to the curved incumbent. There is no hidden point deletion.
The Gaussian comparator has four such failures; both robust policies have five.
Raw positions, failed components and precision estimates are archived.

## Robust conditional prediction

Freeze exactly the previous Gaussian experiment's added track IDs, labels and
integer aliases. Keep original curved points, masks, receiver-support powers,
noise, phase-history means/scales and physical orbit modes unchanged. Each fit
starts at the same 25x25 km regional center (37.906,-122.545), with five phase
refreshes and up to 48 position steps each. No supplied GPS, following TLE,
IQ reread or new RF enters inference. Every source catalogue remains causal.

At each horizontal position, curved data alone produce mean m and conditional
Gaussian calibration precision A. Added linear observations are predicted with
the original physical features U_L. Integrate shared uncertainty through
U_L A^-1 U_L'; do not give every point an independent calibration error.
The two controls change only the new-track predictive distribution:

* Student noise: a separate Gamma(2,2) noise precision per added curve; its
  marginal variance is 2*sigma_radio², matching the previous Gaussian model.
* Student noise and bias: the same noise model plus a four-degree Student bias
  per new curve with variance 300² Hz², matching the Gaussian bias variance.

Use the existing normalized Gaussian/Gamma variational integration, including
determinants, prior penalties, noise normalizations and Gamma terms. The new
predictive latent means are not applied as calibration corrections. Every
saved fit reproduces the curved-only calibration mean, noise precisions and
prior precisions exactly at that position. The covariance still conditions on
curved Gamma means, so this is an approximate modular predictive objective,
not an exact full hierarchical posterior or calibrated identity probability.

![Predictive precision and bias](predictive_precision.png)

Heavy tails do not merely remove outliers. After seeing a new curve, posterior
noise precision can exceed the Gaussian control's fixed 0.5, and the variance-
matched Student bias has a more concentrated center. Some valid-looking linear
evidence can therefore exert more influence. Here median c0 noise precision is
about 1.252 in both robust models, and median bias prior precision is 2.236 in
the Student-bias model, versus 1 for Gaussian bias. The small mean improvement and
worse median do not justify a new default. Scan 217 reaches 0.475 km fitted-c
with Student noise/bias, versus 0.529 km for Gaussian prediction, but that one
pilot cannot select the cohort algorithm. Scan 321 still fails a new linear
gate. No failed point is discarded merely because it prevents a better error.

## A distinct physical check: coupled sample-clock scale and elapsed time

The common RF-times-time drift control tested earlier is not the same effect.
Let epsilon = actual_sample_rate/nominal_sample_rate - 1. For a carrier measured
in nominal sample-rate units and a counter-derived elapsed time, test:

    observed_frequency = physical_frequency(t_observed/(1+epsilon))/(1+epsilon)
    first-order column = -physical_frequency - t_observed*frequency_rate

Use one epsilon per receiver. Existing offset/drift coefficients stay in
observed-time coordinates. Finite differences include the current orbital
correction; update orbit and phase references from curved data only. Append
two Gaussian nuisance columns before the fragment constants and retain the
full integrated complexity penalty. Priors SD 0,25,100 ppm are engineering
hypotheses, not measured oscillator tolerances or hardware specifications.

Both diagnostic scans (257 and 202) retain the same observations/aliases and
pass every c-arm gate. Zero-clock replays reproduce the incumbent. At 100 ppm
prior SD, fitted-c error changes 3.699→3.688 km on 257 and 3.060→2.974 km on
202. The latter fits approximately +129/-127 ppm on RX1/RX2; this is not
independent evidence of actual clock errors. RF preference can represent
compensation for another model discrepancy. Exact time/frequency replay checks
the linearization, not the truth of its clock interpretation.

![Clock control accuracy and RF evidence](sample_clock.png)

The small changes do not resolve these failures. This is a two-scan diagnostic,
not a full-cohort clock benchmark. Its protocol receipt is assembled after the
completed pilots; it does not pretend to be a prospective cohort registration.

## Conditional stationary-history diagnostic: a different information source

The twenty inputs span about four days. Independently localized errors point
in different directions, suggesting a test of averaging rather than another
single-scan nuisance term. For each chronological prefix, calculate the spatial
median of RF-derived positions observed so far, including the current scan.
No later scan affects an earlier prefix, and no GPS enters this calculation.
All original individual fits still start cold in their original regional box.

HISTORY_TABLE

![Chronological prefix diagnostic](stationary_history.png)

This table is the raw diagnostic, explicitly conditional on the receiver remaining
at one site throughout the prefix. It borrows earlier scan results and has no
movement/reset model. The raw coordinates do not by themselves qualify against
the current scan's physical gates. They are not an ALGO01 result, a general
solution for independent new locations, or attainment of the full DS23 goal.
The existing same-site evaluation
assumption and antenna-height question remain unconfirmed. A receiver move
would invalidate pooling across that boundary. The prefix estimates are not
assigned calibrated uncertainty bars or treated as independent TLE observations.

A separate replay now holds each prefix coordinate fixed and refits the current
curved calibration for five phase rounds. Use exactly the current Gaussian
policy's evidence, including linear tracks only when its original paired trial
qualified. Check all original curved and new linear gates in both arms. All
twenty individual-coordinate null replays pass; only 14/20 prefix pairs pass.
With paired fallback, errors are **0.894/0.651 km c0** and **0.794/0.513 km
fitted-c**. Do not report the raw 0.507/0.431 km fitted-c prefix values as a
gate-qualified algorithm result. The replay changes calibration only at the
given coordinate; it is not a joint history-aware RF optimization.

![Physical gate replay and failed statistical margins](history_gate_replay.png)

Failures occur on 74,108,138,143,273 and373. Some are just beyond the statistical
threshold: slope z reaches 3.099 against3; a step z is4.081 against4; one BIC
gain is10.0036 against10. Aliases and the 450Hz RMS bound do not explain those
conditional failures. The exact failed-track statistics are published; a final
family-support failure can also cascade from a companion's failed noise gate.
These margins do not authorize changing thresholds at favorable coordinates.
They motivate a noise-only false-rejection audit of the multiple checks across
all tracks, ideally including parameter fitting and group correlations. Any
replacement should set its error rate without GPS and then rerun all cases,
including regressions and independent validation. No gate is relaxed here.
It must also retain power against injected ramps, curvature and steps; a lower
false-rejection rate alone can hide real model errors. Satellite-identity
competition remains separate from accepting a noise goodness-of-fit test.

The spatial median uses a convex vertex optimality check, then a regularized
Weiszfeld iteration if needed. A midpoint convention preserves non-unique
two-point/collinear median intervals. A future-input perturbation test exposed
slow convergence in the first version; that diagnostic/source is retained under
stationary_history_v1, and the fixed implementation passes the causal test.
This is a numerical correction, not a geographical correction of the estimates.

The useful next steps are statistical gate qualification and a causal history
model with movement/reset handling, current-scan physical gates and explicit
scan dependencies.
It must be compared separately from single-scan performance. Broader satellite
competition using the new linear evidence is another remaining association
test; the earlier replacement search used the curved calibration set alone.
Neither direction authorizes GPS-selecting identities or dropping hard scans.

## Validation and reproduction

Five robust-prediction tests cover exact grouped Student noise density with no
design, selective group downweighting, Student-bias tails, no calibration feedback
and input validation. Four clock tests cover null geometry, coupled derivative
sign/scale and receiver isolation, zero-column prior normalization and an
injected physical clock error. Three history tests cover rigid-coordinate
equivariance, future-prefix invariance and single/duplicate-time conventions.
All twelve pass; they do not prove physical calibration or new-location accuracy.

Run tools/run_ds23_robust_predictive_linear.py with the repository venv,
PYTHONPATH=src:tools and BLAS/OMP threads one. Two subprocesses have 300 s bounds.
Run tools/probe_ds23_sample_clock.py --case for 257 and 202, then
tools/probe_ds23_stationary_history_diagnostic.py and this reporting tool.
Run tools/probe_ds23_history_gate_replay.py after the stationary diagnostic and
before reporting; this sequential numerical replay also preserves the full gates.
Clock tests also require tests/analysis on PYTHONPATH for the prior synthetic
geometry fixture. Sources overlay the earlier height and predictive reports.
Reporting alone uses (37.849061591561885,-122.48574968092912) for error.

[Position trials](positions.csv) · [Predictive precisions](predictive_precisions.csv) ·
[Failed components](failed_components.csv) · [Clock trials](sample_clock.csv) ·
[Clock null replays](sample_clock_null.csv) · [Stationary prefix errors](stationary_history_errors.csv) ·
[Gate-checked prefix errors](history_gate_errors.csv) · [Failed gate statistics](history_failing_statistics.csv) ·
[Summary](summary.json) · [Validation](validation.json) · [Protocol](protocol.json) ·
[Execution](execution.json) · [Causal receipts](causal_receipt_audit.json) ·
[Full lossless evidence](evidence.tar.xz) · [Evidence hashes](evidence_inventory.json).
'''
    (OUT/'README.md').write_text(body.replace('HISTORY_TABLE','\n'.join(ht)).replace('TABLE','\n'.join(table)))
    tools=['ds23_robust_predictive_linear.py','probe_ds23_robust_predictive_linear.py','run_ds23_robust_predictive_linear.py',
        'ds23_sample_clock.py','probe_ds23_sample_clock.py','probe_ds23_stationary_history_diagnostic.py',
        'probe_ds23_history_gate_replay.py','report_ds23_robust_predictive_linear.py']
    names=['tools/'+t for t in tools]+['tests/analysis/'+t for t in ['test_ds23_robust_predictive_linear_tool.py','test_ds23_sample_clock_tool.py','test_ds23_stationary_history_tool.py']]
    sources={}
    for name in names:
        target=OUT/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        sources[str(target.relative_to(OUT))]=sha(target)
    write(OUT/'source_inventory.json',sources)
    paths=[OUT/'protocol.json',OUT/'execution.json',OUT/'stationary_history_diagnostic.json',OUT/'history_gate_replay.json',OUT/'history_gate_replay_partial.json']
    paths += [p for p in OUT.iterdir() if p.name.startswith('DS23-') and p.suffix in ('.json','.log')]
    paths += [p for p in (OUT/'stationary_history_v1').iterdir() if p.is_file()]
    paths += [p for p in CLOCK.iterdir() if p.suffix in ('.json','.log')]
    inventory={}
    with tarfile.open(OUT/'evidence.tar.xz','w:xz',preset=3) as t:
        for p in sorted(paths):
            relative=str(p.relative_to(ROOT));inventory[relative]=dict(sha256=sha(p),bytes=p.stat().st_size);t.add(p,arcname=relative)
    with tarfile.open(OUT/'evidence.tar.xz','r:xz') as t:
        assert len(t.getmembers())==len(inventory)
        for m in t.getmembers():assert hashlib.sha256(t.extractfile(m).read()).hexdigest()==inventory[m.name]['sha256']
    write(OUT/'evidence_inventory.json',inventory)
    print('\n'.join(table));print('Stationary diagnostic only:');print('\n'.join(ht),flush=True)


if __name__=='__main__':run()
