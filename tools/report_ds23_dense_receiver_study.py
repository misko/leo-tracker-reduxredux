"""Report completed dense-RX2, joint-identity and causal-shape controls."""

import csv
import itertools
import re
import shutil
import tarfile
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from audit_ds23_learned_residuals import nearest_pairs
from ds23_heteroscedastic_gates import noise_screen
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from probe_ds23_refined_curve_position import proposed_delta
from report_algo01_ds23_sample import position_error
from run_algo01_ds23_sample import ROOT, read, write, sha

CASE = 'DS23-0202'
OUT = ROOT / 'reports/2026_10_19_ds23_dense_rx2_and_causal_shape'
DENSE = ROOT / 'reports/2026_10_19_ds23_receiver_remeasurement'
JOINT = ROOT / 'reports/2026_10_19_ds23_refined_joint_search'
FORECAST = ROOT / 'reports/2026_10_19_ds23_causal_shape_forecast'
SHAPE = ROOT / 'reports/2026_10_19_ds23_causal_shape_distribution'


def csv_file(name, rows):
    with (OUT / name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def save(fig, name):
    fig.savefig(OUT / name, dpi=165)
    plt.close(fig)


def rx_band(track):
    return int(re.search(r'-RX(\d+)-', track['track'])[1]), int(int(re.search(r'-CH(\d+)-', track['track'])[1]) > 4)


def residual_summary(stages):
    groups, pairs, correlations = [], [], []
    for stage, record in stages:
        for arm, fit in record['arms'].items():
            tracks = fit['tracks']
            for rx, band in itertools.product((1, 2), (0, 1)):
                selected = [t for t in tracks if rx_band(t) == (rx, band)]
                if not selected:
                    continue
                residual = np.concatenate([t['conditional_residual_hz'] for t in selected])
                sigma = np.concatenate([t['sigma_hz'] for t in selected])
                groups.append(dict(stage=stage, arm=arm, receiver=rx, band=band,
                    points=len(residual), curves=len(selected), RMS_hz=float(np.sqrt(np.mean(residual**2))),
                    standardized_RMS=float(np.sqrt(np.mean((residual / sigma)**2)))))
            for a, b in itertools.combinations(tracks, 2):
                ia, ib = nearest_pairs(a['time_s'], b['time_s'])
                if len(ia) < 6:
                    continue
                aa = np.asarray(a['conditional_residual_hz'])[ia]
                bb = np.asarray(b['conditional_residual_hz'])[ib]
                if min(np.std(aa), np.std(bb)) <= 0:
                    continue
                ra, ba = rx_band(a)
                rb, bb_band = rx_band(b)
                pairs.append(dict(stage=stage, arm=arm, left=a['track'], right=b['track'], pairs=len(ia),
                    same_receiver=ra == rb, same_band=ba == bb_band, same_family=a['norad'] == b['norad'],
                    correlation=float(np.corrcoef(aa, bb)[0, 1])))
            for rx, band, family in itertools.product((True, False), repeat=3):
                selected = [r for r in pairs if r['stage'] == stage and r['arm'] == arm and
                    (r['same_receiver'], r['same_band'], r['same_family']) == (rx, band, family)]
                correlations.append(dict(stage=stage, arm=arm, same_receiver=rx, same_band=band,
                    same_family=family, track_pairs=len(selected), median_correlation=
                    float(np.median([r['correlation'] for r in selected])) if selected else None))
    csv_file('receiver_band.csv', groups)
    csv_file('matched_residual_pairs.csv', pairs)
    csv_file('residual_correlations.csv', correlations)
    return groups, correlations


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    dense = read(DENSE / (CASE + '_broad_local_position.json'))
    narrow = read(DENSE / (CASE + '_local_position.json'))
    audited = read(DENSE / (CASE + '_heteroscedastic_gates.json'))
    narrow_audit = read(DENSE / (CASE + '_narrow_heteroscedastic_gates.json'))
    joint = read(JOINT / (CASE + '.json'))
    proposals = [read(p) for p in sorted(JOINT.glob(CASE + '_proposal_*.json'))]
    plan = read(DENSE / (CASE + '_plan.json'))
    raw = read(DENSE / (CASE + '_broad_refined.json'))
    forecast = read(FORECAST / (CASE + '.json'))
    shape = read(SHAPE / (CASE + '.json'))
    position_rows, catalogue_rows = [], []
    comparisons = [('Sparse refinement baseline', dense['baseline']['arms'], True, None)]
    old = read(DENSE / (CASE + '_position.json'))
    for name, r in old['results'].items():
        comparisons.append((name, r['arms'], r.get('legacy_paired_valid', r.get('paired_valid')), None))
    for suffix, document, audit in [('Narrow', narrow, narrow_audit), ('Broad', dense, audited)]:
        for name, r in document['results'].items():
            comparisons.append((suffix + ': ' + name, r['arms'], r['legacy_paired_valid'], audit['results'][name]['paired_valid']))
    for name, arms, legacy, corrected in comparisons:
        for arm, fit in arms.items():
            position_rows.append(dict(method=name, arm=arm, position_error_km=position_error(fit['endpoint_latlon']),
                RF_loss=fit['negative_twice_elbo'], RMS_hz=fit['RMS_hz'], points=fit['active_points'],
                legacy_gates=legacy, uncertainty_consistent_gates=corrected))
    for mode in ('local_noise', 'local_noise_causal_shape'):
        document = read(DENSE / (CASE + '_' + mode + '_catalogue.json'))
        best = document['chosen']['arms']['c0']['negative_twice_elbo']
        assert document['chosen']['proposal']['norad'] == 67335
        for trial in document['trials']:
            for arm, fit in trial['arms'].items():
                catalogue_rows.append(dict(mode=mode, norad=trial['proposal']['norad'], arm=arm,
                    paired_valid=trial['paired_valid'], RF_loss=fit['negative_twice_elbo'],
                    loss_above_c0_winner=fit['negative_twice_elbo'] - best,
                    position_error_km=position_error(fit['endpoint_latlon'])))
    csv_file('position_comparison.csv', position_rows)
    csv_file('dense_identity_comparison.csv', catalogue_rows)
    groups, correlations = residual_summary([('Sparse', dense['baseline'])] + list(dense['results'].items()))
    rng = np.random.default_rng(80)
    times = np.arange(50.)
    sigma = np.r_[np.full(5, 150.), np.full(45, 10.)]
    residual = rng.normal(size=(400, 50)) * sigma
    legacy = batch_noise_screen(residual, times)
    corrected = [noise_screen(r, times, sigma) for r in residual]
    simulation = dict(seed=80, trials=400, sigma_hz=sigma,
        legacy_false_rejection=float(np.mean(~legacy['noise_screen_pass'])),
        uncertainty_consistent_false_rejection=float(np.mean([not r['noise_screen_pass'] for r in corrected])))
    write(OUT / 'gate_simulation.json', simulation)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    cheap_min = min(r['negative_twice_elbo'] for r in proposals)
    for r in proposals:
        axes[0].scatter(len(r['operation']['families']), r['negative_twice_elbo'] - cheap_min, s=20, color='tab:blue', alpha=.65)
    baseline = joint['baseline']['arms']['c0']['negative_twice_elbo']
    for r in joint['trials']:
        p = r['proposal']
        axes[1].scatter(len(p['operation']['families']), r['arms']['c0']['negative_twice_elbo'] - baseline,
            marker='o' if r['paired_valid'] else 'x', s=55, color='tab:blue' if r['paired_valid'] else 'crimson')
        axes[1].annotate(str(p['number']), (len(p['operation']['families']), r['arms']['c0']['negative_twice_elbo'] - baseline), fontsize=8)
    axes[0].set(title='63 cheap proposals: 2 rounds × 12 steps', ylabel='c=0 RF loss above cheap minimum')
    axes[1].set(title='Six full finalists: 5 rounds × 48 steps', ylabel='c=0 RF loss above incumbent')
    for ax in axes:
        ax.set(xlabel='Simultaneously replaced satellite families', xticks=[1, 2, 3, 4])
        ax.axhline(0, color='k', lw=.5)
        ax.grid(alpha=.2)
    fig.suptitle('Earlier four-curve precision data · no accepted RF improvement · circles pass both arms')
    save(fig, 'joint_search.png')

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), constrained_layout=True)
    training = forecast['selection']['training_candidates']
    axes[0].plot([r['beta'] for r in training], [r['loss'] for r in training], '.-')
    axes[0].axvline(0, color='k', lw=.7)
    axes[0].set(title='Signed shape forecast: choose zero', xlabel='Forecast multiplier β', ylabel='Training robust shape loss')
    candidates = shape['selection']['candidates']
    axes[1].bar(range(4), [r['validation_nll'] / shape['selection']['validation_count'] for r in candidates])
    axes[1].set_xticks(range(4), [r['model'].replace('_', '\n') for r in candidates], fontsize=8)
    axes[1].set(title='Later pre-RF publication validation', ylabel='Mean −2 log density (lower is better)')
    axes[2].bar(range(5), np.sqrt(np.diag(shape['selection']['covariance'])))
    axes[2].axhline(1, color='k', lw=.6)
    axes[2].set_xticks(range(5), ['Mean\nmotion', 'Inclination', 'RAAN', 'e cos ω', 'e sin ω'], fontsize=8)
    axes[2].set(title='Training-selected Student diagonal prior', ylabel='Scale relative to original physical prior')
    for ax in axes:
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('6,256 causal historical transitions · no RF/GPS selection · later TLE is a proxy, not orbit truth')
    save(fig, 'causal_shape_qualification.png')

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), constrained_layout=True)
    rr = [r for r in position_rows if r['arm'] == 'c0']
    display = {
        'Sparse refinement baseline': 'Earlier sparse refinement',
        'new_values_old_noise': 'Dense CFO; old noise',
        'new_values_predictive_noise': 'Dense CFO; global predictive noise *',
        'new_values_causal_shape_prior': 'Same + causal shape prior *',
        'Narrow: local_noise': 'Dense CFO; local RF noise',
        'Narrow: local_noise_causal_shape': 'Same + causal shape prior',
        'Broad: local_noise': 'Broader carrier search; local RF noise',
        'Broad: local_noise_causal_shape': 'Same + causal shape prior',
    }
    axes[0].barh(range(len(rr)), [r['position_error_km'] for r in rr],
        color=['tab:blue' if r['legacy_gates'] or r['uncertainty_consistent_gates'] else '0.65' for r in rr])
    axes[0].set_yticks(range(len(rr)), [display[r['method']] for r in rr], fontsize=8)
    axes[0].invert_yaxis()
    axes[0].axvline(.5, color='crimson', ls='--', lw=.7)
    axes[0].set(xlabel='Position error c=0 (km)\n* Gray: legacy failed; revised gates not replayed',
        title='One development scan · measurement/prior controls')
    for k, mode in enumerate(('local_noise', 'local_noise_causal_shape')):
        for r in catalogue_rows:
            if r['mode'] != mode or r['arm'] != 'c0':
                continue
            axes[1].scatter(r['position_error_km'], r['loss_above_c0_winner'], color=['tab:blue', 'tab:orange'][k], marker='o' if r['paired_valid'] else 'x')
            axes[1].annotate(str(r['norad']), (r['position_error_km'], r['loss_above_c0_winner']), fontsize=7, xytext=(3, 3), textcoords='offset points')
        axes[1].plot([], [], '.', color=['tab:blue', 'tab:orange'][k], label=['Gaussian physical prior', 'Causal Student physical prior'][k])
    axes[1].set(xlabel='Position error c=0 (km)', ylabel='RF loss above same-prior winner', title='Six inherited RF shortlist identities retested')
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=.2)
    save(fig, 'position_and_identity.png')

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    stages = ['Sparse', 'local_noise', 'local_noise_causal_shape']
    labels = ['Sparse', 'Dense Gaussian', 'Dense causal Student']
    for j, stage in enumerate(stages):
        rr = [r for r in groups if r['stage'] == stage and r['arm'] == 'c0']
        axes[0].bar(np.arange(4) + (j - 1) * .25, [r['RMS_hz'] for r in rr], width=.24, label=labels[j])
    axes[0].set_xticks(range(4), ['RX1 low', 'RX1 high', 'RX2 low', 'RX2 high'])
    axes[0].set(ylabel='Conditional residual RMS (Hz)', title='Same 2,646 calibration observations')
    axes[0].legend(fontsize=8)
    cells = [(rx, band, family) for rx, band, family in itertools.product((True, False), repeat=3)]
    matrix = np.full((3, 8), np.nan)
    for row, stage in enumerate(stages):
        for col, (rx, band, family) in enumerate(cells):
            r = next(r for r in correlations if r['stage'] == stage and r['arm'] == 'c0' and
                (r['same_receiver'], r['same_band'], r['same_family']) == (rx, band, family))
            if r['track_pairs']:
                matrix[row, col] = r['median_correlation']
            axes[1].text(col, row, '—' if not r['track_pairs'] else f"{r['median_correlation']:+.2f}\n{r['track_pairs']}", ha='center', va='center', fontsize=7)
    im = axes[1].imshow(matrix, vmin=-.7, vmax=.7, cmap='coolwarm', aspect='auto')
    axes[1].set_yticks(range(3), labels, fontsize=8)
    axes[1].set_xticks(range(8), ['\n'.join('Same' if v else 'Diff' for v in cell) for cell in cells], fontsize=7)
    axes[1].set(xlabel='Receiver / band / family', title='Matched residual correlation; number of track pairs')
    fig.colorbar(im, ax=axes[1], shrink=.7)
    fig.suptitle('Scan 202 · conditioned residuals are descriptive; overlapping pairs are dependent')
    save(fig, 'dense_residual_transfer.png')

    target = next(r for r in dense['radio_noise_receipts'] if '-RX2-CH2-T004-' in r['track'])
    track = next(t for t in raw['panel_metadata']['tracks'] if t['key'] == target['track'])
    lookup = {r['point']['observation_id']: r for r in raw['rows']}
    t = np.array(track['times'])
    y = np.array(track['values']) + np.array([proposed_delta(lookup[o], 'joint_CFO_epoch_rate')[0] for o in track['observation_ids']])
    z = (t - t.mean()) / np.ptp(t)
    design = np.vander(z, 5, increasing=True)
    full = design @ np.linalg.lstsq(design, y, rcond=None)[0]
    # Display the archived active-prefix intersection only; never feed it to noise learning.
    active_track = next(r for r in dense['results']['local_noise']['arms']['c0']['tracks'] if r['track'] == track['key'])
    active = t < max(active_track['time_s']) + .02
    prefix = design @ np.linalg.lstsq(design[active], y[active], rcond=None)[0]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    axes[0].plot(t, y - prefix, 'o', ms=4, label='All original 21 CFOs')
    axes[0].scatter(t[~active], (y - prefix)[~active], s=65, facecolors='none', edgecolors='crimson', label='Already masked late points')
    axes[0].plot(t, full - prefix, '.-', label='Whole-curve quartic')
    axes[0].axhline(0, color='k', lw=.6)
    axes[0].set(xlabel='Scan time (s)', ylabel='CFO − active-prefix quartic (Hz)', title='RX2 CH2 T004: global leverage is not noise')
    axes[0].legend(fontsize=7)
    axes[1].bar(range(3), [target['old_PRESS_selected_sigma_hz'], target['studentized_measurement_scatter_hz'], target['selected_sigma_hz']])
    axes[1].set_xticks(range(3), ['Global PRESS', 'Studentized\nglobal', 'Local RF\nscatter'])
    axes[1].set(yscale='log', ylabel='Estimated sigma (Hz)', title='Local variance uses every reliable point')
    axes[2].bar(['Legacy', 'Pointwise sigma'], [simulation['legacy_false_rejection'] * 100, simulation['uncertainty_consistent_false_rejection'] * 100])
    axes[2].set(ylabel='False rejection (%)', title='400 zero-mean mixed-noise synthetic curves')
    fig.suptitle('Noise learning and structure gates changed explicitly · no original active point removed')
    save(fig, 'noise_and_gate_controls.png')
    write(OUT / 'summary.json', dict(case=CASE, positions=position_rows, identities=catalogue_rows,
        receiver_band=groups, residual_correlations=correlations, gate_simulation=simulation,
        historical_shape_selection=shape['selection'], signed_forecast_selection=forecast['selection'],
        joint_proposals=len(proposals), joint_finalists=len(joint['trials']), joint_accepted=joint['chosen'] is not None,
        RX2_original_curves=len(plan['track_keys']), RX2_original_points=plan['points'], RX2_active_points=plan['active_points'],
        raw_windows_read=raw['panel_metadata']['raw_windows_read'], all_calibration_points=2646,
        broadened_CFO_changes=sum(r['broad_carrier_check']['accepted'] for r in raw['rows']),
        all_19_changes_previously_failed_local_quality=True, tail_noise_receipt=target,
        new_full_DS23_or_20_scan_result=False, GPS_used_only_for_reporting=True, target_met=False,
        report_source_sha256=sha(Path(__file__))))
    for document in (audited, narrow_audit):
        assert all(r['paired_valid'] for r in document['results'].values())
        assert all(abs(a['score_replay_difference']) < 1e-5 for r in document['results'].values() for a in r['arms'].values())
        assert all(a['fit']['active_points'] == 2646 for r in document['results'].values() for a in r['arms'].values())
    assert len(proposals) == 63 and joint['chosen'] is None
    assert plan['points'] == 1050 and plan['active_points'] == 1043 and len(plan['track_keys']) == 30
    assert len(raw['rows']) == len({r['point']['observation_id'] for r in raw['rows']}) == 1050
    changed = [r for r in raw['rows'] if r['broad_carrier_check']['accepted']]
    assert len(changed) == 19 and all(not r['broad_carrier_check']['old_reliable'] for r in changed)
    assert simulation['uncertainty_consistent_false_rejection'] < .05
    package()
    write(OUT / 'validation.json', dict(all_assertions_passed=True, no_IQ_published=True,
        original_2646_active_points_preserved_in_both_arms=True, exact_saved_ELBO_replay_below_1e_5=True,
        corrected_gates_pass_both_dense_and_narrow_pairs=True, RF_shortlist_winner_67335_both_priors=True,
        source_test_command='PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest -q '
            'tests/analysis/test_local_pilot_refinement_tool.py tests/analysis/test_ds23_refined_joint_search.py '
            'tests/analysis/test_ds23_causal_shape_forecast.py tests/analysis/test_ds23_causal_shape_distribution.py '
            'tests/analysis/test_ds23_receiver_remeasurement.py tests/analysis/test_ds23_heteroscedastic_gates.py',
        owned_tests_observed_passed=21, observed_test_seconds=3.25, target_met=False))
    print('Report built:', OUT, 'gate false rejection', simulation['legacy_false_rejection'], simulation['uncertainty_consistent_false_rejection'], flush=True)


