"""Evaluate the sealed RX2 cohort; reference coordinates enter this stage only."""

import csv
import shutil
import tarfile
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ds23_measurement_noise import learn_local_noise
from probe_ds23_refined_curve_position import proposed_delta
from probe_ds23_rx2_measurement_position import METHODS
from remeasure_ds23_rx2_cohort import OUT
from report_algo01_ds23_sample import position_error, summarize
from report_ds23_raw_pilot_refinement import choose_degree, polynomial
from run_algo01_ds23_sample import ROOT, read, write, sha

FAST = ROOT / 'reports/2026_10_19_ds23_fast_pilot_estimator'
LABELS = dict(baseline='Incumbent', refined_original_noise='CFO/time, original noise',
    refined_local_noise='CFO/time, local noise', refined_local_noise_five_orbit='Local noise + five orbit modes',
    RF_orbit_selection='RF-selected three/five orbit modes')
POLICIES = ('baseline',)+METHODS+('RF_orbit_selection',)


def csv_file(path, rows):
    with path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def radio_rows(raw):
    lookup = {r['point']['observation_id']: r for r in raw['rows']}
    _, receipts = learn_local_noise(raw)
    noises = {r['track']: r for r in receipts}
    result = []
    for track in raw['panel_metadata']['tracks']:
        rows = [lookup[o] for o in track['observation_ids']]
        t, y = np.asarray(track['times']), np.asarray(track['values'])
        # The archived-curve degree stays fixed for the before/after comparison.
        degree = choose_degree(t, y, 150.)
        before = polynomial(t, y, degree)
        changes = [proposed_delta(r, 'joint_CFO_epoch_rate') for r in rows]
        delta = np.array([d for d, reason in changes])
        offsets = np.array([r['joint_CFO_epoch_rate']['effective_time_from_probe_start_s']-.01
                            if reason=='refined' else 0 for r, (d, reason) in zip(rows, changes, strict=True)])
        after = polynomial(t+offsets, y+delta, degree)
        noise = noises.get(track['key'], {})
        result.append(dict(case=raw['case'], track=track['key'], channel=track['channel'],
            format=raw['panel_metadata']['format'], sample_rate_hz=raw['panel_metadata']['sample_rate_hz'],
            points=len(rows), refined=sum(reason=='refined' for d, reason in changes),
            original_degree=degree, original_RMS_hz=before['RMS_hz'], refined_RMS_hz=after['RMS_hz'],
            original_lag1=before['lag_one_correlation'], refined_lag1=after['lag_one_correlation'],
            local_noise_hz=noise.get('selected_sigma_hz'), split_noise_hz=noise.get('split_frame_proxy_hz')))
    return result


def qualification():
    results = []
    for path in sorted(OUT.glob('*_qualification.json')):
        data = read(path)
        rows = data['rows']
        delta = [r['joint_CFO_epoch_rate']['score']-r['reference']['result']['score'] for r in rows]
        results.append(dict(case=data['case'], points=len(rows), sample_rate_hz=data['panel_metadata']['sample_rate_hz'],
            maximum_CFO_difference_hz=max(abs(r['joint_CFO_epoch_rate']['CFO_hz']-r['reference']['result']['CFO_hz']) for r in rows),
            minimum_score_difference=min(delta), score_regressions_below_negative_1e_minus6=sum(d < -1e-6 for d in delta),
            continuous_core_seconds=sum(r['core_seconds'] for r in rows),
            reference_fit_seconds_excluding_common_scout=sum(r['reference']['seconds'] for r in rows),
            public_score_replays_within_1e_minus9=sum(max(abs(v) for v in r['public_score_replay'].values()) <= 1e-9 for r in rows),
            continuous_epoch_boundaries=sum(r['joint_CFO_epoch_rate']['epoch_search_boundary'] for r in rows),
            reference_epoch_boundaries=sum(r['reference']['result']['epoch_search_boundary'] for r in rows)))
    csv_file(OUT / 'qualification.csv', results)
    return results


