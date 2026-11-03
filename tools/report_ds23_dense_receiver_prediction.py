"""Report conditional prediction and the complete fixed-rule twenty-scan control."""

import csv
import shutil
import tarfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from probe_ds23_dense_receiver_prediction import OUT, METHODS
from probe_ds23_rx1_prediction_cohort import OUT as COHORT, qualify
from report_algo01_ds23_sample import position_error, summarize
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, read, write, sha
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis


def csv_file(name, rows):
    with (OUT / name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def save(fig, name):
    fig.savefig(OUT / name, dpi=165)
    plt.close(fig)


def run():
    protocol = read(COHORT / 'protocol.json')
    receipts = read(COHORT / 'execution.json')
    cases = sorted(protocol['cases'])
    assert len(cases) == len(set(cases)) == len(receipts) == 20
    assert {r['case'] for r in receipts} == set(cases) and all(r['code'] == 0 for r in receipts)
    assert all(r['result_sha256'] == sha(COHORT / (r['case'] + '.json')) for r in receipts)
    assert protocol['source_sha256'] == sha(ROOT / 'tools/probe_ds23_rx1_prediction_cohort.py')
    assert protocol['dependency_sha256'] == sha(ROOT / 'tools/probe_ds23_dense_receiver_prediction.py')
    cohort = {case: read(COHORT / (case + '.json')) for case in cases}
    positions, prediction_rows, dense_rows, causal_receipts = [], [], [], []
    for case, document in cohort.items():
        assert document['case'] == case
        assert document['source_sha256'] == protocol['source_sha256']
        assert document['dense_probe_source_sha256'] == protocol['dependency_sha256']
        assert document['learned_input_sha256'] == sha(ROOT / 'reports/2026_10_18_ds23_history_calibrated_phase' / (case + '.json'))
        assert document['no_GPS_used'] is True
        path = SOURCE / 'causal_prior' / case / 'receipt.json'
        receipt = read(path)
        assert not receipt['reference_position_used'] and receipt['search_box_width_km'] == 25
        assert max(receipt['latest_max_epoch_utc_ns'], receipt['latest_max_collection_utc_ns']) < receipt['cutoff_utc_ns']
        causal_receipts.append(dict(case=case, original_receipt_sha256=sha(path),
            cutoff_utc_ns=receipt['cutoff_utc_ns'], latest_max_epoch_utc_ns=receipt['latest_max_epoch_utc_ns'],
            latest_max_collection_utc_ns=receipt['latest_max_collection_utc_ns'],
            latest_tle_sha256=receipt['latest_tle_sha256'], previous_tle_sha256=receipt['previous_tle_sha256'],
            inherited_bank_sha256=receipt['bank_sha256'], candidate_count=receipt['candidate_count'],
            search_center=receipt['search_center'], reference_position_used=False))
        base, trial = document['baseline_arms'], document['trial_arms']
        selection = qualify(document['records']['baseline'], document['records']['fast_rx1'], document['paired_valid'],
            trial['c0']['negative_twice_elbo'] - base['c0']['negative_twice_elbo'])
        assert selection == document['selection']
        for method in ('baseline', 'fast_rx1'):
            for r in document['records'][method]:
                prediction_rows.append(dict(case=case, method=method, receiver=r['receiver'], norad=r['norad'],
                    train_points=r['train_points'], test_points=r['test_points'],
                    predictive_loss=r['prediction']['negative_twice_log_density'], RMS_hz=r['prediction']['RMS_hz']))
        for arm in ('c0', 'fitted_c'):
            assert trial[arm]['active_points'] == base[arm]['active_points'] == sum(document['original_mask'])
            assert all(t['compatible'] for t in document['selected_arms'][arm]['gates']['tracks'])
            gated = trial if document['paired_valid'] else base
            for policy, pair in [('Incumbent', base), ('RX1, gates only', gated), ('RX1, prediction qualified', document['selected_arms'])]:
                positions.append(dict(case=case, arm=arm, policy=policy,
                    error_km=position_error(pair[arm]['endpoint_latlon']), RMS_hz=pair[arm]['RMS_hz'],
                    RF_loss=pair[arm]['negative_twice_elbo'], calibration_points=pair[arm]['active_points'],
                    raw_trial_error_km=position_error(trial[arm]['endpoint_latlon']),
                    raw_trial_valid=document['paired_valid'], prediction_qualified=selection['qualified']))
    summaries = {}
    for policy in ('Incumbent', 'RX1, gates only', 'RX1, prediction qualified'):
        summaries[policy] = {arm: summarize([r['error_km'] for r in positions if r['policy'] == policy and r['arm'] == arm]) for arm in ('c0', 'fitted_c')}
    csv_file('cohort_position.csv', positions)
    write(OUT / 'causal_input_receipts.json', dict(cases=causal_receipts,
        rechecked_original_causal_receipt_cutoffs=True, full_bank_not_rehashed_by_this_reporting_stage=True))
    csv_file('cohort_prediction_folds.csv', prediction_rows)
    dense = {method: read(OUT / ('DS23-0202_' + method + '.json')) for method in METHODS}
    baseline = dense['baseline']
    for method, document in dense.items():
        selection = qualify(baseline['records'], document['records'], document['paired_valid'],
            document['arms']['c0']['negative_twice_elbo'] - baseline['arms']['c0']['negative_twice_elbo'])
        assert document['source_sha256'] == protocol['dependency_sha256']
        for arm, r in document['arms'].items():
            dense_rows.append(dict(method=method, arm=arm, error_km=position_error(r['endpoint_latlon']),
                RF_loss=r['negative_twice_elbo'], RMS_hz=r['RMS_hz'], paired_valid=document['paired_valid'],
                prediction_qualified=selection['qualified'], gain_RX1=selection['per_receiver_gain']['1'],
                gain_RX2=selection['per_receiver_gain']['2'], active_points=r['active_points']))
    csv_file('dense202_position.csv', dense_rows)
    gains = [{**dict(case=case), **document['selection']} for case, document in cohort.items()]
    write(OUT / 'summary.json', dict(cohort=summaries, dense202=dense_rows, qualification=gains,
        qualified_scans=[c for c, d in cohort.items() if d['selection']['qualified']],
        paired_failed_scans=[c for c, d in cohort.items() if not d['paired_valid']],
        cases=cases, total_prediction_folds=len(prediction_rows),
        target_met=all(summaries['RX1, prediction qualified'][arm][key] <= .5 for arm in ('c0', 'fitted_c') for key in ('mean_km', 'median_km')),
        original20_development_scans_not_untouched_validation=True,
        no_new_full_DS23_cohort_claim=True, report_source_sha256=sha(Path(__file__))))

    fig, axes = plt.subplots(2, 1, figsize=(15, 8), sharex=True, constrained_layout=True)
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for policy, color, marker in [('Incumbent', '0.5', 'o'), ('RX1, gates only', 'tab:orange', 'x'), ('RX1, prediction qualified', 'tab:blue', '.')]:
            rows = [next(r for r in positions if r['case'] == case and r['arm'] == arm and r['policy'] == policy) for case in cases]
            ax.plot(range(20), [r['error_km'] for r in rows], marker=marker, lw=.8, color=color, label=policy)
        ax.axhline(.5, color='crimson', ls='--', lw=.7)
        ax.set(ylabel='Position error (km)', title=arm)
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    axes[-1].set_xticks(range(20), [c.split('-')[1] for c in cases], rotation=90)
    fig.suptitle('Same twenty development scans · fixed RX1 covariance · all original points retained')
    save(fig, 'cohort_position.png')

    fig, axes = plt.subplots(2, 1, figsize=(15, 7), sharex=True, constrained_layout=True)
    for rx, color, offset in [(1, 'tab:blue', -.18), (2, 'tab:orange', .18)]:
        axes[0].bar(np.arange(20) + offset, [cohort[c]['selection'].get('per_receiver_gain', {}).get(str(rx), 0) for c in cases], width=.35, color=color, label=f'Omitted RX{rx}')
    axes[0].set(ylabel='Baseline predictive loss − RX1 variant loss', title='Aggregate across up to three omitted satellite families')
    axes[0].legend(fontsize=8)
    for k, case in enumerate(cases):
        document = cohort[case]
        delta = document['trial_arms']['c0']['negative_twice_elbo'] - document['baseline_arms']['c0']['negative_twice_elbo']
        axes[1].scatter(k, delta, color='tab:blue' if document['selection']['qualified'] else '0.55', marker='o' if document['paired_valid'] else 'x')
    axes[1].set(ylabel='c=0 RF loss change (lower is better)', title='Blue: prediction-qualified; ×: paired gate failure')
    for ax in axes:
        ax.axhline(0, color='k', lw=.6)
        ax.grid(alpha=.2)
    axes[-1].set_xticks(range(20), [c.split('-')[1] for c in cases], rotation=90)
    save(fig, 'cohort_qualification.png')

    display = ['Slow baseline', 'Fast RX1', 'Fast both', 'Fast band half']
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    for k, arm in enumerate(('c0', 'fitted_c')):
        rows = [next(r for r in dense_rows if r['method'] == m and r['arm'] == arm) for m in METHODS]
        axes[0].bar(np.arange(4) + (k-.5)*.3, [r['error_km'] for r in rows], width=.28, label=arm)
    axes[0].set_xticks(range(4), display, rotation=15)
    axes[0].set(ylabel='Position error (km)', title='Dense scan 202 · 2,646 points in every fit')
    axes[0].legend(fontsize=8)
    for k, rx in enumerate((1, 2)):
        rows = [next(r for r in dense_rows if r['method'] == m and r['arm'] == 'c0') for m in METHODS]
        axes[1].bar(np.arange(4) + (k-.5)*.3, [r['gain_RX'+str(rx)] for r in rows], width=.28, label=f'Omitted RX{rx}')
    axes[1].set_xticks(range(4), display, rotation=15)
    axes[1].axhline(0, color='k', lw=.6)
    axes[1].set(ylabel='Aggregate held-vector predictive loss improvement', title='Band-specific addition fails RX2 transfer')
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis='y', alpha=.2)
    save(fig, 'dense202_prediction.png')

    fig, axes = plt.subplots(3, 2, figsize=(14, 9), constrained_layout=True)
    for ax, a, b in zip(axes.flat, baseline['records'], dense['fast_rx1']['records'], strict=True):
        assert (a['receiver'], a['norad']) == (b['receiver'], b['norad'])
        for label, record in [('Baseline', a), ('Fast RX1', b)]:
            prediction = record['prediction']
            order = np.argsort(prediction['time_s'])
            ax.plot(np.array(prediction['time_s'])[order], np.array(prediction['residual_hz'])[order], '.', ms=3, label=label)
        ax.axhline(0, color='k', lw=.6)
        ax.set(title=f"Omit RX{a['receiver']} / satellite {a['norad']}", xlabel='Scan time (s)', ylabel='Predicted CFO residual (Hz)')
        ax.grid(alpha=.2)
        ax.legend(fontsize=7)
    fig.suptitle('Omitted full vectors: no target constant/noise fitted · frozen identities and radio-noise proxies')
    save(fig, 'dense202_omitted_residuals.png')

    t = np.linspace(0, 300, 301)
    bslow = projected_receiver_basis(t)
    bfast = projected_receiver_basis(t, spacing_s=10, width_s=5)
    previous = np.array(baseline['arms']['c0']['state']['smooth'])
    current = np.array(dense['fast_rx1']['arms']['c0']['state']['smooth'])
    fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)
    slow_width = previous.shape[1]
    ax.plot(t, bslow @ previous[0], label='Earlier slow RX1 correction')
    ax.plot(t, bslow @ current[0, :slow_width] + .5*bfast @ current[0, slow_width:], label='Slow + fast RX1 correction')
    ax.plot(t, .5*bfast @ current[0, slow_width:], '--', label='Added fast component')
    ax.set(xlabel='Scan time (s)', ylabel='Receiver smooth correction at 11.5 GHz (Hz)', title='Linear/band drift stays separate; fast basis has no scan-wide affine component')
    ax.grid(alpha=.2)
    ax.legend(fontsize=8)
    save(fig, 'dense202_receiver_correction.png')
    package(cases)
    write(OUT / 'validation.json', dict(all20_completed_with_successful_terminal_receipts=True,
        all_source_dependency_and_baseline_hashes_match=True, all_original_active_point_counts_preserved=True,
        original_causal_catalogue_receipt_cutoffs_rechecked_all20=True,
        selection_recomputed_without_GPS=True, owned_tests_observed_passed=9,
        target_reached_on_all_DS23=False, no_production_or_golden_changes=True))
    print('Cohort summaries', summaries, flush=True)
    print('Qualified', [c for c, d in cohort.items() if d['selection']['qualified']], flush=True)


