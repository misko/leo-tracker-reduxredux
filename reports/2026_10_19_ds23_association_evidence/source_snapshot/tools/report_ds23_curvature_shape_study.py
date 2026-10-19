"""Report completed causal shape, fragment covariance and curvature controls."""

from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_history_calibrated_phase import OUT as LEARNED,HISTORY
from probe_ds23_fragment_covariance import OUT as FRAGMENT
from probe_ds23_causal_shape_ensemble import OUT as SHAPE
from probe_ds23_statistical_curvature import OUT as CURVATURE
from probe_ds23_curvature_shape_combination import OUT as COMBINED
from report_ds23_association_evidence import save_csv,validate_pair
from report_algo01_ds23_sample import position_error,summarize
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan

OUT=ROOT/'reports/2026_10_19_ds23_curvature_shape_study'


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=sorted(read(FRAGMENT/'protocol.json')['cases'])
    assert len(cases)==20
    for directory in (FRAGMENT,SHAPE,CURVATURE,COMBINED):
        protocol=read(directory/'protocol.json');execution=read(directory/'execution.json')
        assert sorted(protocol['cases'])==cases and len(execution)==20 and all(r['code']==0 for r in execution)
        hashes=protocol['source_sha256']
        if isinstance(hashes,dict):assert all(sha(ROOT/'tools'/n)==h for n,h in hashes.items())
    rows=[];promotion=[];shape=[];rho=[];baseline_differences=[]
    for case in cases:
        primary=read(LEARNED/(case+'.json'))['results']['mean_and_distribution']
        f,s,c,m=[read(directory/(case+'.json')) for directory in (FRAGMENT,SHAPE,CURVATURE,COMBINED)]
        assert all(not d['GPS_used'] for d in (f,s,c,m))
        assert f['source_sha256']==sha(ROOT/'tools/probe_ds23_fragment_covariance.py')
        assert s['source_sha256']==sha(ROOT/'tools/probe_ds23_causal_shape_ensemble.py')
        assert c['source_sha256']==sha(ROOT/'tools/probe_ds23_statistical_curvature.py')
        assert m['source_sha256']==sha(ROOT/'tools/probe_ds23_curvature_shape_combination.py')
        assert c['original_active_observation_ids']==sorted(c['original_active_observation_ids'])
        assert set(c['original_active_observation_ids'])<=set(c['final_active_observation_ids'])
        ensemble=read(HISTORY/(case+'_shape_ensemble.json'));raw=read(HISTORY/(case+'.json'))
        assert ensemble['history_sha256']==sha(HISTORY/(case+'.json')) and not ensemble['GPS_or_radio_used']
        assert all(v['epoch']<=raw['cutoff_utc_ns'] and v['collected_utc_ns']<=raw['cutoff_utc_ns'] for versions in raw['past_versions'].values() for v in versions)
        shape.append(dict(case=case,qualified=ensemble['qualified'],mode=ensemble['chosen']['mode'],strength=ensemble['chosen']['strength'],
            validation_gain=ensemble['validation_gain'],required_gain=ensemble['required_gain']))
        choices={'baseline':primary['arms'],'fragment_RF_selected':f['results'][str(f['chosen'])]['arms'],
                 'causal_shape':s['arms'] if s['valid'] else primary['arms'],'curvature':c['arms'],'combined':m['arms']}
        for method,pair in choices.items():
            validate_pair(pair)
            for arm,r in pair.items():
                rows.append(dict(case=case,method=method,arm=arm,error_km=position_error(r['endpoint_latlon']),
                                 RMS_hz=r['RMS_hz'],calibration_points=r['active_points']))
        for arm in ('c0','fitted_c'):
            baseline_differences.append(abs(f['results']['0.0']['arms'][arm]['negative_twice_elbo']-primary['arms'][arm]['negative_twice_elbo']))
        rho.append(dict(case=case,chosen=f['chosen'],rho_half_valid=f['results']['0.5']['valid'],rho_nine_valid=f['results']['0.9']['valid']))
        for a in c['accepted']:promotion.append(dict(case=case,component=a['component'],points=a['radio']['points'],
            delta_BIC=a['radio']['delta_BIC'],degree=a['radio']['degree'],nonlinear_RMS_hz=a['radio']['nonlinear_RMS_hz']))
    methods=list(choices);labels=['Incumbent','Fragment covariance (RF-selected)','Pre-RF shape ensemble','Statistical curvature','Curvature + shape']
    summary={m:{arm:summarize([r['error_km'] for r in rows if r['method']==m and r['arm']==arm]) for arm in ('c0','fitted_c')} for m in methods}
    save_csv(OUT/'position_by_scan.csv',rows);save_csv(OUT/'new_calibration_curves.csv',promotion)
    save_csv(OUT/'causal_shape_choices.csv',shape);save_csv(OUT/'fragment_covariance_choices.csv',rho)
    fig,axes=plt.subplots(2,1,figsize=(14,7),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for method,label in zip(methods,labels,strict=True):
            ax.plot(range(20),[next(r['error_km'] for r in rows if r['case']==c and r['method']==method and r['arm']==arm) for c in cases],'.-',label=label)
        ax.axhline(.5,c='crimson',ls='--');ax.set(title=arm,ylabel='Position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=3)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('Causal evidence controls · all 20 development scans · no GPS rule selection')
    fig.savefig(OUT/'position_error_by_scan.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    for case,row_axes in zip(('DS23-0217','DS23-0161'),axes,strict=True):
        scan=final_scan(case);d=read(CURVATURE/(case+'.json'));accepted=sorted(d['accepted'],key=lambda r:-r['radio']['delta_BIC'])
        for ax,entry in zip(row_axes,accepted[:2],strict=True):
            track=scan.tracks[entry['track_index']];t=np.array(track['times']);y=np.array(track['values']);z=(t-t.mean())/np.ptp(t)
            sigma=np.array([scan.fixed_window_noise['per_observation_noise_sigma_hz'][oid] if scan.fixed_window_noise['extra_parameter_BIC_gain']>0 else scan.radio_sigma_hz for oid in track['observation_ids']])
            line=np.polynomial.polynomial.polyval(z,np.polynomial.polynomial.polyfit(z,y,1,w=1/sigma))
            curve=np.polynomial.polynomial.polyval(z,np.polynomial.polynomial.polyfit(z,y,entry['radio']['degree'],w=1/sigma))
            ax.scatter(t,y-line,s=15,label='GLRT minus best affine');ax.plot(t,curve-line,label='Selected polynomial departure')
            ax.set(title=f"{case} RX{track['receiver']} CH{track['channel']} · ΔBIC {entry['radio']['delta_BIC']:.1f}",xlabel='Time (s)',ylabel='Departure from affine (Hz)')
            ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Additional graph curves with statistical curvature · no linear calibration votes')
    fig.savefig(OUT/'promoted_curvature_examples.png',dpi=160);plt.close(fig)
    pilot=read(ROOT/'reports/2026_10_19_dynamic_pilot_timing/result.json')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    for ax,s in zip(axes,pilot['summaries'],strict=True):
        ax.plot(s['times_s'],s['physical_detrended_samples'],label='Physical positive delay');ax.scatter(s['times_s'],s['measured_detrended_samples'],label='Measured pilot epoch',s=22)
        ax.set(title=s['edge']+f" · gain {s['delay_curvature_gain']:.6f}",xlabel='Scene time (s)',ylabel='Epoch after removing affine (samples)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Noiseless dynamic delay/Doppler positive control · reference integer pilot estimator only')
    fig.savefig(OUT/'dynamic_pilot_control.png',dpi=160);plt.close(fig)
    table=['| Fixed rule | c0 mean / median km | Fitted-c mean / median km |','|---|---:|---:|']
    for method,label in zip(methods,labels,strict=True):
        a,b=summary[method]['c0'],summary[method]['fitted_c'];table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} |")
    write(OUT/'summary.json',dict(position=summary,new_curved_calibration_fragments=len(promotion),
        new_calibration_points=sum(r['points'] for r in promotion),shape_choices=shape,
        fragment_choice_histogram=dict(Counter(str(r['chosen']) for r in rho)),target_met=False))
    write(OUT/'validation.json',dict(all_four_cohorts_complete_20=True,paired_gates_and_ID_sets_match=True,
        raw_causal_history_times_valid=True,original_curvature_IDs_preserved=True,
        maximum_fragment_zero_control_loss_difference=max(baseline_differences),
        source_sha256=sha(Path(__file__)),GPS_only_used_for_reporting=True))
    body='''# DS23: further causal shape and curved-evidence controls

The 0.5 km mean/median target remains unmet. These are complete paired c=0 /
fitted-c controls on the original twenty development scans, not all 413
recordings or an untouched validation cohort. All start from the regional
25 × 25 km box center (37.906, −122.545); the supplied GPS reference is used
only in reporting. Inference uses the same strictly causal catalogue and
pre-scan-only TLE history, including both publication time and encoded epoch.

TABLE

![Position error on every scan](position_error_by_scan.png)

## Shared fragment constants

Correlate fragment constants only within the same satellite and exact
recorded RF. Every fragment retains marginal sigma 300 Hz. Correlations
0, 0.5 and 0.9 are evaluated with identical incumbent observations, labels,
aliases, physical priors and fit budgets. Selection uses minimum normalized
c0 negative-twice ELBO among variants passing both c-arm gates, then reuses
that choice for fitted-c. Rho0 passes 20/20, rho0.5 17/20, rho0.9 15/20;
the selected histogram is rho0.9 fifteen, rho0.5 two, rho0 three. Correlation
slightly improves the mean but worsens median localization. It is not a new
ALGO01 default. A cached all-bank replacement challenger on257 remains
RF-disfavored by 15.662 loss units under the selected covariance even though
its position happens to be closer to the reporting reference.

## Phase-aligned causal orbit-shape means

Use triples of genuinely earlier TLE versions A, B and C. Align A and C in
phase to B, then compare position and velocity residuals at C collection
time plus −150, 0 and +150 s, expressed in B's RTN frame. The causal history
study qualifies interpolation/extrapolation strengths by the existing
chronological 70/30 split before the RF scan; it never uses track labels,
the received frequencies or the GPS position. A robust state-prediction
criterion and one-parameter/mode complexity penalty choose the rule. The
mean state bank interpolates the phase-aligned previous and current TLE
states; this is a linear state-mean hypothesis, not a new exact SGP4 orbit.
Original Gaussian physical orbit modes and Student phase priors stay fixed.
Nineteen scans qualify: seventeen use interpolation strength0.125, two0.25;
one uses zero. All twenty paired gates pass. The overall mean scarcely
changes; fitted-c median improves to0.843 km. On217 the error changes from
1.025/0.869 to0.854/0.700 km (c0/fitted-c).

The large derived transition arrays are reproducible from the previously
published raw causal TLE histories and source snapshots. Compact receipts
under the history folder use a distinct *_shape_forecast_receipt.json name,
record full-derived-file hash/size and the rebuild command, and do not
pretend to be the full transition input. The small *_shape_ensemble.json
model choices are included. Regenerate transitions before replaying their
content-hash checks.

## Statistically supported weaker curvature

The original fixed 250 Hz departure-from-affine threshold discards some
well-sampled, statistically curved graph tracks. This control proposes
existing graph tracks with at least12 points, span20 s, weighted polynomial
order at most4 (at least four samples per coefficient), nonlinear ΔBIC≥10
and the existing residual noise screen. No merely linear trace calibrates.
The candidate must already have a frozen-calibration satellite association
and alias that agree in both c arms. Original curved calibration stays;
radio-only BIC determines greedy addition order, and both arms must pass
all old and new gates after every addition. Twenty-nine fragments add705
calibration points. These were often already associated as output tracks:
do not report them as705 newly associated GLRT points.

This curvature rule is not yet qualified against endpoint deletion or
leave-one-window-out leverage checks. A significant BIC gain can still be
driven disproportionately by a few observations. This is another reason to
keep the result as a research control rather than a new default.

![Examples of additional active curvature](promoted_curvature_examples.png)

Curvature promotion improves c0 mean/median from1.315/0.991 to1.298/0.901 km.
Its composition with the pre-RF shape mean keeps the same promotion pool,
observations and labels; both paired arms pass on all20. It gives
1.302/0.941 km c0 and1.245/0.851 fitted-c. This is a fixed composition,
not a scan-wise choice of the geographically better method. The two effects
are not additive and none is sufficient for the target.

## Physical timing sign control

A separate noiseless three-frame pilot experiment injects range-dependent
fractional delay and consistent carrier Doppler, then evaluates the pinned
published reference integer pilot estimator (commit772633600). Both band
edges recover positive delay curvature with gain0.999882 and RMS0.376
samples at2.5 MHz (~150 ns); a negative delay model misses by2902 samples.
The synthetic CFO search is seeded around the injected CFO. Linear
interpolation, pilot-only waveform and independent20 ms probes restrict its
scope. This is neither a blind detector evaluation nor qualification of the
actual production dense GLRT fractional-time estimator or real transmitter
clock. It does not explain the negative relation previously seen in some
real timing traces and does not justify using them as pseudoranges.

![Dynamic pilot timing control](dynamic_pilot_control.png)

## Receipts and reproduction

[Summary](summary.json) · [Validation](validation.json) · [All position results](position_by_scan.csv) ·
[Lossless full evidence](evidence.tar.gz) · [Evidence hashes](evidence_inventory.json) ·
[Added calibration curves](new_calibration_curves.csv) · [Shape choices](causal_shape_choices.csv) ·
[Fragment choices](fragment_covariance_choices.csv) ·
[Association and peak-recovery investigation](../2026_10_19_ds23_association_evidence/README.md).

Use the source snapshot with PYTHONPATH=src:tools, BLAS/OMP one thread. The
run_ds23_fragment_covariance, run_ds23_causal_shape_ensemble,
run_ds23_statistical_curvature and run_ds23_curvature_shape_combination
tools define bounded two-worker cohorts and record exact source hashes.
Rebuild shape transitions with learn_ds23_causal_shape_forecast.py on each
raw history CASE.json, then learn_ds23_causal_shape_ensemble.py on the
derived CASE_shape_forecast.json. Lossless evidence archives unpack to the
original reports/ paths. The pilot control includes its exact pinned source.
No IQ reread, new RF collection or archive mutation was performed.
'''
    (OUT/'README.md').write_text(body.replace('TABLE','\n'.join(table)));print('\n'.join(table))


if __name__=='__main__':run()
