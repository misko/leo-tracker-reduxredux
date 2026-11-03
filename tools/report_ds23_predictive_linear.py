"""Validate predictive linear-curve controls; GPS enters reporting only."""

import csv
import hashlib
import shutil
import tarfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ds23_height_problem import geometry_features
from ds23_predictive_linear import linear_geometry
from probe_ds23_predictive_linear import OUT
from probe_ds23_height import context,OUT as HEIGHT
from probe_ds23_history_calibrated_phase import make_problem,OUT as LEARNED
from report_algo01_ds23_sample import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha

METHODS=('baseline','all_linear','cross_rx_linear')
LABELS=('Curved calibration incumbent','All qualified linear extensions','Cross-RX-supported linear extensions')


def save_csv(name,rows):
    with (OUT/name).open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def ids(r):
    return [o for t in r['gates']['tracks'] for o in t['observation_ids']]


def illustrative_curves(data):
    case='DS23-0217';r=data[case];entries=r['results']['all_linear']['entries']
    entries=sorted(entries,key=lambda e:(-e['points'],e['component']))[:6]
    scan,node,keep,powers,means,model,_,_=context(case,'archived');predictions={}
    for method in ('baseline','all_linear'):
        fit=(r['baseline_arms'] if method=='baseline' else r['results'][method]['arms'])['fitted_c']
        x=np.array(fit['endpoint_east_north_km'])
        p=make_problem(scan,node,keep,'fitted_c',np.array(fit['phase_reference']),powers,means,model['multiplier'],model['nu'])
        c=p.calculate(x);view,y,_,_,slices=linear_geometry(p,entries);g=geometry_features(view,x,0.)
        predictions[method]=view.q*g['intercept']+g['features']@c['coefficient']
    fig,axes=plt.subplots(len(entries),2,figsize=(13,2.4*len(entries)),squeeze=False,constrained_layout=True)
    for e,sl,ax in zip(entries,slices,axes,strict=True):
        track=scan.tracks[e['track_index']];t=track['times'];values=y[sl]
        ax[0].scatter(t,values/1000,c='black',s=12,label='Measured GLRT CFO + fixed integer alias')
        for method,color in [('baseline','.6'),('all_linear','tab:blue')]:
            prediction=predictions[method][sl]
            ax[0].plot(t,prediction/1000,c=color,label=method)
            ax[1].plot(t,values-prediction,'.-',c=color,label=method)
        ax[0].set(title=f"RX{track['receiver']} CH{track['channel']} · NORAD {e['norad']} · {e['points']} points",ylabel='Lifted raw CFO (kHz)')
        ax[1].set(ylabel='Prediction residual (Hz)');ax[1].axhline(0,c='black',ls=':',lw=.7)
        for a in ax:a.set_xlabel('Time in scan (s)');a.grid(alpha=.2);a.legend(fontsize=6)
    fig.suptitle('Scan217 · fitted-c · six longest added linear curves, selected by point count\nNo new-curve constant or linear-derived calibration correction is subtracted in residual panels')
    fig.savefig(OUT/'scan217_linear_predictions.png',dpi=150);plt.close(fig)


