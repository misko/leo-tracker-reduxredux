"""Evaluation-only height report; supplied GPS is not imported by inference."""

import csv
import shutil
import tarfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_height import OUT,SIGMAS
from ds23_frame_clock_comparison import compare_clock_curvature
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from remeasure_ds23_rx2_cohort import OUT as MEASURED
from report_algo01_ds23_sample import position_error,summarize
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha

LABELS={'0':'Height fixed 0','300':'Height SD 300 m','1000':'Height SD 1000 m','RF_selected':'RF-selected height prior'}


def csv_file(name,rows):
    with (OUT/name).open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)


def run():
    protocol=read(OUT/'cohort_protocol.json');cases=[r['dataset_label'] for r in read(SOURCE/'sample.json')['selected']]
    execution=read(OUT/'cohort_execution.json')
    assert len(execution)==40 and all(r['code']==0 for r in execution)
    assert {(r['case'],r['scope']) for r in execution}=={(c,s) for c in cases for s in ('archived','refined')}
    rows=[];validation=[];choices=[];causal=[]
    for case in cases:
        receipt_path=SOURCE/'causal_prior'/case/'receipt.json';receipt=read(receipt_path)
        assert not receipt['reference_position_used'] and receipt['search_box_width_km']==25
        assert max(receipt['latest_max_epoch_utc_ns'],receipt['latest_max_collection_utc_ns'])<=receipt['cutoff_utc_ns']
        causal.append(dict(case=case,receipt_sha256=sha(receipt_path),**receipt))
        for scope in ('archived','refined'):
            path=OUT/scope/(case+'.json');data=read(path)
            assert data['no_GPS_used']
            assert data['source_sha256']==sha(ROOT/'tools/probe_ds23_height.py')
            assert data['helper_sha256']==sha(ROOT/'tools/ds23_height_problem.py')
            saved_receipt=next(r for r in execution if r['case']==case and r['scope']==scope)
            assert saved_receipt['result_sha256']==sha(path)
            original=(read(LEARNED/(case+'.json'))['results']['mean_and_distribution']['arms'] if scope=='archived'
                      else read(MEASURED/(case+'_refined_local_noise_position.json'))['trial_arms'])
            for arm in ('c0','fitted_c'):
                null=data['results']['0']['arms'][arm];reference=original[arm]
                distance=float(np.linalg.norm(np.array(null['endpoint_east_north_km'])-reference['endpoint_east_north_km']))
                delta=null['negative_twice_elbo']-reference['negative_twice_elbo']
                assert distance<1e-4 and abs(delta)<1e-4,(case,scope,arm,distance,delta)
                validation.append(dict(case=case,scope=scope,arm=arm,null_position_difference_km=distance,null_RF_difference=delta))
                ids=[o for t in null['gates']['tracks'] for o in t['observation_ids']]
                assert len(ids)==len(set(ids))==null['active_points']
                for sigma,result in data['results'].items():
                    current=result['arms'][arm];actual=[o for t in current['gates']['tracks'] for o in t['observation_ids']]
                    assert len(actual)==len(set(actual))==len(ids) and set(actual)==set(ids)
                    if arm=='fitted_c':
                        partner=[o for t in result['arms']['c0']['gates']['tracks'] for o in t['observation_ids']]
                        assert set(partner)==set(actual)
                    policy=data['policy_arms'][sigma][arm]
                    rows.append(dict(case=case,scope=scope,method=sigma,arm=arm,paired_valid=result['paired_valid'],
                        policy_error_km=position_error(policy['endpoint_latlon']),trial_error_km=position_error(current['endpoint_latlon']),
                        baseline_error_km=position_error(data['baseline_arms'][arm]['endpoint_latlon']),
                        delta_RF_loss=current['negative_twice_elbo']-null['negative_twice_elbo'],
                        RMS_hz=current['RMS_hz'],baseline_trial_RMS_hz=null['RMS_hz'],points=current['active_points'],
                        height_m=current['height_mean_m'],height_sigma_m=current['approximate_covariance']['local_height_sigma_m'],
                        height_east_correlation=current['approximate_covariance']['height_east_north_correlation'][0],
                        height_north_correlation=current['approximate_covariance']['height_east_north_correlation'][1],
                        geometry_replay_qualified=current['geometry_replay_qualified'],
                        maximum_exact_CFO_difference_hz=current['exact_geometry_replay']['maximum_CFO_difference_hz'],
                        height_reference_gap_m=current['exact_geometry_replay']['height_reference_difference_m']))
            eligible=[name for name,r in data['results'].items() if r['paired_valid']]
            expected=min(eligible,key=lambda n:data['results'][n]['arms']['c0']['negative_twice_elbo']) if eligible else None
            assert data['selected']==expected
            choices.append(dict(case=case,scope=scope,selected=expected or 'incumbent_fallback'))
            for arm in ('c0','fitted_c'):
                current=data['selected_arms'][arm]
                source=(next(r for r in rows if r['case']==case and r['scope']==scope and r['method']==expected and r['arm']==arm)
                        if expected is not None else next(r for r in rows if r['case']==case and r['scope']==scope and r['method']=='0' and r['arm']==arm))
                rows.append(dict(source,method='RF_selected',paired_valid=expected is not None,
                    policy_error_km=position_error(current['endpoint_latlon'])))
    summary={scope:{method:{arm:summarize([r['policy_error_km'] for r in rows if r['scope']==scope and r['method']==method and r['arm']==arm])
                           for arm in ('c0','fitted_c')} for method in LABELS} for scope in ('archived','refined')}
    csv_file('position_and_height.csv',rows);csv_file('null_replay.csv',validation);csv_file('selected_priors.csv',choices)
    write(OUT/'causal_receipt_audit.json',causal)
    write(OUT/'summary.json',dict(position=summary,selected_priors=choices,
        local_height_covariance_conditions_on_Gamma_precision=True,all20_cases_in_both_scopes=True,
        target_mean_and_median_on_full_DS23_not_demonstrated=True))
    figures(cases,rows)
    timing_summary=timing_figures()
    volume=read(OUT/'volume_gradient.json')
    assert volume['source_sha256']==sha(ROOT/'tools/probe_ds23_volume_gradient.py') and volume['no_GPS_used']
    fig,ax=plt.subplots(figsize=(12,4.5),constrained_layout=True)
    ax.bar(range(20),[r['estimated_shift_norm_km'] for r in volume['records']])
    ax.set_xticks(range(20),[r['case'].split('-')[-1] for r in volume['records']],rotation=45)
    ax.set(ylabel='Local estimated shift (km)',title='c0 sensitivity to removing nuisance log-volume · not a refitted endpoint')
    ax.grid(axis='y',alpha=.2);fig.savefig(OUT/'volume_sensitivity.png',dpi=150);plt.close(fig)
    write(OUT/'validation.json',dict(all40_case_scope_processes_success=True,
        all120_paired_height_trials_and_80_null_replays_verified=True,
        exact_observation_ID_sets_match_all_height_and_c_arms=True,
        source_and_result_receipt_hashes_match=True,selection_recomputed_from_RF_only=True,
        original_latest_catalogue_receipts_causal=True,owned_tests_observed_passed=9,
        no_IQ_read_RF_collection_or_runtime_default_change=True,
        reporter_source_sha256=sha(Path(__file__))))
    table=['| Measurements / policy | c0 mean / median km | Fitted-c mean / median km |', '|---|---:|---:|']
    for scope in ('archived','refined'):
        for method,label in LABELS.items():
            a,b=summary[scope][method]['c0'],summary[scope][method]['fitted_c']
            table.append(f"| {scope} / {label} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} |")
    body='''# DS23: antenna-height uncertainty and horizontal localization

This is a fixed-rule height ablation on the original twenty development scans,
using both the archived measurements and the separately refined RX2 measurements.
It tests a missing geometry term without selecting a height from evaluation GPS.
It does not establish the 0.5 km goal on all 413 DS23 recordings or a new location.
ALGO01's published default remains unchanged.

TABLE

All scans remain in every denominator. A failed trial in either c arm retains
the previously published pair for that measurement policy; no extra point is
trimmed. A fixed height prior is applied to every scan, and the RF-selected
policy chooses the lowest full normalized c0 objective among paired-valid
hypotheses. Both c arms share the selected hypothesis. The archive includes
raw regressions and failed trials, not only final fallbacks.

![Archived measurements](archived_position.png)
![Refined measurements](refined_position.png)

## Model, prior and complexity

Keep the previous curved graph observations, satellite labels, alias integers,
point masks, receiver-support powers, radio-noise law, causal phase-history
forecast, three physical orbit directions and 300 Hz fragment constants.
The three alternatives are height fixed to 0, or one scan-wide Gaussian height
with mean 0 and SD 300 or 1000 metres. These are engineering hypotheses relative
to the geodetic ellipsoid, not surveyed antenna heights, terrain constraints,
or independently calibrated priors. A posterior mean outside -500 to 9000 m
fails an explicit broad engineering plausibility gate; the Gaussian itself is
not truncated. No coordinate-dependent terrain or supplied GPS enters this fit.

Height is a single shared physical nuisance across all receivers, bands and
satellites. Recompute range-rate, elevation, phase derivatives and all physical
orbit features at the current reference height. Differentiate the current
physical mean, including its previous orbital correction, with a central 50 m
height difference. Append sigma_height times this derivative as one Gaussian
feature. Subtract derivative times reference_height from the intercept so the
absolute prior remains centered at zero after every relinearization. The
existing normalized Gaussian/Gamma integration includes the extra coefficient
penalty and determinant; this is not a free vertical correction chosen to
reduce residual RMS. A zero height column integrates to one, including under
the existing Student phase prior.

All fits start at the center of the same 25x25 km region, 37.906, -122.545,
with phase and height references initially zero. Use five phase/height refreshes
and at most 48 position steps per refresh, identically in both c arms. The
horizontal position remains two nonlinear coordinates; height is marginalized
as a local Gaussian nuisance. Height and physical orbit references update from
the curved-data posterior only. No linear track calibrates offsets or drifts.

The refined scope uses the same CFOs, effective times and cached local noise
from the previous RX2 cohort, without rereading IQ. The archived scope uses
the original causal-history/receiver-support incumbent. Score differences are
only compared within one measurement scope; cross-noise RF scores are not
used to choose a geographically favorable measurement policy.

## Geometry checks and interpretation

Every full fit replays the complete physical design at its posterior height,
keeping its fitted coefficients and phase reference. Qualification requires
maximum prediction difference below 0.1 point-noise units and final height
reference movement below 0.5 m, alongside the unchanged residual, alias,
visibility and owner gates. Pointwise-noise development gates remain explicit
for refined data; archived data retain their original gates. A failed replay
or gate causes paired fallback, never a hidden deletion or relaxed threshold.

The zero-height controls reproduce the earlier endpoints and full objectives;
null_replay.csv records all eighty comparisons. Four owned height tests
check zero-height parity with the original physics, height derivatives including
orbit corrections, exact integration of an unused Gaussian height feature under
Student phase priors, and the sign/scale of a known-height Doppler signal.

Height uncertainty bars are local Gaussian approximations conditional on fitted
Gamma precisions and discrete identities. They include horizontal-position
coupling via the complete position/nuisance normal system. They are not
calibrated survey confidence intervals. Different scans can estimate different
heights because height trades against receiver and orbital errors. Do not pool
their fitted heights into a new site prior or select a prior using GPS error.

![Fitted height and local uncertainty](height_posteriors.png)
![Frequency evidence versus actual position change](RF_and_position.png)
![Vertical-horizontal ambiguity](height_position_coupling.png)

Reported horizontal errors use 37.849061591561885, -122.48574968092912, only in
this reporting tool. The dataset manifest supplies no per-recording surveyed
coordinate or antenna height. The existing assumption that every scan shares
that reference remains explicit; its confirmation has been requested. Every
TLE epoch/collection receipt still precedes the original cutoff, and no future
TLE, GPS-selected identity or new satellite nomination is introduced here.

## Unused frame timing: a separate sign/clock diagnostic

Scans 217 and 274 also test archived frame epochs as a possible additional
observable. Use the immutable device counter, within-visit probe offset and
integer/fractional epoch to form arrival time; never substitute the concatenated
IQ payload offset. Compute causal range at that arrival time using the
CFO-fitted position, phase and physical orbit modes, without evaluation GPS.
The first plots remove one affine clock per curve/gap segment. Their clock
residual RMS is tens of microseconds, which does not qualify a stable-clock
pseudorange model across a long graph track.

Inspect fixed 15 s receiver-time windows, separately testing window origins
0, 3, 6, 9 and 12 s. These are sensitivity controls, not asserted network
reconfiguration boundaries. Within each window, remove an affine component
from observed arrival phase and geometric range/c. Fit their curvature ratio
gamma only as a diagnostic; also report fixed gamma=+1 and -1 without fitting
that coefficient. The raw frame interval ambiguity remains 1/750 s. Long
gaps split at 10 s and no short-gap unwrap is certified solely by continuity.

At receiver-window origin 0, median gamma is -1.012/-0.991 for scans 217/274.
The ordinary +range/c model leaves median RMS 3.580/3.896 microseconds; the
opposite-sign diagnostic leaves 0.075/0.041 microseconds. The other window
origins show the same approximate negative coupling. Window records are
dependent and some curvature ratios are unstable when geometric curvature
is weak. The illustrated window is chosen by point count, not fit quality.

![Signed timing-curvature controls](signed_clock_curvature.png)
![Full-track timing diagnostic for scan 217](frame_timing/DS23-0217.png)
![Full-track timing diagnostic for scan 274](frame_timing/DS23-0274.png)

This does not justify reversing propagation delay or applying a timing-derived
position. Candidate explanations include frame-clock behavior and acquisition
epoch conventions; neither is established by this diagnostic. Synthetic controls
recover the expected positive-delay sign, but they do not identify the binary
used for every archived capture. No clock timing, free gamma or resulting
position enters any height experiment or ALGO01.

[Qin et al., Timing Properties of the Starlink Ku-Band Downlink](https://arxiv.org/html/2501.05302v1)
report beam-dependent frame clocks, timing adjustments, and frame/carrier rate
differences that can include opposite signs. Their clock-steering explanation
does not establish the cause of our measured curvature. This is an independent
reason to qualify a transmitter-clock model before interpreting frame timing
as pseudorange. Three timing/identity tests and two signed-curvature tests
supplement the four height tests; all nine pass.

## Local sensitivity to nuisance integration

A separate c0-only calculation differentiates the original objective's
quadratic, integration log-volume and Gamma terms at each archived RF endpoint.
The local Gauss–Newton estimate of the position change after dropping only
log-volume has median 0.154 km and maximum 0.340 km. This is a sensitivity
calculation, not a refitted position, a new inference policy or a c ablation.
The original adaptive precision updates still run inside the derivatives.
It neither certifies a distant alternative minimum nor establishes which
direction improves actual accuracy.

![Local nuisance-volume sensitivity](volume_sensitivity.png)

This warrants a controlled comparison of penalized profiling and marginal
integration with common frozen precisions, before attributing any change to
geometry volume. Their raw objective numbers would not be comparable as the
same probability. Such a position algorithm has not been run in this report.
Positive beam-clock agreement could also help validate additional track
identities, while absolute timing remains unqualified. Linear extensions may
provide position evidence only with calibration learned from curved tracks;
they must not learn receiver offsets or drifts.

## Reproduction and evidence

Run tools/run_ds23_height_cohort.py --stage pilot, then --stage cohort, followed
by tools/probe_ds23_frame_timing.py --case DS23-0217 and --case DS23-0274,
tools/probe_ds23_volume_gradient.py, then tools/report_ds23_height.py with the
repository venv, PYTHONPATH=src:tools
and BLAS/OMP threads one. Two numerical subprocesses each have a 600 s limit.
There is no IQ access, RF acquisition, external service or QNAP mutation.
Source snapshots overlay the previous causal-history and RX2 reports. Full
case/scope fits, phase/height refresh histories, raw gates and covariance/replay
checks are preserved in the lossless archive.

[Summary](summary.json) · [All positions and heights](position_and_height.csv) ·
[Null controls](null_replay.csv) · [RF model selection](selected_priors.csv) ·
[All clock windows](timing_curvature_windows.csv) · [Clock-window summaries](timing_curvature_summary.csv) ·
[Validation](validation.json) · [Causal receipt audit](causal_receipt_audit.json) ·
[Lossless evidence](evidence.tar.xz) · [Evidence hashes](evidence_inventory.json).
'''.replace('TABLE','\n'.join(table))
    (OUT/'README.md').write_text(body)
    package(cases)
    print('\n'.join(table),flush=True)