def package():
    evidence = []
    for folder in (JOINT, FORECAST, SHAPE, DENSE):
        evidence += [p for p in sorted(folder.glob('*.json')) if 'partial' not in p.name]
    with tarfile.open(OUT / 'evidence.tar.gz', 'w:gz') as archive:
        for path in evidence:
            archive.add(path, arcname=str(path.relative_to(ROOT)))
    write(OUT / 'evidence_inventory.json', {str(p.relative_to(ROOT)): dict(sha256=sha(p), bytes=p.stat().st_size) for p in evidence})
    sources = ['tools/' + name + '.py' for name in (
        'probe_ds23_refined_joint_search', 'ds23_causal_shape_forecast', 'ds23_causal_shape_distribution',
        'probe_ds23_history_shape_prior', 'local_pilot_refinement', 'refine_ds23_receiver_panel',
        'probe_ds23_receiver_positions', 'ds23_measurement_noise', 'broaden_ds23_receiver_cfo',
        'probe_ds23_local_noise_positions', 'ds23_heteroscedastic_gates', 'audit_ds23_heteroscedastic_gates',
        'probe_ds23_dense_receiver_catalogue', 'report_ds23_dense_receiver_study')]
    sources += ['tests/analysis/' + name + '.py' for name in (
        'test_local_pilot_refinement_tool', 'test_ds23_refined_joint_search', 'test_ds23_causal_shape_forecast',
        'test_ds23_causal_shape_distribution', 'test_ds23_receiver_remeasurement', 'test_ds23_heteroscedastic_gates')]
    inventory = {}
    for name in sources:
        destination = OUT / 'source_snapshot' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
        inventory[str(destination.relative_to(OUT))] = sha(destination)
    for path in sorted((DENSE / 'source_v1').rglob('*.py')):
        destination = OUT / path.relative_to(DENSE)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        inventory[str(destination.relative_to(OUT))] = sha(destination)
    write(OUT / 'source_inventory.json', inventory)


if __name__ == '__main__':
    run()