def run():
    protocol=read(OUT/'protocol.json');execution=read(OUT/'execution.json');cases=sorted(protocol['cases'])
    assert len(cases)==20 and {r['case'] for r in execution}==set(cases) and all(r['code']==0 for r in execution)
    data={};positions=[];counts=[];failures=[];max_delta=0.;max_phase=0.
    for receipt in execution:
        path=OUT/(receipt['case']+'.json');assert sha(path)==receipt['result_sha256']
        r=read(path);case=r['case'];data[case]=r
        assert r['no_GPS_used'] and r['no_original_point_trimming'] and r['curved_only_calibration_no_linear_normal_equation_update']
        assert r['source_sha256']==sha(ROOT/'tools/probe_ds23_predictive_linear.py')
        assert r['helper_sha256']==sha(ROOT/'tools/ds23_predictive_linear.py')
        assert r['baseline_arms']==read(LEARNED/(case+'.json'))['results']['mean_and_distribution']['arms']
        base_ids=ids(r['baseline_arms']['c0']);assert len(base_ids)==len(set(base_ids))
        for method in METHODS:
            v=None if method=='baseline' else r['results'][method]
            pair=r['baseline_arms'] if v is None else v['policy_arms']
            if v:
                new_ids=[o for e in v['entries'] for o in e['observation_ids']]
                assert len(new_ids)==len(set(new_ids)) and not set(new_ids)&set(base_ids)
                valid=all(all(t['compatible'] for t in a['gates']['tracks']+a['linear_gates']) and a['final_phase_change_s']<=.01 for a in v['arms'].values())
                assert valid==v['paired_valid']
                counts.append(dict(case=case,method=method,curves=len(v['entries']),points=len(new_ids),paired_valid=valid,
                    policy_additional_points=len(new_ids) if valid else 0))
            for arm in ('c0','fitted_c'):
                trial=pair[arm] if v is None else v['arms'][arm]
                assert set(ids(trial))==set(base_ids)
                if v:
                    assert {o for t in trial['linear_gates'] for o in t['observation_ids']}==set(new_ids)
                    max_delta=max(max_delta,trial['calibration_replay_max_coefficient_difference'])
                    max_phase=max(max_phase,trial['final_phase_change_s'])
                    for t in trial['gates']['tracks']+trial['linear_gates']:
                        if not t['compatible']:failures.append(dict(case=case,method=method,arm=arm,component=t['component']))
                positions.append(dict(case=case,method=method,arm=arm,policy_error_km=position_error(pair[arm]['endpoint_latlon']),
                    raw_trial_error_km=position_error(trial['endpoint_latlon']),curved_RMS_hz=trial['RMS_hz'],
                    curved_points=trial['active_points'],additional_points=0 if v is None else trial['additional_predictive_points'],
                    paired_valid=v is None or v['paired_valid']))
    assert max_delta==0
    save_csv('positions.csv',positions);save_csv('extension_counts.csv',counts)
    if failures:save_csv('failed_components.csv',failures)
    summary={};table=['| Policy | c0 mean / median km | Fitted-c mean / median km | Paired valid /20 |','|---|---:|---:|---:|']
    for method,label in zip(METHODS,LABELS,strict=True):
        summary[method]={}
        for arm in ('c0','fitted_c'):
            values=[r['policy_error_km'] for r in positions if r['method']==method and r['arm']==arm]
            summary[method][arm]=dict(mean_km=float(np.mean(values)),median_km=float(np.median(values)))
        valid=20 if method=='baseline' else sum(data[c]['results'][method]['paired_valid'] for c in cases)
        a,b=summary[method]['c0'],summary[method]['fitted_c']
        table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} | {valid} |")
    fig,axes=plt.subplots(2,1,figsize=(13,7),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for method,label in zip(METHODS,LABELS,strict=True):
            values=[next(r['policy_error_km'] for r in positions if r['case']==c and r['method']==method and r['arm']==arm) for c in cases]
            ax.plot(range(20),values,'.-',label=label,lw=1)
        ax.axhline(.5,c='crimson',ls='--',lw=1);ax.set(ylabel='Position error (km)',title=arm);ax.grid(alpha=.2);ax.legend(fontsize=8)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('Linear tracks predict position; curved tracks alone estimate calibration · 20 development scans')
    fig.savefig(OUT/'position_errors.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for method in METHODS[1:]:
            baseline=[next(r['policy_error_km'] for r in positions if r['case']==c and r['method']=='baseline' and r['arm']==arm) for c in cases]
            values=[next(r['policy_error_km'] for r in positions if r['case']==c and r['method']==method and r['arm']==arm) for c in cases]
            ax.scatter([next(r['policy_additional_points'] for r in counts if r['case']==c and r['method']==method) for c in cases],np.array(values)-baseline,label=method)
        ax.axhline(0,c='.5',lw=.7);ax.set(title=arm,xlabel='Added predictive GLRT points after paired fallback',ylabel='Position error change (km)');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.savefig(OUT/'points_and_accuracy.png',dpi=160);plt.close(fig)
    illustrative_curves(data)
    write(OUT/'summary.json',dict(position=summary,goal_half_km_met=False,counts=counts,
        no_default_promotion=True,original20_development_not_all413=True))
    write(OUT/'validation.json',dict(all20_processes_terminal_success=True,original_curved_IDs_exact_all80_trials=True,
        new_IDs_unique_disjoint_and_matched_both_c_arms=True,maximum_calibration_replay_difference=max_delta,
        maximum_final_phase_change_s=max_phase,all_source_receipts_and_baselines_match=True,
        four_owned_predictive_tests_passed=True,GPS_only_in_reporter=True,reporter_sha256=sha(Path(__file__))))
    shutil.copyfile(HEIGHT/'causal_receipt_audit.json',OUT/'causal_receipt_audit.json')
    body='''# DS23: linear-track position evidence with curved-only calibration

This prototype uses already associated linear graph extensions as additional
position evidence. Receiver offsets, receiver/band drifts, smooth hardware terms
and satellite corrections are still inferred from the original curved set only.
Shared calibration uncertainty is propagated across every added observation.
The 0.5 km mean and median goal is not established, and ALGO01 is not promoted.

TABLE

![Position errors by scan](position_errors.png)
![Additional points versus actual accuracy](points_and_accuracy.png)

Across the twenty scans, all-linear offers441curves/7,046points. Paired gates
retain357curves/5,734points in16scans. The cross-RX policy offers188curves/
3,169points and retains179curves/3,034points in19scans. These are additional
predictive observations; they do not enlarge the calibration set or its owner
votes. Four all-linear trials fall back:321,365,173 and74. Scan321 fails a
new linear gate;365 and173 fail an original curved gate;74 fails both. The
cross-RX trial on74 also fails an original curved gate. No failed curve is
quietly removed to retain the rest of its trial.

## Selection and matching controls

At the incumbent c0 RF-derived position, run the existing frozen-calibration
extension against families supported by accepted curved tracks. Keep only
non-curved graph tracks with at least6 original probes and no canonical-ID
overlap with curved evidence or another added curve. The all-linear control
uses every such extension. The cross-RX control keeps only families whose
original active curved evidence already spans both receivers. Both policies
are applied to every scan; there is no per-scan GPS choice. Labels and aliases
are frozen from c0 and identical in the fitted-c arm. The existing catalogue
and every TLE receipt remain causal; there is no new satellite nomination.

Original observations, masks, aliases, receiver-support powers, phase-history
prior, three physical orbit modes and300Hz fragment constants remain unchanged.
Every arm starts at the center of the same25x25km regional box centered on
(37.906,-122.545), with five phase refreshes and up to48 steps each. Original
curved gates, new-curve residual/alias/visibility gates and a0.01s phase-refresh
gate must pass in both arms. Otherwise keep the incumbent pair, without removing
another observation or relaxing a gate. Raw failures and regressions remain.

## Conditional predictive likelihood

At each trial horizontal position, fit the original curved-data hierarchical
model and recover coefficient mean m and conditional Gaussian precision A.
Rebuild the same physical features U_L at each new linear observation, including
its actual RX, band, RF and time. Existing curved-fragment constant columns are
zero for the new curves; their biases cannot leak into another track.

    calibration_mean = m(curved data, position)
    predictive_mean = nominal_Doppler_L + U_L m
    covariance_L = D_L + U_L A^-1 U_L' + 300² Z Z'

Z gives one independent constant per new curve. D_L uses the original radio-only
point-noise law, multiplied by2 in variance: an unseen Gamma(2,2) noise precision
has E[1/tau]=2. This is a Gaussian approximation to a heavy-tailed predictive
distribution, not a fitted extra noise law or calibrated probability. Added
linear predictive factors have power1; the original curved powers are unchanged.
The full calibration covariance is shared across tracks, receivers and families.
It is conditioned on the curved posterior Gamma precision means, not on fixed
perfect hardware or independent pointwise calibration error bars.

The optimizer adds the normalized Gaussian predictive cost to the existing
curved bound. New linear points never enter calibration normal equations,
Gamma updates, owner votes or phase-reference estimates. They can affect the
chosen horizontal position, at which curved data alone are refit. This is a
modular predictive research objective; do not call it the exact full
hierarchical joint posterior. Its coefficient replay against curved-only
calibration at the same position is exactly unchanged in every saved fit.

Unlike fitting all points jointly, a coincident linear slope cannot create its
own receiver drift. Unlike a plug-in calibration estimate, the shared covariance
prevents many copies of the same uncertain calibration direction becoming
independent evidence. The synthetic dense-covariance and shared-mode controls
verify that distinction. Gaussian nuisance integration includes both the prior
penalty and determinant; extra points are not rewarded simply for being added.

## Scan217 and limits

The nine accepted extensions supply151points; the cross-RX subset supplies77.
The all-linear raw trial changes c0 error from1.025 to0.775km and fitted-c error
from0.869 to0.529km. This was the pilot development case, not an untouched
validation. The second pilot, scan274, regresses with all-linear evidence:
1.277 to1.345km fitted-c. Both outcomes are retained in the cohort table.

![Scan217 measured curves and curved-only predictions](scan217_linear_predictions.png)

The figure uses the six longest added tracks by point count, not by accuracy
or residual improvement. CFOs are original measurements plus a fixed integer
alias; residuals subtract the complete curved-only mean, without subtracting
a newly fitted constant or a linear-derived calibration term. These plots do
not establish the truth of the frozen satellite identities. Alternative label
competition and receiver/family predictive calibration remain relevant.

Actual position error uses (37.849061591561885,-122.48574968092912) in this
reporter only, under the existing unconfirmed same-site assumption. These are
the original twenty development scans, not all413 DS23 recordings or independent
new-location validation. Compare each prespecified policy across all scans,
including fallback failures. Losses with different observation sets cannot be
ranked to select a geographically favorable policy; lower CFO RMS alone cannot
establish more accurate position. No new RF, IQ read or QNAP mutation occurs.

## Reproduction

Use the repository venv, PYTHONPATH=src:tools and BLAS/OMP threads one. Run
tools/run_ds23_predictive_linear.py and tools/report_ds23_predictive_linear.py.
Two subprocesses have300s per-case bounds. Four owned tests check dense
predictive covariance parity, dependence of repeated shared-mode observations,
an empty extension identity, and zero feedback to curved calibration despite
inconsistent added linear measurements. Overlay the frozen-precision/height
and earlier ALGO01 source snapshots before these research sources.

[Positions and raw trials](positions.csv) · [Additional evidence](extension_counts.csv) ·
[Failed components](failed_components.csv) ·
[Summary](summary.json) · [Validation](validation.json) · [Protocol](protocol.json) ·
[Execution](execution.json) · [Causal receipts](causal_receipt_audit.json) ·
[Lossless full evidence](evidence.tar.xz) · [Evidence hashes](evidence_inventory.json).
'''
    (OUT/'README.md').write_text(body.replace('TABLE','\n'.join(table)))
    snapshot=OUT/'source_snapshot';inventory={}
    for name in ['tools/ds23_predictive_linear.py','tools/probe_ds23_predictive_linear.py','tools/run_ds23_predictive_linear.py',
                 'tools/report_ds23_predictive_linear.py','tests/analysis/test_ds23_predictive_linear_tool.py']:
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        inventory[str(target.relative_to(OUT))]=sha(target)
    write(OUT/'source_inventory.json',inventory)
    paths=[OUT/'protocol.json',OUT/'execution.json']+[p for p in OUT.iterdir() if p.name.startswith('DS23-') and p.suffix in ('.json','.log')]
    evidence={}
    with tarfile.open(OUT/'evidence.tar.xz','w:xz',preset=3) as t:
        for p in sorted(paths):
            relative=str(p.relative_to(ROOT));evidence[relative]=dict(sha256=sha(p),bytes=p.stat().st_size);t.add(p,arcname=relative)
    with tarfile.open(OUT/'evidence.tar.xz','r:xz') as t:
        assert len(t.getmembers())==len(evidence)
        for m in t.getmembers():assert hashlib.sha256(t.extractfile(m).read()).hexdigest()==evidence[m.name]['sha256']
    write(OUT/'evidence_inventory.json',evidence)
    print('\n'.join(table),flush=True)


if __name__=='__main__':run()
