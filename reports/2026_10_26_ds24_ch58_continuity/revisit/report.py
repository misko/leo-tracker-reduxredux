"""Descriptive natural revisit report. Target responses are evaluation only."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import study

HERE = Path(__file__).resolve().parent


def quantiles(values):
    if not values:
        return None
    return dict(zip(['minimum', 'p25', 'median', 'p75', 'maximum'],
                    [float(x) for x in np.quantile(values, [0, .25, .5, .75, 1])]))


def main():
    panel = study.load(HERE / 'panel.json')
    predictions = study.load(HERE / 'predictions.json')
    results = study.load(HERE / 'results.json')
    predicted = {(r['request_id'], r['receiver_id']): r for r in predictions['rows']}
    measured = {(r['request_id'], c['receiver_id']): c for r in results['rows'] for c in r['cells']}
    cells = []
    mode_rows = []
    histories = []
    for slot in panel['slots']:
        for cell in slot['cells']:
            h = cell['header']
            f = predicted[(h['request_id'], h['receiver_id'])]['forecast']
            earlier = sorted(cell['earlier'], key=lambda p: p['valid_start_counter'])
            eligible = [study.donors(p, h['sample_rate_hz']) for p in earlier]
            passes = [bool(c) for c in eligible]
            latest_count = len(eligible[-1]) if eligible else 0
            primary = f['primary_mode']
            evaluation = measured.get((h['request_id'], h['receiver_id']))
            cells.append(dict(**h, donor_visit_count=len(earlier), gatepassing_visit_count=sum(passes),
                latest_donor_gatepass=bool(passes and passes[-1]), at_least_two_gatepassing=sum(passes) >= 2,
                all_three_gatepassing=len(passes) == 3 and all(passes), latest_donor_modes=latest_count,
                complete_modes=sum(m['status'] == 'complete' for m in f['modes']),
                missing_modes=sum(m['status'] == 'missing_earlier_matches' for m in f['modes']),
                ambiguous_modes=sum(m['status'] == 'ambiguous_earlier_matches' for m in f['modes']),
                forecast_available=primary is not None, primary_mode=primary,
                latest_elapsed_s=(h['target_start_counter'] - earlier[-1]['valid_start_counter']) / h['sample_rate_hz']
                    if earlier else None,
                primary_constant_consistent=bool(evaluation and primary is not None and next(
                    (o['variants']['constant']['independent_support_consistent'] for o in evaluation['outcomes']
                     if o['mode_index'] == primary), False)),
                primary_linear_consistent=bool(evaluation and primary is not None and next(
                    (o['variants']['linear']['independent_support_consistent'] for o in evaluation['outcomes']
                     if o['mode_index'] == primary), False)),
                any_constant_consistent=bool(evaluation and any(o['variants']['constant']['independent_support_consistent']
                    for o in evaluation['outcomes'])),
                any_linear_consistent=bool(evaluation and any(o['variants']['linear']['independent_support_consistent']
                    for o in evaluation['outcomes']))))
            for mode_index, mode in enumerate(f['modes']):
                if mode['status'] != 'complete':
                    continue
                period = h['sample_rate_hz'] / 750
                target = cell['target_original']
                original_pass = study.donors(target, h['sample_rate_hz']) if target else []
                for variant in ['constant', 'linear']:
                    p = mode[variant]
                    # Nearest observed target mode is solely a descriptive evaluation;
                    # it never chooses the prediction or a scoring mode.
                    closest = min(original_pass, key=lambda c: abs(study.wrap(study.epoch(c) - p['epoch_samples'], period)) / 64 +
                                  abs(c['fractional_tracking_cfo_hz'] - p['CFO_hz']) / 5000, default=None)
                    outcome = next((o['variants'][variant] for o in evaluation['outcomes'] if o['mode_index'] == mode_index), None) if evaluation else None
                    timing_delta = study.wrap(study.epoch(closest) - p['epoch_samples'], period) if closest else None
                    cfo_delta = closest['fractional_tracking_cfo_hz'] - p['CFO_hz'] if closest else None
                    mode_rows.append(dict(request_id=h['request_id'], case=h['case'], channel=h['channel'],
                        receiver_id=h['receiver_id'], mode_index=mode_index, seed_rank=mode['seed_rank'], variant=variant,
                        horizon_s=mode['horizon_s'], CFO_rate_hz_per_s=mode['CFO_fit']['rate_per_s'],
                        timing_rate_samples_per_s=mode['timing_fit']['rate_per_s'],
                        CFO_half_width_heuristic=mode['CFO_fit']['heuristic_half_width_3scale'],
                        timing_half_width_heuristic=mode['timing_fit']['heuristic_half_width_3scale'],
                        target_original_gatepass_count=len(original_pass),
                        closest_original_rank=closest['candidate_rank'] if closest else None,
                        closest_original_timing_delta_samples=timing_delta, closest_original_CFO_delta_hz=cfo_delta,
                        linear_band_compatible=bool(closest and abs(timing_delta) <= mode['timing_fit']['heuristic_half_width_3scale'] and
                            abs(cfo_delta) <= mode['CFO_fit']['heuristic_half_width_3scale']) if variant == 'linear' else None,
                        both_half_gatepass=outcome['both_pass'] if outcome else False,
                        half_CFO_difference_hz=outcome['CFO_difference_hz'] if outcome else None,
                        support_consistent=outcome['independent_support_consistent'] if outcome else False))
                histories.append(mode)
    funnel_fields = ['latest_donor_gatepass', 'at_least_two_gatepassing', 'all_three_gatepassing', 'forecast_available',
                     'primary_constant_consistent', 'primary_linear_consistent', 'any_constant_consistent', 'any_linear_consistent']
    def funnel(rows):
        return dict(cells=len(rows), **{k: sum(r[k] for r in rows) for k in funnel_fields},
                    complete_modes=sum(r['complete_modes'] for r in rows),
                    missing_modes=sum(r['missing_modes'] for r in rows), ambiguous_modes=sum(r['ambiguous_modes'] for r in rows))
    summary = dict(protocol_sha256=study.sha(HERE / 'protocol.json'), panel_sha256=study.sha(HERE / 'panel.json'),
        predictions_sha256=study.sha(HERE / 'predictions.json'), results_sha256=study.sha(HERE / 'results.json'),
        windows_requested=48, window_statuses=dict(Counter(r['status'] for r in results['rows'])),
        all_opened_windows_original_paired_parity=all(r['status'] == 'complete' and
            all(p['all_passed'] for p in r['parity']['parity'].values()) for r in results['rows']),
        runtime_seconds=results['seconds'], runtime_identity_unchanged=results['runtime_identity_unchanged'],
        overall=funnel(cells), by_channel={str(ch): funnel([r for r in cells if r['channel'] == ch]) for ch in study.CHANNELS},
        by_channel_receiver={f'CH{ch}-RX{rx}': funnel([r for r in cells if r['channel'] == ch and r['receiver_id'] == rx])
                             for ch in study.CHANNELS for rx in [0, 1]},
        donor_elapsed_s=quantiles([r['latest_elapsed_s'] for r in cells if r['latest_elapsed_s'] is not None]),
        eligible_CFO_rate_hz_per_s=quantiles([m['CFO_fit']['rate_per_s'] for m in histories]),
        eligible_timing_rate_samples_per_s=quantiles([m['timing_fit']['rate_per_s'] for m in histories]),
        linear_minus_constant_CFO_hz=quantiles([m['linear']['CFO_hz'] - m['constant']['CFO_hz'] for m in histories]),
        linear_band_original_compatible_modes=sum(r['linear_band_compatible'] for r in mode_rows if r['variant'] == 'linear'),
        original_acquisition_exposed=True, external_natural_signal_truth=False,
        heuristic_uncertainty_not_calibrated=True, paired_targets_share_donors=True,
        direct_position_accuracy_claim=False)
    study.write(HERE / 'summary.json', summary)
    for name, rows in [('cells.csv', cells), ('mode_evaluation.csv', mode_rows)]:
        with (HERE / name).open('x') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    x = np.arange(len(study.CHANNELS))
    fig, ax = plt.subplots(figsize=(9, 4.5), layout='constrained')
    keys = ['latest_donor_gatepass', 'at_least_two_gatepassing', 'all_three_gatepassing', 'forecast_available']
    labels = ['Latest visit has donor', 'At least 2/3 visits', 'All 3 visits', 'Unique compatible history']
    for i, (key, label) in enumerate(zip(keys, labels)):
        ax.bar(x + (i - 1.5) * .19, [summary['by_channel'][str(ch)][key] for ch in study.CHANNELS],
               width=.18, label=label)
    ax.set(xticks=x, xticklabels=[f'CH{ch}' for ch in study.CHANNELS], ylabel='Receiver cells / 16 per channel',
           ylim=(0, 17), title='Natural donor availability: frozen midpoint targets')
    ax.legend(fontsize=8)
    for ext in ['png', 'pdf']:
        fig.savefig(HERE / ('opportunity_funnel.' + ext), dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), layout='constrained')
    linear = [r for r in mode_rows if r['variant'] == 'linear']
    for ax, field, label in [(axes[0], 'CFO_rate_hz_per_s', 'Fitted donor CFO rate (Hz/s)'),
                             (axes[1], 'timing_rate_samples_per_s', 'Fitted donor timing phase rate (samples/s)')]:
        ax.axhline(0, color='.7', lw=1)
        ax.scatter(range(len(linear)), [r[field] for r in linear], c=[r['channel'] for r in linear], cmap='viridis')
        ax.set(xlabel='Complete earlier-only mode (8 modes, 5 receiver cells)', ylabel=label)
    fig.suptitle('Three natural donor visits: compatible-history subset only')
    for ext in ['png', 'pdf']:
        fig.savefig(HERE / ('natural_drift.' + ext), dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), layout='constrained')
    for variant, color in [('constant', 'tab:blue'), ('linear', 'tab:orange')]:
        rows = [r for r in mode_rows if r['variant'] == variant]
        axes[0].scatter(range(len(rows)), [r['half_CFO_difference_hz'] for r in rows], label=variant, c=color)
        axes[1].bar([variant], [sum(r['support_consistent'] for r in rows)], color=color)
    axes[0].axhline(100, c='.4', ls='--', label='100 Hz consistency threshold')
    axes[0].set(xlabel='Complete earlier-only mode', ylabel='Disjoint-half tracking CFO difference (Hz)')
    axes[0].legend(fontsize=8)
    axes[1].set(ylabel='Both margins pass and CFO agrees / 8 modes', ylim=(0, 9))
    fig.suptitle('Natural target support consistency; external identity truth unavailable')
    for ext in ['png', 'pdf']:
        fig.savefig(HERE / ('target_support.' + ext), dpi=180)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
