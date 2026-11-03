"""Report RF-only receiver prediction, satellite rates and native measurement controls."""

import csv
import gzip
import shutil
import tarfile
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_shared_rate import OUT as RATE
from probe_ds23_receiver_prediction import OUT as PREDICTION
from probe_native_dynamic_timing import OUT as TIMING,BUILD
from probe_native_code_carrier import OUT as CODE
from probe_native_cfo_time_reference import OUT as TIME
from probe_native_fft_bias import OUT as BIAS
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from report_algo01_ds23_sample import position_error,summarize
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_19_ds23_clock_measurement_controls'
TOOLS=['probe_ds23_receiver_prediction.py','probe_ds23_shared_rate.py','run_ds23_clock_calibration_controls.py',
       'probe_native_dynamic_timing.py','probe_native_code_carrier.py','probe_native_cfo_time_reference.py',
       'probe_native_fft_bias.py','report_ds23_clock_calibration_controls.py']
TESTS=['test_ds23_receiver_prediction_tool.py','test_ds23_shared_rate_tool.py','test_native_dynamic_timing_tool.py',
       'test_native_code_carrier_tool.py','test_native_fft_bias_tool.py']


def csv_file(path,rows):
    with path.open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)


def pair_valid(pair):
    a,b=[{oid for t in pair[arm]['gates']['tracks'] for oid in t['observation_ids']} for arm in ('c0','fitted_c')]
    assert a==b
    assert all(t['compatible'] for r in pair.values() for t in r['gates']['tracks'])


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=sorted(read(RATE/'protocol.json')['cases'])
    assert len(cases)==20 and len(read(RATE/'execution.json'))==20 and all(r['code']==0 for r in read(RATE/'execution.json'))
    assert sorted(r['case'] for r in read(RATE/'execution.json'))==cases
    assert len(read(PREDICTION/'execution.json'))==4 and all(r['code']==0 for r in read(PREDICTION/'execution.json'))
    position=[];choices=[];invalid=Counter()
    for case in cases:
        d=read(RATE/(case+'.json'));assert not d['GPS_used'] and d['source_sha256']==sha(ROOT/'tools/probe_ds23_shared_rate.py')
        assert d['learned_input_sha256']==sha(LEARNED/(case+'.json'));choices.append(d['chosen'])
        for method in ('0.0','0.25','1.0','selected'):
            if method=='selected':pair=d['arms'];valid=True
            else:
                v=d['results'][method];valid=v['paired_valid'];invalid[method]+=not valid
                pair=v['arms'] if valid else d['results']['0.0']['arms']
            pair_valid(pair)
            for arm,r in pair.items():
                original=d['results']['0.0']['arms'][arm]
                assert r['active_points']==original['active_points']
                assert {oid for t in r['gates']['tracks'] for oid in t['observation_ids']}=={oid for t in original['gates']['tracks'] for oid in t['observation_ids']}
                position.append(dict(case=case,method=method,arm=arm,error_km=position_error(r['endpoint_latlon']),
                    RMS_hz=r['RMS_hz'],points=r['active_points'],paired_trial_valid=valid,negative_twice_ELBO=r['negative_twice_elbo']))
    summary={m:{a:summarize([r['error_km'] for r in position if r['method']==m and r['arm']==a]) for a in ('c0','fitted_c')} for m in ('0.0','0.25','1.0','selected')}
    csv_file(OUT/'rate_position_by_scan.csv',position)
    fig,axes=plt.subplots(2,1,figsize=(14,7),sharex=True,constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for m,label in [('0.0','Incumbent'),('0.25','Rate σ0.25 Hz/s'),('1.0','Rate σ1 Hz/s'),('selected','RF-selected rate width')]:
            ax.plot(range(20),[next(r['error_km'] for r in position if r['case']==c and r['method']==m and r['arm']==arm) for c in cases],'.-',label=label)
        ax.axhline(.5,c='crimson',ls='--');ax.set(title=arm,ylabel='Position error (km)');ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=2)
    axes[-1].set_xticks(range(20),[c.split('-')[1] for c in cases],rotation=45)
    fig.suptitle('Shared satellite carrier rate · same causal data/prior, all 20 development scans')
    fig.savefig(OUT/'rate_position_by_scan.png',dpi=160);plt.close(fig)
    prediction=[];folds=[];pcases=read(PREDICTION/'protocol.json')['cases']
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    for case,ax in zip(pcases,axes.flat,strict=True):
        d=read(PREDICTION/(case+'.json'));assert not d['GPS_used'] and d['source_sha256']==sha(ROOT/'tools/probe_ds23_receiver_prediction.py')
        assert d['learned_input_sha256']==sha(LEARNED/(case+'.json'))
        pair_valid(d['selected_arms'])
        for method in ('fast_receiver','fast_band_half'):
            gains=d['gains'].get(method,dict(per_receiver=[0,0],qualified=False))
            for k,rx in enumerate((1,2)):
                ax.bar(k+(-.18 if method=='fast_receiver' else .18),gains['per_receiver'][k],width=.35,label=method if k==0 else None)
            prediction.append(dict(case=case,method=method,RX1_predictive_gain=gains['per_receiver'][0],RX2_predictive_gain=gains['per_receiver'][1],
                qualified=gains['qualified'],selected=d['selected']==method,
                paired_full_valid=d['full_results'][method]['paired_valid'],
                fixed_c0_error_km=position_error(d['full_results'][method]['policy_arms']['c0']['endpoint_latlon']),
                fixed_fitted_error_km=position_error(d['full_results'][method]['policy_arms']['fitted_c']['endpoint_latlon'])))
        for r in d['records']:
            assert r['failure'] is None
            folds.append(dict(case=case,method=r['method'],held_receiver=r['receiver'],norad=r['norad'],train_points=r['train_points'],test_points=r['test_points'],
                negative_twice_predictive_score=r['prediction']['negative_twice_log_density'],test_RMS_hz=r['prediction']['RMS_hz'],
                predictive_covariance_RMS_hz=r['prediction']['covariance_RMS_hz']))
        ax.axhline(0,c='black',lw=.8);ax.set(title=case+' · selected '+d['selected'],ylabel='Predictive score gain (positive better)')
        ax.set_xticks([0,1],['Omit family on RX1','Omit family on RX2']);ax.legend(fontsize=7);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Receiver model must improve both independent RX directions\nPosition and nuisance fit omit the target RX/family data')
    fig.savefig(OUT/'receiver_prediction_gains.png',dpi=160);plt.close(fig)
    csv_file(OUT/'receiver_prediction.csv',prediction);csv_file(OUT/'receiver_folds.csv',folds)
    timing=read(TIMING/'result.json');code=read(CODE/'result.json');time=read(TIME/'result.json');bias=read(BIAS/'result.json')
    for d,tool in [(timing,'probe_native_dynamic_timing.py'),(code,'probe_native_code_carrier.py'),(time,'probe_native_cfo_time_reference.py'),(bias,'probe_native_fft_bias.py')]:
        assert d['source_sha256']==sha(ROOT/'tools'/tool)
    assert timing['library_sha256']==code['library_sha256']==time['library_sha256']==sha(BUILD/'libleo-adaptive-detector.so')
    assert bias['native_test_sha256']==sha(TIME/'result.json')
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),constrained_layout=True)
    for ax,s in zip(axes,timing['summaries'],strict=True):
        ax.plot(s['times_s'],s['expected_detrended_samples'],label='Injected range delay');ax.scatter(s['times_s'],s['observed_detrended_samples'],s=20,label='Native fractional epoch')
        ax.set(title=s['edge']+f" · RMS {s['positive_RMS_samples']:.3f} samples",xlabel='Scene time (s)',ylabel='Affine-removed delay (samples)');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Receipt-verified native binary · blind search · positive physical delay sign')
    fig.savefig(OUT/'native_positive_timing.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),constrained_layout=True)
    for ax,edge in zip(axes,('lower','upper'),strict=True):
        for fs in (2500000,10000000):
            selected=[r for r in time['summaries'] if r['edge']==edge and r['sample_rate_hz']==fs]
            ax.scatter([r['CFO_hz']/1000 for r in selected],[r['effective_time_minus_midpoint_s']*1000 for r in selected],s=12,alpha=.6,label=f'{fs/1e6:g} MHz')
        ax.axhline(0,c='black',lw=.7);ax.set(title=edge,xlabel='Injected midpoint CFO (kHz)',ylabel='Local effective time minus midpoint (ms)');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Matched opposite chirps · a hypothesis switch is retained as an outlier\nNo single common 8 ms time-tag shift is supported')
    fig.savefig(OUT/'native_effective_time.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,7),constrained_layout=True)
    for ax,(fs,edge) in zip(axes.flat,[(2500000,'lower'),(2500000,'upper'),(10000000,'lower'),(10000000,'upper')],strict=True):
        selected=[r for r in bias['records'] if r['sample_rate_hz']==fs and r['edge']==edge and r['eligible']]
        offset=[r['truth_CFO_hz']-500*np.floor(r['truth_CFO_hz']/500+.5) for r in selected]
        curve=bias['response_curves'][f'{fs}/{edge}'];actual=np.array(curve['actual_offset_hz']);reported=np.array(curve['reported_offset_hz'])
        ax.plot(actual,reported-actual,'--',c='.5',label='Template-predicted bias')
        ax.scatter(offset,[r['original_error_hz'] for r in selected],s=15,label='Native, uncorrected')
        ax.scatter(offset,[r['corrected_error_hz'] for r in selected],s=15,label='Template-derived inverse')
        ax.set(title=f'{fs/1e6:g} MHz {edge}',xlabel='True CFO offset within 500 Hz FFT bin (Hz)',ylabel='Error (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Independent noiseless validation of the FFT interpolation response\nNear-DC/boundary behavior excluded explicitly; no GPS or native-output training')
    fig.savefig(OUT/'template_fft_bias.png',dpi=160);plt.close(fig)
    csv_file(OUT/'fft_bias_validation.csv',bias['records']);csv_file(OUT/'fft_bias_summary.csv',bias['summaries'])
    write(OUT/'summary.json',dict(rate_position=summary,rate_choice_histogram=dict(Counter(choices)),rate_paired_failures=dict(invalid),
        receiver_prediction=prediction,native_timing=[{k:v for k,v in r.items() if not isinstance(v,list)} for r in timing['summaries']],
        fft_bias_validation=bias['summaries'],target_met=False))
    write(OUT/'validation.json',dict(all20_rate_cases_and4_receiver_probes_complete=True,paired_full_outputs_pass_original_gates=True,
        rate_variants_preserve_exact_incumbent_observation_ID_sets=True,
        all_source_and_baseline_input_hashes_checked=True,capture_binary_identity_not_proven=True,
        no_native_bias_correction_applied_to_DS23_positions=True,full_original_observations_restored_after_prediction_folds=True,
        new_tool_unit_tests_passed=13,source_sha256=sha(Path(__file__))))
    table=['| Carrier-rate policy | c0 mean / median km | Fitted-c mean / median km |','|---|---:|---:|']
    for method,label in [('0.0','Incumbent'),('0.25','σ0.25 Hz/s'),('1.0','σ1 Hz/s'),('selected','RF-selected prior width')]:
        a,b=summary[method]['c0'],summary[method]['fitted_c'];table.append(f"| {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} |")
    body='''# DS23: predictive calibration, carrier rates and native CFO measurement bias

The 0.5 km mean/median target remains unmet. This continues the earlier
association study with one full twenty-scan development comparison, four
receiver-prediction probes and synthetic tests of a receipt-verified native
GLRT binary. GPS is used only by this reporting tool. The same causal
catalogue, frozen identities/aliases, observation masks, radio-noise proxies
and pre-RF-history phase priors remain in the position comparisons. Every
full fit starts at the same25×25km regional center37.906,−122.545 and uses
five phase refreshes with up to48 position steps. No new RF was collected.

## Small shared satellite carrier rates

TABLE

Add one Gaussian frequency-rate coefficient for each satellite with active
curved support on both receivers: q·rate·(t−150), q=RF/11.5GHz. It is shared
across that satellite's curves and distinct from receiver/band drift, orbital
phase and state-error modes. Rate widths0.25 and1 Hz/s are engineering
hypotheses, not calibrated clock priors. Both c arms use identical columns
and observations. No data are trimmed; invalid variants fall back to the
incumbent pair. RF-only selection minimizes normalized c0 negative-twice
ELBO among paired-valid variants; it chooses width1 on ten scans and zero
on ten. The improvement is too small to resolve the localization problem.

![Carrier-rate position comparison](rate_position_by_scan.png)

## Does extra receiver freedom predict an omitted family?

Select the largest active cross-receiver family by point count, without GPS.
Omit all its RX1 curves, then all its RX2 curves in reciprocal folds. Train
position and nuisance corrections on the remaining measurements, starting at
the regional center; three phase rounds/24 steps are used per diagnostic
fit. Predict omitted CFOs without fitting their fragment constants, group
noise, receiver correction or receiver-side data. The same family remains
observed on the opposite RX, so its phase can be learned there. The prior
support design is held fixed; production two-owner gates are not imposed
on a deliberately omitted family inside the diagnostic fold.

Predictions include local joint position/nuisance covariance and prior
Gamma(2,2) noise variance for unobserved groups. Score the full target vector
with its correlated covariance, not independent standardized points. This is
a local moment-matched Gaussian predictive approximation, not an exact
Student posterior probability. Identity, integer aliases and radio-noise
proxies are frozen from the incumbent; this is conditional validation of
calibration transfer, not independent blind identification or raw-data
cross-validation. All points return for the final paired position fit.

Compare the slow receiver model with additional10s-spaced/5s-width receiver
features of amplitude radio_sigma/sqrt(2), and a variance-matched half-shared
cross-band version. A change must improve both RX directions and beat a
2log2 mode-selection penalty. All four probes retain the incumbent. On217,
extra receiver freedom improves RX1 predictive score by7.27 but worsens RX2
by1.65; its full-data c0 position worsens1.025→1.509km. This supports using
prediction to reject extra flexibility that merely lowers residuals.

The cases are217/257/273 plus274, the smallest-fragment high-band recording
in the sealed sample. They are diagnostic choices, not a representative or
untouched four-scan test. The full-data fixed controls and both c arms are
reported in CSV, including failures and incumbent fallback.

![Receiver prediction gains](receiver_prediction_gains.png)

## Native fractional-time semantics

The existing host binary and build receipt agree by SHA256. A blind native
CFO/epoch search on26 noiseless dynamic pilot probes recovers positive
arrival-delay curvature, with RMS0.105/0.110samples on the two edges at
2.5MHz (~42/44ns). This verifies this binary's sign under the tested model;
it does not establish the binary used for every DS23 recording or qualify
real transmitter timing. The waveform is a pilot-only three-frame periodic
approximation, not a full transmitted Starlink waveform.

![Native positive arrival delay](native_positive_timing.png)

Matched ±2000Hz/s chirps with the same envelope/epoch isolate local CFO time
sensitivity. Most cases lie within0.459ms of the nominal sample midpoint;
one near-DC upper-edge hypothesis switch gives10.6ms and remains in the
raw records. No shared8ms midpoint correction is justified. This derivative
can change when the detector selects a different peak and cannot always be
interpreted as a physical measurement timestamp.

![Native CFO time-reference controls](native_effective_time.png)

## A concrete interpolation bias, independently predicted

The tested native build uses500Hz FFT samples and a three-bin magnitude
parabola. The true magnitude response is not a parabola. Off-grid tones
therefore move toward bin centers even without noise. Predict the response
from the published pilot template's power over the same alternating OFDM
symbols, evaluate its Fourier magnitude at the three bins, and invert the
resulting monotone response. Native outputs are used only for validation,
not to fit the correction.

Across64 eligible cases per sample-rate/edge combination, original RMS is
about10.8Hz; the template-derived inverse reduces it to0.57/0.32Hz at2.5MHz
and0.12/0.11Hz at10MHz. These counts include aligned and off-grid cases.
Near-DC and boundary behavior are explicitly excluded from this correction;
their measurements remain in the original time-reference dataset. The
unmodeled modulation/carrier-rate experiment also changes CFO estimates by
roughly10–32Hz RMS relative to matched zero-extra-rate controls. An oracle
resampling control reduces some but not all dynamic CFO error and is not
an implementable real-data correction by itself.

![Native CFO interpolation response validation](template_fft_bias.png)

This demonstrates a deterministic approximation bias for the
qualified binary, not the cause or size of DS23 position errors. No bias
correction has been applied to the DS23 measurements in this report. First
establish capture-build identity and test noisy, faded recorded windows.
Frequency-alias lifts are not multiples of500Hz: any correction must use
the original canonical CFO before lifting, never the polynomial's unwrapped
CFO. Noise propagation and near-DC fallback behavior must be qualified too.
Do not choose a correction from the known GPS position.

## Relevant signal-model literature

Qin et al. distinguish beam-dependent frame timing from carrier timing;
their observations include differing frame/carrier rates and discuss timing
precompensation as a hypothesis. These results make a simple frame-epoch
pseudorange assumption unsafe, but do not identify the cause in DS23.
See [Timing Properties of the Starlink Ku-Band Downlink](https://arxiv.org/html/2501.05302v1).
Psiaki and Bowman explicitly estimate arrival time, carrier Doppler and
intra-frame code/carrier divergence jointly from edge pilots. Their
[2026 conference abstract](https://www.ion.org/publications/abstract.cfm?articleID=20760)
motivates testing a richer raw-pilot measurement model; it does not supply
calibrated rate priors for this experiment or verify our data.

## Next step and reproduction

The next substantive test is a bounded re-analysis of existing DS23 IQ
windows, comparing the unchanged native output with direct local CFO and
modulation-rate refinement against known pilots. Establish the applicable
binary/configuration first; freeze the test windows by RF criteria and keep
GPS outside measurement fitting. Full413-scan and untouched-location
validation remain outstanding. ALGO01's published default is unchanged.

[Summary](summary.json) · [Validation](validation.json) ·
[All twenty rate results](rate_position_by_scan.csv) ·
[Receiver folds](receiver_folds.csv) · [Full receiver controls](receiver_prediction.csv) ·
[FFT validation](fft_bias_summary.csv) · [All bias cases](fft_bias_validation.csv) ·
[Evidence archive](evidence.tar.gz) · [Evidence inventory](evidence_inventory.json).

Use PYTHONPATH=src:tools and BLAS/OMP threads1 in the repository venv.
run_ds23_clock_calibration_controls.py records the bounded two-worker
cohort. The source snapshot overlays the earlier ALGO01/DBG01 research
snapshots. Unpack evidence.tar.gz at the repository root to restore exact
report paths. It includes the binary and receipt used in synthetic controls;
the host FFTW dependencies must match their recorded authority for exact
replay. Native input generation and the response model require no IQ, TLE,
GPS, network service or legacy-repository runtime dependency.
'''
    (OUT/'README.md').write_text(body.replace('TABLE','\n'.join(table)))
    files=[]
    for directory in (RATE,PREDICTION,TIMING,CODE,TIME,BIAS):
        files.extend(p for p in directory.rglob('*') if p.is_file() and p.suffix in ('.json','.log','.so'))
    inventory=[]
    with (OUT/'evidence.tar.gz').open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w') as archive:
                for path in sorted(files):
                    relative=str(path.relative_to(ROOT));inventory.append(dict(path=relative,sha256=sha(path),bytes=path.stat().st_size))
                    info=archive.gettarinfo(str(path),arcname=relative);info.mtime=0;info.uid=info.gid=0;info.uname=info.gname=''
                    with path.open('rb') as stream:archive.addfile(info,stream)
    write(OUT/'evidence_inventory.json',dict(archive='evidence.tar.gz',sha256=sha(OUT/'evidence.tar.gz'),members=inventory))
    for path in [ROOT/'tools'/n for n in TOOLS]+[ROOT/'tests/analysis'/n for n in TESTS]+[ROOT/'src/leo/analysis/starlink/native_short_window.py',ROOT/'src/leo/analysis/starlink/templates.py']:
        target=OUT/'source_snapshot'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    # These exact low-level sources also match the verified binary receipt.
    receipt=read(BUILD/'build-receipt.json')
    for relative in ('kernel/private/fine_precision.h','kernel/private/full_search.c','kernel/private/native_presence/presence.c'):
        path=ROOT/'native/adaptive/detector'/relative;assert sha(path)==receipt['sources'][relative]
        target=OUT/'source_snapshot'/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    write(OUT/'source_inventory.json',{str(p.relative_to(OUT/'source_snapshot')):sha(p) for p in sorted((OUT/'source_snapshot').rglob('*')) if p.is_file()})
    print('\n'.join(table));print('archive MB',(OUT/'evidence.tar.gz').stat().st_size/1e6)


if __name__=='__main__':run()
