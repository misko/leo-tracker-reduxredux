"""Report precise-CFO controls, family reentry gates and physical orbit modes."""

import csv
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_refined_precision import OUT
from probe_ds23_raw_pilot_refinement import OUT as RAW
from report_algo01_ds23_sample import position_error
from run_algo01_ds23_sample import read,write,sha

CASES=('DS23-0202','DS23-0274')


def run():
    rows=[];sources={};radio=[];stages={}
    def add(case,name,pair,valid,failed=()):
        incumbent=read(OUT/(case+'.json'))['incumbent_arms']
        for arm,r in pair.items():
            selected=r if valid else incumbent[arm]
            rows.append(dict(case=case,method=name,arm=arm,paired_valid=valid,trial_error_km=position_error(r['endpoint_latlon']),
                reported_error_km=position_error(selected['endpoint_latlon']),calibration_points=r['active_points'],
                failed_tracks=';'.join(failed),negative_twice_elbo=r['negative_twice_elbo']))
    for case in CASES:
        d=read(OUT/(case+'.json'));add(case,'incumbent',d['incumbent_arms'],True)
        radio.extend(dict(case=case,**r) for r in d['radio_noise_receipts'])
        for method,r in d['results'].items():
            add(case,method,r['trial_arms'],r['paired_valid'])
        for suffix,name in [('_times','effective_time'),('_eccentric','eccentric_single_curve')]:
            r=read(OUT/(case+suffix+'.json'));add(case,name,r['trial_arms'],r['paired_valid'],r['failed_tracks'])
        if case=='DS23-0202':
            restore=read(OUT/(case+'_restore.json'))
            for method,r in restore['results'].items():add(case,'restore_'+method,r['trial_arms'],r['paired_valid'],r['failed_tracks'])
            family=read(OUT/(case+'_family.json'))
            for method,r in family['results'].items():add(case,'family_'+method,r['trial_arms'],r['paired_valid'],r['failed_tracks'])
            stages={name:r['trial_arms']['c0'] for name,r in restore['results'].items()}
            stages['effective_time']=read(OUT/(case+'_times.json'))['trial_arms']['c0']
            stages['eccentric_single_curve']=read(OUT/(case+'_eccentric.json'))['trial_arms']['c0']
            stages['eccentric_whole_family']=family['results']['eccentric']['trial_arms']['c0']
    for case in CASES:
        for suffix in ['','_times','_eccentric']+(['_restore','_family'] if case=='DS23-0202' else []):
            p=OUT/(case+suffix+'.json');sources[p.name]=sha(p)
    gains={case:read(OUT/(case+'_times.json'))['trial_arms']['c0']['negative_twice_elbo']-
           read(OUT/(case+'_eccentric.json'))['trial_arms']['c0']['negative_twice_elbo'] for case in CASES}
    # A development rule: same-data model comparison, every gate in both arms.
    family=read(OUT/'DS23-0202_family.json')['results'];valid=[(k,r) for k,r in family.items() if r['paired_valid']]
    chosen202=min(valid,key=lambda item:item[1]['trial_arms']['c0']['negative_twice_elbo'])[0] if valid else 'incumbent'
    a=read(OUT/'DS23-0274_times.json');b=read(OUT/'DS23-0274_eccentric.json')
    chosen274=min([(k,r) for k,r in [('precise',a),('eccentric',b)] if r['paired_valid']],
                  key=lambda item:item[1]['trial_arms']['c0']['negative_twice_elbo'])[0]
    policies={'DS23-0202':chosen202,'DS23-0274':chosen274}
    for case in CASES:
        base=read(OUT/(case+'.json'))['incumbent_arms']
        reproduced=read(OUT/(case+'.json'))['results']['original_reference1']['trial_arms']
        assert all(np.linalg.norm(np.array(base[a]['endpoint_east_north_km'])-reproduced[a]['endpoint_east_north_km'])<.001 for a in base)
    write(OUT/'summary.json',dict(position=rows,radio_noise=radio,source_evidence_sha256=sources,
        same_data_eccentricity_RF_improvement=gains,RF_only_development_policy=policies,
        policy_is_post_hoc_development_not_untouched_validation=True,target_met=False,
        no_full_DS23_or_new_cohort_accuracy_claim=True,GPS_used_only_here_for_evaluation=True,
        source_sha256=sha(Path(__file__))))
    with (OUT/'position_comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    fig,axes=plt.subplots(2,1,figsize=(15,9),constrained_layout=True)
    for ax,case in zip(axes,CASES,strict=True):
        methods=list(dict.fromkeys(r['method'] for r in rows if r['case']==case))
        for offset,arm,color in [(-.12,'c0','tab:blue'),(.12,'fitted_c','tab:orange')]:
            rr=[next(r for r in rows if r['case']==case and r['method']==m and r['arm']==arm) for m in methods]
            for k,r in enumerate(rr):
                ax.scatter(k+offset,r['trial_error_km'],marker='o' if r['paired_valid'] else 'x',color=color,s=45)
                if not r['paired_valid']:ax.scatter(k+offset,r['reported_error_km'],marker='_',color=color,s=80)
            ax.plot([],[],color=color,marker='o',ls='',label=arm)
        ax.set_xticks(range(len(methods)),methods,rotation=28,ha='right',fontsize=7)
        ax.axhline(.5,color='crimson',ls='--',lw=.7);ax.set(title=case+' · circles pass both-arm gates; crosses are rejected trials; bars show fallback',ylabel='Position error (km)')
        ax.grid(axis='y',alpha=.2);ax.legend()
    fig.savefig(OUT/'position_controls.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(13,5),constrained_layout=True)
    x=np.arange(len(radio))
    ax.bar(x-.2,[r['predictive_scatter_hz'] for r in radio],.4,label='Radio polynomial leave-one-out scatter')
    ax.bar(x+.2,[r['split_frame_proxy_hz'] for r in radio],.4,label='Alternating-frame difference / 2')
    ax.axhline(40,color='gray',ls='--',label='Old 40 Hz floor')
    ax.set_xticks(x,[r['track'].split('-RF')[0].replace('DS23-0','') for r in radio],rotation=25,ha='right',fontsize=8)
    ax.set(ylabel='Noise proxy (Hz)',title='Between-window scatter exceeds disjoint-frame disagreement, especially RX1')
    ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8);fig.savefig(OUT/'radio_uncertainty.png',dpi=160);plt.close(fig)
    target='DS23-0202-RX2-CH2-T001-RF10959687500.000000';fig,axes=plt.subplots(3,2,figsize=(14,10),constrained_layout=True)
    for ax,(name,result) in zip(axes.flat,stages.items(),strict=True):
        t=next(t for t in result['tracks'] if t['track']==target);gate=next(r for r in result['gates']['tracks'] if r['component']==target)
        values=np.array(t['conditional_residual_hz']);times=np.array(t.get('time_s',read(RAW/'DS23-0202_tracks.json')['panel_metadata']['tracks'][-1]['times']))
        diag=gate['conditional_residual_gate']['diagnostics'];acf=diag['lag1_acf'];threshold=4/np.sqrt(len(values))
        ax.plot(times,values,'.-',lw=.8);ax.axhline(0,color='k',lw=.6)
        ax.set(title=f'{name}\nRMS {np.sqrt(np.mean(values*values)):.1f} Hz · ACF {acf:.3f} / limit {threshold:.3f}\nconditional pass={gate["conditional_residual_gate"]["compatible"]}; all gates={gate["compatible"]}',
            xlabel='Scan time (s)',ylabel='Conditional CFO residual (Hz)');ax.grid(alpha=.2)
    fig.suptitle('Scan 202, RX2 CH2: residual structure and independent-owner support are separate gates')
    fig.savefig(OUT/'scan202_residual_gates.png',dpi=150);plt.close(fig)
    table=['| Scan | Trial | c=0 / fitted-c error km | Both-arm gates | Reported c=0 / fitted-c km |',
           '|---|---|---:|---|---:|']
    selected=['incumbent','refined_sigma40','refined_predictive_sigma','effective_time','eccentric_single_curve','family_precise','family_eccentric']
    for case in CASES:
        for method in selected:
            rr=[r for r in rows if r['case']==case and r['method']==method]
            if not rr:continue
            table.append(f'| {case} | {method} | {rr[0]["trial_error_km"]:.4f} / {rr[1]["trial_error_km"]:.4f} | {"Pass" if rr[0]["paired_valid"] else "Fail; fallback"} | {rr[0]["reported_error_km"]:.4f} / {rr[1]["reported_error_km"]:.4f} |')
    body='''# DS23: precise CFO uncertainty, family reentry and missing orbital directions

This development study improves two diagnostic scans without relaxing a gate
or using GPS in inference. Scan 202 can recover an originally excluded 71-point
satellite family with shared physical eccentricity modes: c=0/fitted-c error
falls from3.0609/3.0602 to2.6014/2.6013km. Scan274's RF-selected simpler model
reaches1.2507/1.2048km from1.3173/1.2769. These are two inspected development
scans, not a new 20-scan benchmark or evidence for the 0.5 km DS23 goal.

## An observation-ID correction changes the diagnosis

The earlier raw-IQ report incorrectly stated that scan202's two RX1 curves
were outside calibration. Exact ID intersection shows the opposite: RX1 CH2
andCH7 contribute21+16 active points, while the cleaner37-point RX2 CH2 curve
was masked. Both RX2 CH2 and its34-point CH3 companion, NORAD64442, were
excluded by the learned phase-prior refit. The numerical position results were
correct; the earlier explanation was not. The earlier report and its generator
are corrected. This audit explains why refining the RX2 curve alone did not
affect a fit with the old fixed mask.

## Learn noise from radio evidence, preserving original measurements

For each complete selected curve, fit degrees0–4 on reliable refined CFOs using
profile BIC, at least four samples per coefficient and a declared5Hz floor.
Use the RMS leave-one-out polynomial prediction error, r/(1−leverage), as a
conservative scatter proxy. Also compute alternating-frame frequency
differences after correcting for their distinct effective times and the
radio-polynomial rate; difference RMS/2 supplies another lower bound. Select
the maximum of these and5Hz. The alternating fits share epoch/rate assumptions,
so this is not fully independent validation or a calibrated error bar.

RX2 proxies are about10–13Hz; RX1 proxies are80–164Hz. Between-window scatter
is much larger than alternating-frame disagreement, especially RX1. This can
reflect hardware drift/jitter, interference, template mismatch or unresolved
curvature; the experiment does not identify a unique cause. A shared component
must be predicted across independent families before changing a receiver model.

![Radio uncertainty proxies](radio_uncertainty.png)

Boundary/control failures retain original CFO and its exact original effective
noise. They do not learn the refined scale. Every unmodified point retains its
old uncertainty; original observations, aliases and contracts remain unchanged.
Native WindowNoise still enforces40Hz. A separate research closure accepts
positive scales below40Hz and uses a common1Hz residual reference in every arm.
The normalized ELBO already includes absolute noise normalization. Tests prove
that changing reference alone changes only a constant, not the likelihood or
its derivatives; real baseline endpoints reproduce within1m. Fragment constants,
family powers, Gamma noise and phase/orbit priors otherwise remain fixed.

## Position results include failed trials and fallback

TABLE

Every pair uses identical data, aliases, labels, priors and search budgets:
regional-center cold start in25×25km, five phase rounds with48 position steps.
The fixed-mask controls differ only in refined CFO/noise. Reentry controls
explicitly augment the mask, with both c arms matched and no incumbent point
removed. Gate failures fall back to the incumbent pair; their geographically
better raw trial endpoints are not accepted results.

![Position controls](position_controls.png)

## Why the recovered curve was still rejected

Restoring just scan202 RX2 CH2 with archived data yields132Hz conditional RMS,
significant slope/step and lag-one correlation. Refined CFO with the old noise
reduces RMS to87Hz but leaves structure. Refined predictive noise reduces RMS
to16Hz; effective timestamps reduce it to15Hz. The remaining lag-one
correlation still exceeds4/sqrt(37)=0.658. A small RMS is not a white residual.

The original model already includes phase, mean motion, inclination and RAAN
uncertainty, but not both eccentricity-vector directions. Add those two physical
directions for each supported family, shared across receiver/channel tracks.
Widths come only from latest/previous causal TLE eccentricity disagreement,
transporting the previous TLE to the latest epoch, with the existing declared
floors/caps. They are uncertainty hypotheses, not measured covariance or free
per-track polynomials. This reduces CH2 conditional RMS to11Hz and passes its
residual screen. It still fails the existing independent-owner gate: its only
other nominated channel was masked. This is a support failure, not permission
to loosen residual gates or fit an unsupported extra orbit.

Restore the original curved family companions as a unit, restricted to points
accepted before the learned phase-prior exclusion. CH3 retains archived CFO
and original noise; no new measurement is invented. Without eccentricity both
curves fail. With the shared physical modes both pass, restoring71 calibration
points, and every other active track still passes in both c arms. Identities
and aliases are unchanged. No satellite was chosen by position error.

![Residual and support gates](scan202_residual_gates.png)

Effective timestamps use the local frequency-information instant within each
original20ms window. All time-dependent geometry, indexes, whiteners and
receiver bases are rebuilt. A synthetic asymmetric-envelope control with
opposite±2000Hz/s chirps predicts the local fitted CFO within0.2Hz. This qualifies
that local model calculation, not the actual historical acquisition timestamp.

## Complexity and selection matter

On the identical augmented observation set in202, eccentricity improves
penalized c=0 RF evidence by16.894 and is the only family-reentry model passing
both-arm gates. On274, adding eccentricity improves geographic error to
1.1787/1.1246km but worsens RF evidence by0.084. The RF-only development
selection therefore keeps the simpler precise/timestamp model on274, even
though GPS favors the more complex result. Do not compare raw ELBOs across
different observation sets, confidence powers or denominators to admit data.
Family reentry here uses physical support and the existing gates. Model
comparison is permitted only within the same observations and likelihood.
The legacy residual screen has a75Hz scale floor and a conservative correlation
threshold. Passing it means no structure detected by that screen, not proof of
independent noise at the new10Hz precision. Precision-aware predictive checks
are needed before treating this prototype as a default.

## Limits and next experiment

The0.5km mean/median goal remains unmet. These are post-hoc development
prototypes on two inspected scans. Neither full413 DS23 performance nor
untouched/location generalization has been established. Association totals
after full salvage have not been recomputed:71 restored calibration points
are not a claim of71 new globally associated GLRT points.

The newly active precise family should now be screened against the entire
unchanged causal catalogue, because earlier broad replacement searches could
not rank a family whose observations were masked. Refine its channel companion
from a bounded existing-IQ panel, test whether receiver-common discrepancies
are predictable rather than merely downweighted, and freeze a rule before
untouched scans. No future TLE, GPS-favored hyperparameter or rejected-trial
position is allowed to determine inference.

## Reproduction and receipts

[Summary](summary.json) · [All trials](position_comparison.csv) ·
[Full evidence](evidence.tar.gz) · [Inventory](evidence_inventory.json) ·
[Validation](validation.json) · [Source snapshots](source_snapshot/).

Use repository venv, PYTHONPATH=src:tools, BLAS/OMP threads1. Run
probe_ds23_refined_precision.py, probe_ds23_refined_timestamps.py and
probe_ds23_refined_eccentricity.py with --case for202/274;
probe_ds23_refined_restoration.py and probe_ds23_refined_family_reentry.py for202;
then this reporter. Raw panels are unchanged local prerequisites from the
previous study; no raw-IQ payload, new collection or recording mutation occurs.
Eight focused tests cover degree/scatter recovery, unit shifts, input validation,
likelihood-reference invariance, point-noise preservation, complete-curve/family
restoration, effective-time response and shared eccentricity design.
'''.replace('TABLE','\n'.join(table))
    (OUT/'README.md').write_text(body)
    print('\n'.join(table),flush=True)


if __name__=='__main__':run()