def timing_figures():
    records=[];fig,axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
    for column,case in enumerate(('DS23-0217','DS23-0274')):
        data=read(OUT/'frame_timing'/(case+'.json'))
        assert data['source_sha256']==sha(ROOT/'tools/probe_ds23_frame_timing.py') and data['no_GPS_used']
        examples=[]
        for track in data['tracks']:
            t=np.array(track['arrival_time_s']);rho=np.array(track['range_km'])
            for phase in (0.,3.,6.,9.,12.):
                for segment in compare_clock_curvature(t,t,rho,window_phase_s=phase):
                    records.append(dict(case=case,track=track['track'],receiver=track['receiver'],channel=track['channel'],
                        norad=track['norad'],window_phase_s=phase,points=segment['points'],gamma=segment['gamma'],
                        raw_RMS_us=segment['raw_RMS_us'],positive_range_RMS_us=segment['positive_range_RMS_us'],
                        negative_range_RMS_us=segment['negative_range_RMS_us'],geometric_RMS_us=segment['geometric_RMS_us'],
                        free_gamma_RMS_us=segment['free_gamma_RMS_us']))
                    if phase==0:examples.append((track,segment))
        track,segment=max(examples,key=lambda x:(x[1]['points'],x[1]['geometric_RMS_us']))
        t=segment['time_s'];y=segment['observed_curvature_us'];g=segment['geometric_curvature_us']
        axes[0,column].plot(t,y,'k.-',label='Observed frame timing')
        axes[0,column].plot(t,g,'--',label='Ordinary +range / c')
        axes[0,column].plot(t,-g,'--',label='Diagnostic -range / c')
        axes[0,column].set(title=f"{case} · RX{track['receiver']} CH{track['channel']} · {track['norad']}",ylabel='Affine-removed timing (microseconds)')
        axes[1,column].plot(t,y-g,'.-',label=f"+range model: {segment['positive_range_RMS_us']:.3f} us RMS")
        axes[1,column].plot(t,y+g,'.-',label=f"-range diagnostic: {segment['negative_range_RMS_us']:.3f} us RMS")
        axes[1,column].set(xlabel='Scan time (s)',ylabel='Residual (microseconds)',title=f"Diagnostic curvature coefficient {segment['gamma']:.3f}")
        for ax in axes[:,column]:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Unused timing observable · RF-nominated causal geometry · no GPS\nLargest-point-count 15 s receiver-time window per case; no timing applied to position')
    fig.savefig(OUT/'signed_clock_curvature.png',dpi=155);plt.close(fig)
    csv_file('timing_curvature_windows.csv',records)
    summary=[]
    for case in ('DS23-0217','DS23-0274'):
        for phase in (0.,3.,6.,9.,12.):
            rr=[r for r in records if r['case']==case and r['window_phase_s']==phase]
            summary.append(dict(case=case,receiver_window_phase_s=phase,windows=len(rr),
                **{name:float(np.median([r[name] for r in rr])) for name in
                   ('gamma','raw_RMS_us','positive_range_RMS_us','negative_range_RMS_us','geometric_RMS_us')}))
    csv_file('timing_curvature_summary.csv',summary)
    write(OUT/'timing_summary.json',dict(results=summary,cases_are_two_diagnostic_scans_not_a_cohort_test=True,
        receiver_time_windows_are_not_claimed_to_match_actual_network_reconfiguration_times=True,
        overlapping_phase_controls_are_dependent=True,timing_not_applied_to_any_position=True,
        curvature_model_does_not_certify_epoch_sign_convention_or_transmitter_compensation=True))
    return summary


