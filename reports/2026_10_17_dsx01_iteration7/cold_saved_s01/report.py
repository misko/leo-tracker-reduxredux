"""Render all fixed cohorts and identity/timing histograms from saved replay."""
import csv
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def csv_rows(path, rows):
    with path.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def main():
    result = json.loads((HERE/'results.json').read_text())
    comparisons = result['comparisons']
    rows, identities, timings = [], [], []
    for arm, scopes in comparisons.items():
        for scope, record in scopes.items():
            rows.append(dict(arm=arm, scope=scope, **{k:v for k, v in record.items() if not k.endswith('_histogram')}))
            for model in ['original', 'saved']:
                identities.extend(dict(arm=arm, scope=scope, endpoint=model, satellite_number=int(number), count=count)
                    for number, count in record[model+'_identity_histogram'].items())
    for endpoint, provenance in result['provenance'].items():
        fitted = provenance['fitted'];common = fitted['common_timing_s']
        for number, value in fitted['total_timing_s'].items():
            timings.append(dict(endpoint=endpoint, number=int(number), common_timing_s=common,
                relative_timing_s=value-common, total_timing_s=value,
                shared_selected_id=int(number) in result['candidates']['shared']))
    csv_rows(HERE/'comparisons.csv', rows)
    csv_rows(HERE/'identity-histograms.csv', identities)
    csv_rows(HERE/'timings.csv', timings)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    colors = {'original':'#777777', 'saved':'#147d9c', 'saved_space_track':'#147d9c'}
    scopes = ['full', 'DSX01-001', 'DSX01-002', 'DSX01-003']
    fig, axes = plt.subplots(2, 2, figsize=(13, 7), constrained_layout=True)
    for column, arm in enumerate(['fitted-c', 'zero-c-diagnostic']):
        for delta, endpoint in [(-.18, 'original'), (.18, 'saved')]:
            values = [comparisons[arm][scope] for scope in scopes]
            axes[0, column].bar(np.arange(4)+delta,
                [100.*v[endpoint+'_assigned']/v['denominator'] for v in values], .35,
                color=colors[endpoint], label=endpoint)
        axes[0, column].set_xticks(np.arange(4), ['full /4797', '001 /86', '002 /35', '003 /27'])
        axes[0, column].set(title=arm, ylabel='Assigned original observations (%)', ylim=(0, 100))
        for endpoint in ['original', 'saved']:
            axes[1, column].plot(scopes, [comparisons[arm][s]['intersection_'+endpoint+'_rms_hz'] for s in scopes],
                marker='o', color=colors[endpoint], label=endpoint)
        axes[1, column].set(ylabel='Retained-observation RMS (Hz)', xlabel='Frozen cohort; missing values have no retained points')
        for axis in axes[:, column]:
            axis.grid(axis='y', alpha=.2);axis.legend()
    fig.suptitle('S01 immutable saved endpoints: original frozen cohorts; zero-c is not refitted')
    fig.savefig(HERE/'coverage-and-paired-rms.png', dpi=160)
    plt.close(fig)
    for arm in ['fitted-c', 'zero-c-diagnostic']:
        fig, axes = plt.subplots(2, 2, figsize=(16, 9), constrained_layout=True)
        for axis, scope in zip(axes.ravel(), scopes):
            record = comparisons[arm][scope]
            numbers = sorted(set(record['original_identity_histogram']) | set(record['saved_identity_histogram']), key=int)
            if numbers:
                x = np.arange(len(numbers))
                for delta, endpoint in [(-.18, 'original'), (.18, 'saved')]:
                    axis.bar(x+delta, [record[endpoint+'_identity_histogram'].get(n, 0) for n in numbers], .35,
                        color=colors[endpoint], label=endpoint)
                axis.set_xticks(x, numbers, rotation=90, fontsize=6)
            else:
                axis.text(.5, .5, 'No assigned observations', ha='center', va='center', transform=axis.transAxes)
            axis.set(title=f"{scope} /{record['denominator']}", ylabel='Assigned observations; model labels')
            axis.grid(axis='y', alpha=.2)
        axes[0, 0].legend()
        fig.suptitle(f'Every nonzero identity count retained, {arm}; identity confidence not established')
        fig.savefig(HERE/f'identity-histograms-{arm}.png', dpi=180)
        plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    bins = np.arange(-25., 25.01, 1.)
    for endpoint in ['original', 'saved_space_track']:
        selected = [r for r in timings if r['endpoint'] == endpoint]
        shared = [r for r in selected if r['shared_selected_id']]
        for axis, values, title in [
            (axes[0, 0], [r['total_timing_s'] for r in selected], 'Total timing: own selected banks (46 vs59)'),
            (axes[0, 1], [r['relative_timing_s'] for r in selected], 'Relative timing: own selected banks'),
            (axes[1, 0], [r['total_timing_s'] for r in shared], 'Total timing: same34 shared selected IDs')]:
            axis.hist(values, bins=bins, histtype='step', linewidth=1.5, color=colors[endpoint], label=endpoint)
            axis.set(title=title, xlabel='Timing shift (s)', ylabel='Satellite count')
            axis.grid(axis='y', alpha=.2)
    axes[1, 1].bar(['original', 'saved ST'], [result['provenance'][k]['fitted']['common_timing_s']
        for k in ['original', 'saved_space_track']], color=[colors['original'], colors['saved']])
    axes[1, 1].set(title='Common timing (one value per endpoint)', ylabel='seconds')
    axes[0, 0].legend()
    fig.suptitle('Timing remains exactly unchanged by c zeroing; distributions are not localization accuracy')
    fig.savefig(HERE/'timing-histograms.png', dpi=160)
    plt.close(fig)
    print('Wrote comparisons, every identity count, timing CSV and four figures; no model calls.')


if __name__ == '__main__':main()