def run():
    protocol = read(OUT / 'protocol.json')
    cases = [r['case'] for r in protocol['cases']]
    assert len(cases) == 20
    execution = read(OUT / 'measure_execution.json')
    assert sorted(r['case'] for r in execution) == sorted(cases) and all(r['code']==0 for r in execution)
    by_case = {r['case']: r for r in execution}
    causal = []
    from run_algo01_ds23_sample import OUT as SOURCE
    for case in cases:
        receipt_path = SOURCE / 'causal_prior' / case / 'receipt.json'
        receipt = read(receipt_path)
        assert not receipt['reference_position_used'] and receipt['search_box_width_km']==25
        assert receipt['latest_max_epoch_utc_ns'] <= receipt['cutoff_utc_ns']
        assert receipt['latest_max_collection_utc_ns'] <= receipt['cutoff_utc_ns']
        causal.append(dict(case=case, receipt_sha256=sha(receipt_path), **receipt))
    write(OUT / 'causal_receipt_audit.json', causal)
    positions, radio, gates, measurements = [], [], [], []
    for item in protocol['cases']:
        case = item['case']
        raw_path = OUT / (case+'_refined.json')
        raw = read(raw_path)
        assert sha(raw_path) == by_case[case]['result_sha256']
        assert raw['source_sha256'] == sha(ROOT / 'tools/remeasure_ds23_rx2_cohort.py')
        assert raw['refinement_source_sha256'] == sha(ROOT / 'tools/fast_local_pilot_refinement.py')
        assert raw['plan_sha256'] == item['plan_sha256'] == sha(OUT / (case+'_plan.json'))
        plan = read(OUT / (case+'_plan.json'))
        assert {r['point']['observation_id'] for r in raw['rows']} == {r['observation_id'] for r in plan['points']}
        assert len(raw['rows']) == item['points']
        radio.extend(radio_rows(raw))
        reasons = [proposed_delta(r, 'joint_CFO_epoch_rate')[1] for r in raw['rows']]
        measurements.append(dict(case=case, format=item['format'], sample_rate_hz=item['sample_rate_hz'],
            curves=item['curves'], points=item['points'], refined=reasons.count('refined'),
            boundary_or_control_fallbacks=len(reasons)-reasons.count('refined'),
            median_core_seconds=float(np.median([r['core_seconds'] for r in raw['rows']])),
            wall_seconds=raw['seconds'], decoded_bytes=raw['decoded_bytes'], raw_windows_read=raw['raw_windows_read']))
        first = read(OUT / (case+'_'+METHODS[0]+'_position.json'))
        authorities = read(SOURCE / case / 'result.json')
        tracks_by_key = {t['key']:t for t in read(SOURCE / case / 'tracks.json')}
        flattened_ids = [oid for r in authorities['final_node']['seed']['rows'] if r['active_curvature']
                         for oid in tracks_by_key[r['component']]['observation_ids']]
        assert len(flattened_ids)==len(first['original_mask'])
        expected_ids = {oid for oid, good in zip(flattened_ids, first['original_mask'], strict=True) if good}
        candidates = {}
        for method in ('baseline',)+METHODS:
            data = first if method=='baseline' else read(OUT / (case+'_'+method+'_position.json'))
            if method != 'baseline':
                assert data['source_sha256'] == sha(ROOT / 'tools/probe_ds23_rx2_measurement_position.py')
                assert data['refined_sha256'] == sha(raw_path)
                candidates[method] = data
            for arm in ('c0', 'fitted_c'):
                reference = data['baseline_arms'][arm]
                trial = reference if method=='baseline' else data['trial_arms'][arm]
                chosen = reference if method=='baseline' else data['policy_arms'][arm]
                labels = sorted({r['candidate_index'] for r in authorities['final_node']['seed']['rows'] if r['active_curvature']})
                phase = np.asarray(trial['state']['phases'])[labels]
                gap = float(max(abs(phase-np.asarray(trial['phase_reference']))))
                assert trial['active_points'] == reference['active_points'] == int(np.sum(data['original_mask']))
                positions.append(dict(case=case, method=method, source_method=method, arm=arm,
                    error_km=position_error(chosen['endpoint_latlon']),
                    trial_error_km=position_error(trial['endpoint_latlon']),
                    baseline_error_km=position_error(reference['endpoint_latlon']),
                    paired_valid=True if method=='baseline' else data['paired_valid'],
                    points=trial['active_points'], trial_RMS_hz=trial['RMS_hz'], baseline_RMS_hz=reference['RMS_hz'],
                    trial_negative_twice_elbo=trial['negative_twice_elbo'],
                    baseline_negative_twice_elbo=reference['negative_twice_elbo'],
                    maximum_phase_reference_gap_s=gap, maximum_absolute_phase_s=float(max(abs(phase)))))
                if method != 'baseline':
                    actual_ids = [oid for track in trial['gates']['tracks'] for oid in track['observation_ids']]
                    assert len(actual_ids)==len(set(actual_ids))==len(expected_ids) and set(actual_ids)==expected_ids
                    for track in trial['gates']['tracks']:
                        a, b = track['profile_noise'], track['conditional_noise']
                        gates.append(dict(case=case, method=method, arm=arm, track=track['component'],
                            norad=track['norad'], points=track['points'], compatible=track['compatible'],
                            hard_bounds_pass=track['hard_bounds_pass'], legacy_compatible=track['legacy_compatible'],
                            profile_pass=a['noise_screen_pass'], conditional_pass=b['noise_screen_pass'],
                            mean_z=b['mean_z'], slope_z=b['slope_z'], quadratic_BIC=b['quadratic_bic_gain'],
                            step_z=b['maximum_step_z'], lag1=b['lag1_acf'], RMS_hz=track['conditional_RMS_hz']))
            if method != 'baseline':
                assert data['trial_arms']['c0']['active_points'] == data['trial_arms']['fitted_c']['active_points']
        eligible = [m for m in METHODS[1:] if candidates[m]['paired_valid']]
        selected = min(eligible, key=lambda m:candidates[m]['trial_arms']['c0']['negative_twice_elbo']) if eligible else 'baseline'
        for arm in ('c0', 'fitted_c'):
            row = next(r for r in positions if r['case']==case and r['method']==selected and r['arm']==arm)
            positions.append(dict(row, method='RF_orbit_selection'))
    csv_file(OUT / 'position_by_scan.csv', positions)
    csv_file(OUT / 'curve_metrics.csv', radio)
    csv_file(OUT / 'measurement_by_scan.csv', measurements)
    csv_file(OUT / 'gate_metrics.csv', gates)
    summary = {method:{arm:summarize([r['error_km'] for r in positions if r['method']==method and r['arm']==arm])
                       for arm in ('c0', 'fitted_c')} for method in POLICIES}
    counts = {method:sum(r['paired_valid'] for r in positions if r['method']==method and r['arm']=='c0') for method in METHODS}
    qualifiers = qualification()
    identities = []
    for case in ('DS23-0217', 'DS23-0321'):
        path = OUT / 'catalogue' / (case+'.json')
        data = read(path)
        plan = read(OUT / 'catalogue' / (case+'_plan.json'))
        assert data['source_sha256']==sha(ROOT / 'tools/probe_ds23_rx2_catalogue.py')
        for trial in data['trials']:
            baseline = data['trials'][0]['arms']['c0']
            identities.append(dict(case=case, source_norad=plan['source_norad'],
                candidate_norad=trial['proposal']['norad'], paired_valid=trial['paired_valid'],
                selected=data['chosen'] is not None and trial['proposal']['index']==data['chosen']['proposal']['index'],
                delta_c0_RF_loss=trial['arms']['c0']['negative_twice_elbo']-baseline['negative_twice_elbo'],
                c0_error_km=position_error(trial['arms']['c0']['endpoint_latlon']),
                fitted_c_error_km=position_error(trial['arms']['fitted_c']['endpoint_latlon'])))
    csv_file(OUT / 'identity_trials.csv', identities)
    write(OUT / 'summary.json', dict(position=summary, paired_valid_scans=counts,
        RF_selected_hypotheses={m:sum(r['source_method']==m for r in positions if r['method']=='RF_orbit_selection' and r['arm']=='c0') for m in ('baseline',)+METHODS[1:]},
        measurements=measurements, qualification=qualifiers, points=sum(r['points'] for r in measurements),
        curves=len(radio), all_twenty_reported=True, reference_only_used_for_evaluation=True,
        full_DS23_413_and_new_locations_not_validated=True, target_met_on_full_DS23=False))
    figures(cases, positions, radio, measurements, gates)
    write(OUT / 'validation.json', dict(all20_measurements_and_60_position_trials_complete=True,
        exact_sealed_observation_ID_coverage_and_source_hashes_verified=True,
        matched_c_data_priors_and_budgets=True, original_points_not_removed=True,
        original_latest_catalogue_epoch_and_collection_receipts_are_causal=True,
        no_GPS_in_measurement_or_inference=True, raw_IQ_not_in_evidence_archive=True,
        owned_tests_observed_passed=read(OUT / 'test_results.json')['passed'],
        source_sha256=sha(Path(__file__))))
    table = ['| Fixed policy | c0 mean / median, km | Fitted-c mean / median, km | Paired-valid scans |',
             '|---|---:|---:|---:|']
    for method in POLICIES:
        a, b = summary[method]['c0'], summary[method]['fitted_c']
        count = (20 if method=='baseline' else
                 sum(r['source_method']!='baseline' for r in positions if r['method']==method and r['arm']=='c0')
                 if method=='RF_orbit_selection' else counts[method])
        table.append(f"| {LABELS[method]} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} | {count} / 20 |")
    body = '''# DS23: precise RX2 measurements across both recording formats

This study remeasures every point in every originally seeded curved RX2 graph
track in the original twenty development scans. It tests whether cleaner radio
measurements improve position, keeping the existing satellite hypotheses fixed.
It is not a new full association pipeline or validation on all 413 recordings.
The 0.5 km full-DS23 mean-and-median goal remains unproven.

TABLE

Every failed paired trial falls back to the original pair, with its raw outcome
preserved. No scan is dropped and no extra point is trimmed to rescue a fit.
The policies are fixed rules, not the geographically best variant per scan.
Passing counts refer to new trials; the RF-selected policy uses ten valid
new trials and ten incumbent fallbacks. It selects three orbit modes on six
scans and five on four. All final policy results remain in the denominator.

Radio measurements improve substantially: median fixed-degree curve RMS drops
from 78.07 to 22.18 Hz. Of 11,167 probes, 10,581 receive valid refinements and
586 retain archived CFO/noise at a boundary. This does not deliver a general
position improvement. Local noise barely lowers c0 mean while worsening its
median; fitted-c mean is essentially unchanged and its median worsens. Adding
physical directions or choosing them by RF objective does not resolve this.
The published ALGO01 default remains unchanged.

![Position errors](position_by_scan.png)
![Raw trials and accepted policies](raw_trial_accuracy.png)

## Measurement and controls

The sealed selection is 322 original curves and 11,167 physical probes, including
masked points of seeded curves. The initial position comparison keeps the exact
original calibration mask: measuring a masked curve does not silently restore it.
Canonical IDs, satellite labels and integer alias lifts remain unchanged. The
alias period is 1/(4.4 microseconds), 227272.72727272726 Hz.

The continuous fitter uses the same known pilot, independent complex gain/DC
per frame and three carrier/epoch/code-rate parameters as the reference grid.
It uses analytic variable-projection derivatives, a damped 3x3 Gauss–Newton
solve, and independently rechecks the likelihood through the original scorer.
Bounds are archived carrier ±800 Hz, epoch ±0.75 samples and code rate ±40 ppm;
a common ±600 Hz/100 Hz scout precedes fixed epoch/rate seeds. A boundary or
nonpositive exact-control margin retains the archived value and original noise.
Effective CFO times remain inside the original 20 ms probe. Odd/even frame
fits are retained as a noise diagnostic with their different effective times.
More explained IQ energy is not proof of unbiased CFO.

The first policy changes CFO/time only. The second also uses radio-only local
scatter: sliding windows of up to 16 points, degree 0–3 complexity selection,
median scatter, a 5 Hz floor and the timing-adjusted odd/even proxy floor.
The plotted before/after polynomial RMS separately freezes a degree 0-4 chosen
from archived CFO with a 150 Hz complexity score, retaining every curve point.
That whole-curve diagnostic is distinct from the local measurement-noise proxy.
Only successful refined points receive the new uncertainty; fallback points
retain their original uncertainty. These are estimated noise proxies, not
externally calibrated error bars. Complete radio curves learn them; there is
no claim of blind raw-data validation.

The third policy adds the two missing eccentricity-vector directions to the
original three physical orbit coordinates, shared per supported satellite.
Their scales come from latest/previous causal TLE disagreement transported to
the latest epoch, with the existing 1e-5 to 5e-4 bounds. Existing physical
priors are unchanged. This generic follow-up was motivated by structured
residuals revealed by the initial precise measurements. It is reported for all
twenty scans, with no GPS-selected use of extra freedom.

One additional policy selects between the local-noise three/five-mode trials
by the normalized c0 RF objective, requiring gates to pass in both arms.
Both candidates have the same CFOs, times, noise, points and other priors.
The selected design applies to both c arms; if neither passes, retain the
incumbent pair. This is distinct from choosing a design using geographic error.

All full position trials start at zero in the same 25x25 km region centered at
37.906, -122.545. Both c arms have identical observations, nuisance hypothesis
and five phase-reference refreshes with up to 48 position steps each. Causal
catalogues, pre-RF phase forecasts, receiver terms, 300 Hz fragment constants
and receiver-support powers remain fixed. Evaluation uses the supplied
37.849061591561885, -122.48574968092912 coordinate and height 0 m, under the
existing assumption that this reference applies to every sampled recording.
The dataset manifest has no independent per-recording surveyed position.

## Read-port qualification and performance

Fast captures are read through ShortWindowReader. Their virtual tracking
session spans original segment session IDs; dataset-bound manifest hashes,
selected window hashes, compressed payload and index hashes are checked.
Stopping inside a final chunk does not claim its complete decoded chunk hash.
Adaptive captures use the additive NativeAdaptiveReader: schema-14 manifests,
single-visit schema-12 chunks, complete compressed/decoded digests and counters.
Chunk first_visit_index addresses the retained stream, not the original device
visit. The receipt retained_visit_indices maps the ordinal back to device time.
The initial reader rejected a capture with omitted visits; its failed receipts
are retained under qualification_v1. The corrected mapping is covered by an
owned gap fixture and real 10 MHz replay. Payload offsets never become time.

Per-case bounds are 1,200 selected probes, 12,000 fast windows, 8 GiB decoded,
64 MiB per adaptive chunk and 900 seconds. Two read/fit workers use existing
recordings only. The read subprocess has read authorization; its non-root
orchestrator owns stdout results. No recording, tracking contract or QNAP
path is changed. No new RF is collected and no IQ payload is published.

The earlier sealed 96-probe 2.5 MHz benchmark gives 15.004 s reference versus
4.937 s continuous core fitting (3.04x), maximum carrier difference 1.249 Hz,
and no likelihood regression below 1e-6. Three-start and initial one-start
versions are retained rather than removed. The final estimator also passes
synthetic 10 MHz tests, including both edges and high signed carriers.
The 96-probe panel was reused for implementation optimization, so it is a
development benchmark, not untouched accuracy validation.
The separate real qualification panel contains 42 probes: fast 2.5 MHz,
adaptive 2.5 MHz and adaptive 10 MHz. See qualification.csv for rate-specific
runtime, likelihood differences and boundary counts. The reference qualification
timings exclude the common scout while continuous core timings include it;
the 96-probe benchmark is the matched timing comparison. These are core fitter
timings, not embedded-device or full-pipeline benchmarks.

Scoring at archived final CFO does not reproduce every archived GLRT score,
as in the earlier bounded pilot study: the acquired CFO is not persisted.
Exact-replay exceptions remain in qualification.csv and are not used to select
points. The independent local likelihood does not require those archived
normalizations to match. This does not certify capture-binary provenance.

![Radio scatter and boundaries](radio_precision.png)

## Residual acceptance and interpretation

Pointwise-noise development gates test mean, trend, quadratic structure,
steps and lag-one correlation under the proposed measurement uncertainty.
The same thresholds, alias/elevation/RMS/bias bounds and independent-owner
requirements apply in both c arms. Original legacy gate results are retained
alongside these explicit development gates; they are not silently called
production ALGO01 acceptance. Losing an owner can reject another fragment
even when that fragment's own residual screen passes.

![Residual-gate failures](gate_failures.png)

A lower polynomial RMS, tighter conditional information or better full-data
frequency objective does not establish better position. Every raw regression
and gate failure remains visible. A more precise receiver may expose orbit,
calibration or identity mismatch that the old noise floor hid. Frozen identities
make this a controlled measurement experiment, not proof that those identities
remain optimal after the change. Do not promote any variant from these
development cases alone. Fresh causal identity competition and independent
predictive checks are required under any materially changed measurement model.
The largest final phase-reference discrepancy is 65.4 ms in a failed scan-74
five-mode trial; among passing trials it is 1.204 ms. These are reported in
position_by_scan.csv rather than declaring every five-round fit converged.

## Fresh identity and frame-phase diagnostics

Two diagnostic cases recheck the family most affected by the RX2 measurement
change, ranked by summed active squared CFO changes divided by original radio
variance. Inference does not use GPS to choose that family. Scan 217 is the
ongoing failure investigation; scan 321 is an observed geographic regression,
so these cases are not an unbiased validation sample. Every causal candidate
is screened at the new endpoint, regional center and four clipped +/-2 km
anchors. Screening shares one phase across the family's fragments, with their
300 Hz independent constants and pointwise noise. Its Gaussian phase proxy
omits physical orbit modes; four alternate finalists receive exact paired
five-round/48-step fits with all five physical directions. Mergers and changes
to other families are excluded, so this is not global reassociation.

All eight alternate finalists fail paired gates. The incumbent labels remain
57879 on scan 217 and 59616 on scan 321 under this bounded RF decision rule.
Identity trials, failed gates and geographically better losers are preserved
in identity_trials.csv and the lossless archive. Passing the incumbent does
not establish its identity, nor exclude a more coordinated reassignment.

On the separate sealed 96-probe panel, fit a common frame phase/frequency and
measure energy-weighted phase coherence while allowing frame amplitudes to
differ. Search one 750 Hz frame-rate interval; the integer frame-rate alias
remains unresolved. Median coherence is 0.475, versus 0.313 for fixed-seed
random-phase surrogates with matched amplitudes/energy. Only two probes exceed
0.9. RX1/RX2 median residual phase RMS is 0.927/0.795 rad. This does not qualify
a universally coherent carrier model; no coherent CFO is applied. Some probes
may support a separate future phase-continuity test. Surrogates are diagnostics,
not independent measurements or a calibrated existence probability. The first
common-amplitude version is preserved under phase_coherence_v1.

![Frame-phase continuity test](frame_phase_coherence.png)

## Evidence and reproduction

Run tools/remeasure_ds23_rx2_cohort.py --stage prepare once to seal selection.
Run tools/run_ds23_rx2_measurement_cohort.py --stage qualify and then --stage
measure. The only privileged stage reads declared existing recording members;
stdout files are owned by the unprivileged runner. Run
tools/run_ds23_rx2_position_cohort.py on ready cases, then this reporter.
Use the repository venv with PYTHONPATH=src:tools and BLAS/OMP threads one.
Position_v1 preserves the original two-policy pilots; the final comparison
reports all three policies on all twenty scans. A null replay exactly reproduces
the prior endpoint and ELBO for scan 7 under both c arms.

[Summary](summary.json) · [Measurement counts](measurement_by_scan.csv) ·
[All positions including failed trials](position_by_scan.csv) ·
[Curve metrics](curve_metrics.csv) · [Gate metrics](gate_metrics.csv) ·
[Qualification](qualification.csv) · [Validation](validation.json) ·
[Fresh identity trials](identity_trials.csv) ·
[Lossless evidence](evidence.tar.xz) · [Evidence hashes](evidence_inventory.json).
Sources overlay the earlier causal-history and dense-measurement reports.
Original checksum-bound recording/catalogue authorities remain prerequisites.
'''.replace('TABLE', '\n'.join(table))
    (OUT / 'README.md').write_text(body)
    package()
    print('\n'.join(table), flush=True)