def figures(cases,rows):
    for scope in ('archived','refined'):
        fig,axes=plt.subplots(2,1,figsize=(14,8),sharex=True,constrained_layout=True)
        for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
            for method,label in LABELS.items():
                y=[next(r['policy_error_km'] for r in rows if r['case']==case and r['scope']==scope and r['method']==method and r['arm']==arm) for case in cases]
                ax.plot(range(20),y,'.-',label=label)
            ax.axhline(.5,color='crimson',ls='--',lw=1);ax.set(ylabel='Horizontal error (km)',title=arm);ax.grid(alpha=.2);ax.legend(fontsize=8,ncol=2)
        axes[-1].set_xticks(range(20),[c.split('-')[-1] for c in cases],rotation=45)
        fig.suptitle(scope+' measurements · preset Gaussian height priors · paired failure → incumbent')
        fig.savefig(OUT/(scope+'_position.png'),dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(14,8),sharex=True,constrained_layout=True)
    for column,scope in enumerate(('archived','refined')):
        for row,arm in enumerate(('c0','fitted_c')):
            ax=axes[row,column]
            for sigma,shift in (('300',-.12),('1000',.12)):
                rr=[next(r for r in rows if r['case']==case and r['scope']==scope and r['method']==sigma and r['arm']==arm) for case in cases]
                ax.errorbar(np.arange(20)+shift,[r['height_m'] for r in rr],yerr=[r['height_sigma_m'] for r in rr],fmt='.',capsize=2,label='Prior SD '+sigma+' m')
            ax.axhline(0,color='black',ls=':',lw=.7);ax.set(ylabel='Height (m above ellipsoid)',title=scope+' / '+arm);ax.grid(alpha=.2);ax.legend(fontsize=8)
    for ax in axes[-1]:ax.set_xticks(range(20),[c.split('-')[-1] for c in cases],rotation=60)
    fig.suptitle('Local uncertainty includes horizontal position; identities and Gamma precisions fixed')
    fig.savefig(OUT/'height_posteriors.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
    for ax,scope in zip(axes,('archived','refined'),strict=True):
        for sigma in ('300','1000'):
            rr=[r for r in rows if r['scope']==scope and r['method']==sigma and r['arm']=='c0']
            null={r['case']:r['trial_error_km'] for r in rows if r['scope']==scope and r['method']=='0' and r['arm']=='c0'}
            ax.scatter([r['delta_RF_loss'] for r in rr],[r['trial_error_km']-null[r['case']] for r in rr],label='SD '+sigma+' m',s=30)
        ax.axhline(0,c='black',lw=.7);ax.axvline(0,c='black',lw=.7);ax.set(xlabel='RF loss minus fixed height (lower preferred)',ylabel='Raw position error change (km)',title=scope);ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Frequency evidence and position accuracy are separate outcomes · c0 raw trials')
    fig.savefig(OUT/'RF_and_position.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
    for ax,scope in zip(axes,('archived','refined'),strict=True):
        rr=[r for r in rows if r['scope']==scope and r['method']=='1000' and r['arm']=='c0']
        ax.scatter([r['height_east_correlation'] for r in rr],[r['height_north_correlation'] for r in rr])
        for r in rr:ax.annotate(r['case'].split('-')[-1],(r['height_east_correlation'],r['height_north_correlation']),fontsize=7)
        ax.axhline(0,c='black',lw=.7);ax.axvline(0,c='black',lw=.7);ax.set(xlim=(-1,1),ylim=(-1,1),xlabel='Height/east correlation',ylabel='Height/north correlation',title=scope);ax.grid(alpha=.2)
    fig.savefig(OUT/'height_position_coupling.png',dpi=150);plt.close(fig)


def package(cases):
    source_names=['tools/'+name+'.py' for name in ('ds23_height_problem','probe_ds23_height','run_ds23_height_cohort','report_ds23_height')]
    source_names+=['tests/analysis/test_ds23_height_problem.py']
    source_names+=['tools/probe_ds23_frame_timing.py','tools/ds23_frame_clock_comparison.py',
        'tools/probe_ds23_volume_gradient.py',
        'tests/analysis/test_ds23_frame_timing_tool.py','tests/analysis/test_ds23_frame_clock_comparison.py']
    inventory={}
    for name in source_names:
        target=OUT/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        inventory[str(target.relative_to(OUT))]=sha(target)
    write(OUT/'source_inventory.json',inventory)
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.suffix in ('.json','.log','.png')
           and 'source_snapshot' not in p.parts and p.name not in ('source_inventory.json','evidence_inventory.json')]
    with tarfile.open(OUT/'evidence.tar.xz','w:xz',preset=3) as archive:
        for path in sorted(paths):archive.add(path,arcname=str(path.relative_to(ROOT)))
    write(OUT/'evidence_inventory.json',{str(p.relative_to(ROOT)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in paths})


if __name__=='__main__':run()