def package(cases):
    paths = [OUT / ('DS23-0202_' + m + '.json') for m in METHODS]
    paths += [COHORT / (case + '.json') for case in cases] + [COHORT / 'protocol.json', COHORT / 'execution.json']
    with tarfile.open(OUT / 'evidence.tar.gz', 'w:gz') as archive:
        for p in paths:
            archive.add(p, arcname=str(p.relative_to(ROOT)))
    write(OUT / 'evidence_inventory.json', {str(p.relative_to(ROOT)): dict(sha256=sha(p), bytes=p.stat().st_size) for p in paths})
    sources = ['tools/' + n + '.py' for n in ('probe_ds23_dense_receiver_prediction', 'probe_ds23_rx1_prediction_cohort',
        'run_ds23_rx1_prediction_cohort', 'report_ds23_dense_receiver_prediction', 'probe_ds23_receiver_prediction')]
    sources += ['tests/analysis/' + n + '.py' for n in ('test_ds23_dense_receiver_prediction', 'test_ds23_rx1_prediction_cohort', 'test_ds23_receiver_prediction_tool')]
    inventory = {}
    for name in sources:
        path = OUT / 'source_snapshot' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
        inventory[str(path.relative_to(OUT))] = sha(path)
    write(OUT / 'source_inventory.json', inventory)


if __name__ == '__main__':
    run()