def figures(cases, positions, radio, measurements, gates):
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True, constrained_layout=True)
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for method in POLICIES:
            ax.plot(range(20), [next(r['error_km'] for r in positions if r['case']==c and r['method']==method and r['arm']==arm) for c in cases], '.-', label=LABELS[method])
        ax.axhline(.5, c='crimson', ls='--', lw=1)
        ax.set(ylabel='Position error (km)', title=arm)
        ax.grid(alpha=.2)
        ax.legend(fontsize=8, ncol=2)
    axes[-1].set_xticks(range(20), [c.split('-')[-1] for c in cases], rotation=45)
    fig.suptitle('All 20 development scans · failed paired trial falls back · identical c-arm data')
    fig.savefig(OUT / 'position_by_scan.png', dpi=155)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for method in METHODS:
            rows = [r for r in positions if r['method']==method and r['arm']==arm]
            ax.scatter([r['baseline_error_km'] for r in rows], [r['trial_error_km'] for r in rows],
                s=35, alpha=.75, label=LABELS[method])
        ax.plot([0, 5], [0, 5], 'k--', lw=1)
        ax.set(xlabel='Incumbent error (km)', ylabel='Raw trial error (km)', title=arm)
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.suptitle('All raw trials, including gate failures · below diagonal improves')
    fig.savefig(OUT / 'raw_trial_accuracy.png', dpi=155)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    for fs, marker in ((2500000, 'o'), (10000000, '^')):
        rows = [r for r in radio if r['sample_rate_hz']==fs]
        axes[0].scatter([r['original_RMS_hz'] for r in rows], [r['refined_RMS_hz'] for r in rows], s=18,
            marker=marker, alpha=.6, label=f'{fs/1e6:g} MHz')
    axes[0].plot([1, 1000], [1, 1000], 'k--', lw=1)
    axes[0].set(xscale='log', yscale='log', xlabel='Archived polynomial RMS (Hz)',
        ylabel='Refined CFO/time polynomial RMS (Hz)', title='Same degree and every original curve point')
    axes[0].legend()
    axes[1].bar(range(20), [r['boundary_or_control_fallbacks']/r['points']*100 for r in measurements])
    axes[1].set_xticks(range(20), [r['case'].split('-')[-1] for r in measurements], rotation=60)
    axes[1].set(ylabel='Archived-value fallback (%)', title='Boundary/control failures retain observations')
    fig.savefig(OUT / 'radio_precision.png', dpi=155)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(13, 5), constrained_layout=True)
    for k, method in enumerate(METHODS):
        counts = [sum(not r['compatible'] for r in gates if r['case']==c and r['method']==method and r['arm']=='c0') for c in cases]
        ax.bar(np.arange(20)+(k-1)*.25, counts, width=.24, label=LABELS[method])
    ax.set_xticks(range(20), [c.split('-')[-1] for c in cases], rotation=45)
    ax.set(ylabel='Failing fragments at c0', title='Raw development-gate failures; no point trimming')
    ax.legend(fontsize=8)
    fig.savefig(OUT / 'gate_failures.png', dpi=155)
    plt.close(fig)


