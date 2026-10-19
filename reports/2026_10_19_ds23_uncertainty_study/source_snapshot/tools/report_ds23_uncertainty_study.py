"""Report complete band/phase cohorts and local information/UTC/evidence audits."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

from probe_ds23_history_calibrated_phase import OUT as BASE,ROOT,HISTORY
from probe_ds23_band_covariance import OUT as BAND
from probe_ds23_satellite_phase_scale import OUT as SCALE
from diagnose_ds23_position_information import OUT as INFO
from probe_ds23_utc_bracket import OUT as UTC
from probe_ds23_marginal_evidence import OUT as EVIDENCE
from report_algo01_ds23_sample import position_error,REFERENCE,summarize
from prototype_dsx01_continuous_position import CENTER
from run_algo01_ds23_sample import OUT as SOURCE,read,write,sha

OUT=ROOT/'reports/2026_10_19_ds23_uncertainty_study'
METHODS=('baseline','band_half','band_independent','satellite_scale')
LABELS=('Scalar history + RX support','Half shared band variance','Independent band smooth','Satellite-specific phase scale')


def save_csv(path,rows):
    with path.open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=sorted(read(BAND/'protocol.json')['cases']);assert len(cases)==20
    for directory in (BAND,SCALE,INFO):
        protocol=read(directory/'protocol.json');execution=read(directory/'execution.json')
        assert sorted(protocol['cases'])==cases and len(execution)==20 and all(r['code']==0 for r in execution)
        hashes=protocol['source_sha256']
        if isinstance(hashes,dict):assert all(sha(ROOT/'tools'/n)==h for n,h in hashes.items())
        else:assert sha(ROOT/'tools/diagnose_ds23_position_information.py')==hashes
    rows=[];information=[];replay=[];finite_diff=[]
    for case in cases:
        base=read(BASE/(case+'.json'))['results']['mean_and_distribution']
        band=read(BAND/(case+'.json'));scale=read(SCALE/(case+'.json'));info=read(INFO/(case+'.json'))
        assert band['source_sha256']==sha(ROOT/'tools/probe_ds23_band_covariance.py')
        assert scale['source_sha256']==sha(ROOT/'tools/probe_ds23_satellite_phase_scale.py')
        assert info['source_sha256']==sha(ROOT/'tools/diagnose_ds23_position_information.py')
        receipt=read(SOURCE/case/'receipt.json');history=read(HISTORY/(case+'.json'))
        forecast=read(HISTORY/(case+'_forecast.json'));specific=read(HISTORY/(case+'_satellite_scale.json'))
        assert history['cutoff_utc_ns']==receipt['cutoff_utc_ns']
        assert forecast['history_sha256']==sha(HISTORY/(case+'.json'))
        assert specific['forecast_sha256']==sha(HISTORY/(case+'_forecast.json'))
        assert scale['scale_input_sha256']==sha(HISTORY/(case+'_satellite_scale.json'))
        assert all(v['epoch']<=receipt['cutoff_utc_ns'] and v['collected_utc_ns']<=receipt['cutoff_utc_ns'] for versions in history['past_versions'].values() for v in versions)
        assert all(r['validation_time_ns']<=receipt['cutoff_utc_ns'] for r in forecast['transitions'])
        for method in METHODS:
            record=base if method=='baseline' else band['results']['0.5'] if method=='band_half' else band['results']['0.0'] if method=='band_independent' else scale
            assert record['valid']
            identities=[{oid for t in record['arms'][arm]['gates']['tracks'] for oid in t['observation_ids']} for arm in ('c0','fitted_c')]
            assert identities[0]==identities[1]
            for arm in ('c0','fitted_c'):
                r=record['arms'][arm]
                rows.append(dict(case=case,method=method,arm=arm,error_km=position_error(r['endpoint_latlon']),
                    RMS_hz=r['RMS_hz'],calibration_points=r['active_points'],valid=record['valid']))
        for arm,r in info['results'].items():
            replay.append(r['score_replay_difference']);finite_diff.append(r['finite_difference_max_relative_change'])
            for control,result in r['controls'].items():
                assert result['positive_definite']
                information.append(dict(case=case,arm=arm,control=control,local_RMS_radius_km=result['RMS_radius_km'],
                    maximum_sigma_km=result['principal_sigma_km'][0],minimum_sigma_km=result['principal_sigma_km'][1]))
    summary={m:{a:summarize([r['error_km'] for r in rows if r['method']==m and r['arm']==a]) for a in ('c0','fitted_c')} for m in METHODS}
    save_csv(OUT/'position_comparison.csv',rows);save_csv(OUT/'local_information.csv',information)
    write(OUT/'summary.json',dict(position_results=summary,target_met=False,all20_reported=True,
        inference_uses_no_GPS=True,local_information_is_not_calibrated_accuracy=True))
    fig,axes=plt.subplots(2,1,figsize=(14,7),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for m,label in zip(METHODS,LABELS,strict=True):
            ax.plot(range(20),[next(r['error_km'] for r in rows if r['case']==c and r['method']==m and r['arm']==arm) for c in cases],'.-',label=label)
        ax.axhline(.5,c='crimson',ls='--');ax.grid(alpha=.2);ax.set(title=arm,ylabel='Actual position error (km)');ax.legend(ncol=2,fontsize=8)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('All 20 development scans · matched c arms · no GPS model selection')
    fig.savefig(OUT/'position_error_by_scan.png',dpi=160);plt.close(fig)
    controls=list(read(INFO/(cases[0]+'.json'))['results']['c0']['controls'])
    fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        data=[[r['local_RMS_radius_km'] for r in information if r['arm']==arm and r['control']==c] for c in controls]
        ax.boxplot(data,tick_labels=[c.replace('_','\n') for c in controls],showfliers=True)
        ax.set(title=arm,ylabel='Local linearized RMS radius (km)');ax.grid(axis='y',alpha=.2)
    fig.suptitle('Oracle information controls, not new localization results\nFitted Gamma precisions fixed; recorded UTC uncertainty omitted from these widths')
    fig.savefig(OUT/'nuisance_information.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,6),constrained_layout=True)
    true_xy=np.array([(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),(REFERENCE[0]-CENTER[0])*111])
    for case,color in zip(('DS23-0257','DS23-0202','DS23-0273','DS23-0217'),('tab:blue','tab:orange','tab:green','tab:purple'),strict=True):
        r=read(INFO/(case+'.json'))['results']['c0'];xy=np.array(r['endpoint_east_north_km'])
        cov=np.array(r['controls']['all_uncertain']['covariance_km2']);eigen,vectors=np.linalg.eigh(cov)
        angle=np.rad2deg(np.arctan2(vectors[1,1],vectors[0,1]))
        ax.add_patch(Ellipse(xy,2*np.sqrt(eigen[1]),2*np.sqrt(eigen[0]),angle=angle,fill=False,color=color,lw=1.5))
        ax.scatter(*xy,c=color,label=case);ax.annotate(case.split('-')[1],xy,xytext=(4,5),textcoords='offset points',color=color)
    ax.scatter(*true_xy,marker='*',s=180,c='crimson',label='Reference: evaluation only')
    ax.set(xlabel='East from regional center (km)',ylabel='North (km)',title='c0 endpoints with one local standard-deviation ellipses\nConditional generalized widths, not calibrated coverage',aspect='equal')
    ax.autoscale();ax.grid(alpha=.2);ax.legend(fontsize=8);fig.savefig(OUT/'endpoint_uncertainty.png',dpi=160);plt.close(fig)
    clock=[];fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
    for col,case in enumerate(('DS23-0257','DS23-0202')):
        d=read(UTC/(case+'.json'));assert not d['partial'] and len(d['records'])==5
        assert d['source_sha256']==sha(ROOT/'tools/probe_ds23_utc_bracket.py')
        zero=next(r for r in d['records'] if r['fraction']==0)
        for arm in ('c0','fitted_c'):
            t=[r['delta_s']*1000 for r in d['records']]
            errors=[position_error(r['arms'][arm]['endpoint_latlon']) for r in d['records']]
            losses=[r['arms'][arm]['negative_twice_elbo']-zero['arms'][arm]['negative_twice_elbo'] for r in d['records']]
            axes[0,col].plot(t,errors,'.-',label=arm);axes[1,col].plot(t,losses,'.-',label=arm)
            clock.extend(dict(case=case,arm=arm,delta_s=r['delta_s'],error_km=e,delta_RF_loss=l,valid=r['paired_gates_pass']) for r,e,l in zip(d['records'],errors,losses,strict=True))
        axes[0,col].set(title=case,ylabel='Position error (km)');axes[1,col].set(xlabel='Shared UTC shift (ms)',ylabel='RF loss relative to midpoint')
        for ax in axes[:,col]:ax.axvline(0,c='black',ls=':',lw=.7);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Clock sensitivity inside the recorded host bracket · fixed associations and observations')
    fig.savefig(OUT/'UTC_bracket_sensitivity.png',dpi=170);plt.close(fig);save_csv(OUT/'UTC_comparison.csv',clock)
    evidence=read(EVIDENCE/'DS23-0257.json')['results']
    assert read(EVIDENCE/'DS23-0257.json')['source_sha256']==sha(ROOT/'tools/probe_ds23_marginal_evidence.py')
    importance=[]
    for name,r in evidence.items():
        importance.append(dict(candidate=name,negative_twice_ELBO=r['variational_negative_twice_ELBO'],
            estimated_negative_twice_log_evidence=r['negative_twice_log_evidence'],MC_SE=r['Monte_Carlo_SE'],
            ESS=r['effective_samples'],draws=r['samples'],gap=r['estimated_variational_gap'],ESS_rule_pass=r['reliable_by_declared_ESS_rule']))
    save_csv(OUT/'importance_audit.csv',importance)
    evidence_table=['| Candidate at its saved RF endpoint | Variational loss | Importance estimate | MC SE | ESS / draws |',
        '|---|---:|---:|---:|---:|']
    for r in importance:evidence_table.append(f"| {r['candidate']} | {r['negative_twice_ELBO']:.3f} | {r['estimated_negative_twice_log_evidence']:.3f} | {r['MC_SE']:.3f} | {r['ESS']:.0f} / {r['draws']} |")
    table=['| Actual position algorithm | c0 mean / median, km | Fitted-c mean / median, km |','|---|---:|---:|']
    for m,label in zip(METHODS,LABELS,strict=True):
        a,b=summary[m]['c0'],summary[m]['fitted_c'];table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} |")
    info_table=['| Oracle nuisance control | Median local RMS radius c0 / fitted-c, km |','|---|---:|']
    for control in controls:
        med=[np.median([r['local_RMS_radius_km'] for r in information if r['arm']==a and r['control']==control]) for a in ('c0','fitted_c')]
        info_table.append(f'| {control} | {med[0]:.3f} / {med[1]:.3f} |')
    write(OUT/'validation.json',dict(all20_complete=True,all_final_gates_pass=all(r['valid'] for r in rows),
        all_protocol_and_case_source_hashes_match=True,all_raw_history_rows_pre_RF=True,paired_observation_ID_sets_match=True,
        max_information_replay_loss_difference=max(abs(np.array(replay))),
        max_derivative_step_relative_difference=max(finite_diff),new_tool_tests_passed=19,
        information_and_evidence_audits_do_not_claim_new_position_accuracy=True,report_source_sha256=sha(Path(__file__))))
    body='''# DS23: receiver covariance, satellite uncertainty, UTC and evidence integration

**The 0.5 km mean/median target remains unmet.** This report retains every outcome
on the original20 development scans; it is not validation on all413 DS23 scans
or at a new location. ALGO01 and DBG01 remain the published baseline/debug
specifications. No GPS-derived prior or candidate choice is introduced here.

POSITION_TABLE

![Actual position errors](position_error_by_scan.png)

## 1. Receiver and band covariance

The [residual audit](../2026_10_18_ds23_learned_residuals/README.md) shows more
correlation within one receiver than across receivers. Test a common receiver
smooth process plus independent low/high band processes. For correlation rho,
basis blocks are sqrt(rho)*B, sqrt(1−rho)*B_low, sqrt(1−rho)*B_high. Per-band
marginal variance and all within-band covariance remain unchanged. Cross-band
covariance alone becomes rho times the original. Test rho1,0.5,0; retain the
same linear-drift priors. Expanded seed states exactly preserve the initial
predicted correction. Low-only scans are numerical null controls.

All20 paired final gates pass. Half-sharing slightly improves the median but
worsens the mean; independent bands worsen the mean further. This covariance
split does not solve the localization error. Conditional frequency RMS and
retained calibration counts are reported separately in position_comparison.csv;
better frequency fit is not taken as geographic improvement. Every fit begins
with identical original retained observations, fixed labels/aliases, and uses
five phase-reference rounds,48 position steps and four paired gate/refit rounds.
Gate exclusions apply to both c arms; final masks may differ between policies.

## 2. Satellite-specific uncertainty from causal history

Keep the scalar historical phase forecast and Student tail model. Add a
population-centered log-scale mixture for each satellite. Normalize its prior
so E[tau²]=1. Earlier updates estimate a posterior scale, and use
sqrt(E[tau² | past updates]) as the moment-matched Student scale multiplier.
Unseen identities and zero scale spread retain multiplier1. Fit candidate-
bank-wide histories, never an RF-selected satellite whitelist. Test spread
0,0.25,0.5,1 using the existing chronological70/30 historical split, all before
RF. Require at least30 validation transitions and predictive gain greater than
log(validation count). Only4/20 scans qualify; the mean gain is about6m c0.
This does not materially solve the goal. Historical selection and qualification
share the later pre-RF block; RF accuracy is the subsequent evaluation, and
these20 scans are now development data. No per-scan choice uses GPS.

## 3. What limits the local position information?

INFORMATION_TABLE

![Nuisance information controls](nuisance_information.png)
![Endpoint uncertainty](endpoint_uncertainty.png)

These are **local generalized information scales**, not achieved position
errors, calibrated confidence intervals or a fundamental CRLB. At each saved
RF endpoint, condition on fitted noise and Student prior precisions. Form the
position derivative D, nuisance features U, point precision W, nuisance prior
precision P, and Schur information
I=D'WD−D'WU(P+U'WU)^−1U'WD. Its local covariance is I^−1; RMS radius is
sqrt(trace(I^−1)). Finite differences at0.01/0.02km agree within6.1e−10 in
relative derivative norm. The algebra is tested against dense marginalization.

Freeze selected nuisance groups at their fitted values for oracle controls;
do not set them to zero or refit claimed improved positions. Satellite phase
uncertainty dominates these local widths more than receiver uncertainty.
On257, all-uncertain RMS radius1.827km becomes1.522km if receiver corrections
are known,0.527km if satellite phases are known, and0.064km if all corrections
are known. Across20 scans, median radius drops from1.029km to0.221km when
phase is known. This motivates better independent orbital-phase information
and stronger geometric evidence, rather than merely more RF points.

The calculation conditions on Gamma precisions, excludes their uncertainty,
does not marginalize discrete identities, and initially assumes the recorded
UTC midpoint. Those omissions can make widths optimistic. Receiver/family
parameters remain correlated. This diagnostic identifies sensitivity, not
proof that any particular TLE is wrong or that0.5km is impossible.

## 4. Recorded UTC uncertainty was omitted from the position model

![UTC bracket sensitivity](UTC_bracket_sensitivity.png)

The prepared public observations explicitly retain the host timing bracket:
257 has±182.55ms;202 has±124.59ms. The previous fits use its midpoint. Test
five common clock nodes at−1,−0.5,0,0.5,1 times that half-width. Orbit-bank
queries shift in ECEF time, including Earth rotation. Hardware/smooth terms
remain functions of elapsed device time. This is one common UTC hypothesis
for both receivers/all satellites, not an independent orbital phase per family.
The catalogue cutoff stays at the original earliest UTC bound, so all selected
TLEs remain causal for every tested clock. Phase priors, observations, aliases
and labels stay fixed. No observation is trimmed within clock selection; both
arms must pass all original gates. All five nodes have equal fit budgets.

RF-only profile selection picks the early endpoint on both probes. On257 it
changes3.722/3.699km to2.877/2.859km, but improves c0 RF loss by only0.104:
the clock is weakly identified there. On202 it changes3.061/3.060km to
2.943/2.942km. These two probes do not establish a cohort correction. A
boundary maximum on a nearly flat clock profile is not a precise clock
measurement; proper uncertainty propagation is preferable to forcing a node.
No clock default or new ALGO01 accuracy claim is adopted from these cases.

The read-only archive inventory also checked the latest three pre-scan257
snapshots: none contained regional candidates with reference epochs after
the scan. A stale catalogue caused solely by excluding already-published
future-reference epochs is therefore unsupported on those inspected snapshots.
No such elements or post-observation TLEs were used in any fit.

## 5. Does the variational approximation reject the better geographic identity?

The257 alternative63070→48482 passes gates and gives a smaller evaluated
position error, while the existing RF objective rejects it. Audit the same
Gaussian/Gamma model with Rao-Blackwell importance sampling: sample noise
and phase precisions from the fitted variational Gamma proposal, analytically
integrate all Gaussian nuisance coefficients, and apply the exact prior/
proposal ratio. Likelihood powers and every normalization constant are kept.
The implementation is checked against analytic Student integration and direct
Gaussian quadrature, including fractional powers. No position is refit and
no model/prior changes. This is a c0 objective audit, not a c-arm algorithm
comparison. The paired localization results remain in the tables above.

The1024-draw audit gives a challenger disadvantage15.329 RF units versus
15.268 from the variational bound. Estimated bound gaps2.475/2.414 are nearly
the same for the two candidates; effective sample sizes847/868 and nominal
Monte Carlo SE0.029/0.027 pass the declared sampling rule. A4096-draw repeat
is in importance_audit.csv and the raw receipts. Sampling diagnostics do not
prove coverage of unseen modes, but this check supplies no evidence that the
variational approximation causes this identity decision. It leaves the causal
phase model, identities and underlying information as the relevant questions.

EVIDENCE_TABLE

## Evidence and reconstruction

[Position CSV](position_comparison.csv) · [Local information](local_information.csv) ·
[UTC controls](UTC_comparison.csv) · [Evidence audit](importance_audit.csv) ·
[Summary](summary.json) · [Validation](validation.json).

Raw protocols/outputs reside in ../2026_10_19_ds23_band_covariance/,
../2026_10_19_ds23_satellite_phase_scale/,
../2026_10_19_ds23_position_information/,
../2026_10_19_ds23_utc_bracket/ and
../2026_10_19_ds23_marginal_evidence/.
Scale receipts overlay ../2026_10_18_ds23_causal_phase_mean/history/.
Source snapshots overlay the prior ALGO01/DBG01 and research snapshots.
Use the repository venv, PYTHONPATH=src:tools, OPENBLAS_NUM_THREADS=1 and
OMP_NUM_THREADS=1. Numerical runs use bounded subprocesses; no new RF,
IQ reread, QNAP mutation or production component change is included.
'''.replace('POSITION_TABLE','\n'.join(table)).replace('INFORMATION_TABLE','\n'.join(info_table)).replace('EVIDENCE_TABLE','\n'.join(evidence_table))
    (OUT/'README.md').write_text(body);print('\n'.join(table),flush=True)


if __name__=='__main__':run()