def package():
    sources = ['tools/'+name+'.py' for name in ('fast_local_pilot_refinement', 'local_pilot_refinement',
        'benchmark_ds23_fast_pilots', 'remeasure_ds23_rx2_cohort', 'run_ds23_rx2_measurement_cohort',
        'probe_ds23_rx2_measurement_position', 'run_ds23_rx2_position_cohort', 'report_ds23_rx2_measurement_cohort')]
    sources += ['tools/'+name+'.py' for name in ('probe_ds23_frame_phase_coherence', 'probe_ds23_rx2_catalogue',
        'ds23_correlated_family_screen', 'probe_native_code_carrier', 'ds23_measurement_noise', 'ds23_refined_noise',
        'probe_ds23_refined_precision', 'probe_ds23_refined_eccentricity', 'probe_ds23_refined_timestamps', 'ds23_heteroscedastic_gates')]
    sources += ['src/leo/storage/native_adaptive_read.py', 'tests/storage/test_native_adaptive_read.py',
        'tests/analysis/test_fast_local_pilot_refinement.py', 'tests/analysis/test_ds23_rx2_measurement_tool.py']
    sources += ['tests/analysis/test_ds23_frame_phase_coherence_tool.py', 'tests/analysis/test_ds23_rx2_catalogue_tool.py']
    sources += ['src/leo/analysis/starlink/'+name+'.py' for name in ('templates', 'fast_scan_scores', 'fast_scan_fractional')]
    inventory = {}
    for name in sources:
        destination = OUT / 'source_snapshot' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        inventory[str(destination.relative_to(OUT))] = sha(destination)
    write(OUT / 'source_inventory.json', inventory)
    paths = [p for p in OUT.rglob('*') if p.is_file() and p.suffix in ('.json', '.log', '.incomplete', '.py', '.png')
             and p.name not in ('evidence_inventory.json', 'source_inventory.json') and 'source_snapshot' not in p.parts]
    paths += [p for p in FAST.rglob('*') if p.is_file()]
    with tarfile.open(OUT / 'evidence.tar.xz', 'w:xz', preset=3) as archive:
        for path in sorted(paths):
            archive.add(path, arcname=str(path.relative_to(ROOT)))
    write(OUT / 'evidence_inventory.json', {str(p.relative_to(ROOT)):dict(sha256=sha(p), bytes=p.stat().st_size) for p in paths})


if __name__ == '__main__':
    run()
