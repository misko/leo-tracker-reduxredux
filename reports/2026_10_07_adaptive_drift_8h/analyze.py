"""Plot scan-level frequency slopes from a frozen, verified result inventory."""

import csv
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np


HERE = Path(__file__).resolve().parent
LOCAL = ZoneInfo('America/Los_Angeles')
COLORS = ['#2369bd', '#d96919']
METHODS = ['V16', 'T1AT']
ARMS = ['fitted-c', 'zero-c']


def statistics(values):
    a = np.asarray(values, float)
    if not len(a):
        return {'n': 0}
    assert np.isfinite(a).all()
    return dict(n=len(a), minimum=float(a.min()), p05=float(np.percentile(a, 5)),
                p25=float(np.percentile(a, 25)), median=float(np.median(a)),
                p75=float(np.percentile(a, 75)), p95=float(np.percentile(a, 95)),
                maximum=float(a.max()), mean=float(a.mean()),
                absolute_over_10=int((abs(a) > 10).sum()),
                absolute_over_50=int((abs(a) > 50).sum()),
                absolute_at_least_129_15=int((abs(a) >= 129.15).sum()))


def extract(snapshot):
    rows = []
    for capture in snapshot['captures']:
        doc = capture.get('regional_document')
        if not doc:
            continue
        for method in doc['methods']:
            for arm in method['arms']:
                selected = arm['selected']
                if not selected:
                    continue
                completed = [r for r in doc['diagnostics']['final_starts']
                             if r['method'] == method['name'] and r['arm'] == arm['name'] and r['fit']]
                best = min(completed, key=lambda r: (r['fit']['objective'] + r['calibration_penalty'],
                                                    r['basin'], r['start']))
                fit, vector = best['fit'], best['fit']['vector']
                # Audit exact publisher selection and physical vector layout.
                assert best['basin'] == selected['source_basin']
                for a, b in [(fit['objective'] + best['calibration_penalty'], selected['selection_score']),
                             (vector[0], selected['east_km']), (vector[1], selected['north_km']),
                             (vector[6], selected['coefficient_hz_per_ghz'])]:
                    assert np.isclose(a, b, rtol=0, atol=1e-8), (a, b)
                assert fit['converged'] == selected['converged']
                if arm['name'] == 'zero-c':
                    assert vector[6] == 0
                cal = capture['selected_calibrations'].get(best['basin'], {})
                post = cal.get('postfit', {}).get('vector')
                row = dict(session_id=capture['session_id'],
                           capture_start_utc=capture['capture_start_utc'],
                           capture_start_local=dt.datetime.fromtimestamp(capture['capture_start_s'], LOCAL).isoformat(),
                           capture_start_s=capture['capture_start_s'], method=method['name'], arm=arm['name'],
                           rx0_additional_hz_s=vector[3], rx1_additional_hz_s=vector[5],
                           differential_additional_hz_s=vector[5] - vector[3],
                           rx0_calibration_hz_s=post[3] if post else None,
                           rx1_calibration_hz_s=post[5] if post else None,
                           rx0_total_linear_hz_s=post[3] + vector[3] if post else None,
                           rx1_total_linear_hz_s=post[5] + vector[5] if post else None,
                           differential_total_linear_hz_s=post[5] + vector[5] - post[3] - vector[3] if post else None,
                           converged=fit['converged'], boundary=fit['boundary'],
                           stationarity=fit['stationarity'], stop_reason=fit['stop_reason'],
                           selection_score=selected['selection_score'],
                           horizontal_error_km=selected['horizontal_error_m'] / 1000,
                           posterior_rms_hz=selected['posterior_rms_hz'],
                           coefficient_hz_per_ghz=vector[6],
                           source_basin=best['basin'], source_start=best['start'],
                           relative_sigma_s=doc['configuration']['scores'][method['name']]['relative_sigma_s'],
                           configuration_sha256=doc['configuration_sha256'],
                           regional_document_sha256=capture['regional_document_sha256'],
                           calibration_checkpoint_sha256=cal.get('checkpoint_value_sha256'))
                rows.append(row)
    assert len(rows) == len({(r['session_id'], r['method'], r['arm']) for r in rows})
    return rows


def write_csv(name, rows):
    with (HERE / name).open('w') as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def finish(fig, name):
    fig.savefig(HERE / (name + '.png'), dpi=180, facecolor='white')
    fig.savefig(HERE / (name + '.svg'), facecolor='white')
    plt.close(fig)


def distributions(rows, summary, metric):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    fig.subplots_adjust(left=.065, right=.975, bottom=.18, top=.83, hspace=.47, wspace=.15)
    label = 'Additional fitted frequency drift' if metric == 'additional' else 'Total linear frequency-drift term'
    fig.suptitle(label + ' across adaptive scans', fontsize=20, weight='bold', y=.98)
    fig.text(.5, .925, summary['window_label'] + '\n22 completed scans per method/arm; 9 more scans pending',
             ha='center', va='top', fontsize=11, color='#444444')
    values = [r[f'rx{rx}_{metric}_hz_s'] for r in rows for rx in (0, 1)]
    bound = max(150, max(abs(v) for v in values) * 1.15)
    for ai, arm in enumerate(ARMS):
        for mi, method in enumerate(METHODS):
            ax = axes[ai, mi]
            group = [r for r in rows if r['method'] == method and r['arm'] == arm]
            for rx, y in [(0, 1.4), (1, .4)]:
                data = np.array([r[f'rx{rx}_{metric}_hz_s'] for r in group])
                ax.boxplot([data], positions=[y], orientation='horizontal', widths=.34, whis=(0, 100),
                                patch_artist=True, showfliers=False, manage_ticks=False,
                                boxprops=dict(facecolor=COLORS[rx], alpha=.18, edgecolor=COLORS[rx]),
                                medianprops=dict(color=COLORS[rx], linewidth=2),
                                whiskerprops=dict(color=COLORS[rx]), capprops=dict(color=COLORS[rx]))
                # Deterministic offsets expose every scan without suggesting density.
                jitter = (np.arange(len(data)) * .61803398875 % 1 - .5) * .23
                ax.scatter(data, y + jitter, s=25, color=COLORS[rx], edgecolor='white', linewidth=.4, zorder=3)
                bad = np.array([not r['converged'] or r['boundary'] for r in group])
                ax.scatter(data[bad], (y + jitter)[bad], marker='x', s=55, color='#111111', linewidth=1.4, zorder=4)
                ax.text(.025, y / 2.3 + .115,
                        f'median {np.median(data):+.2f}  |  range {data.min():+.2f} to {data.max():+.2f}',
                        transform=ax.transAxes, fontsize=9, color=COLORS[rx])
            ax.set_title(f'{method}  ·  {"fitted c" if arm == "fitted-c" else "c = 0"}',
                         loc='left', fontsize=13, weight='bold', pad=12)
            ax.set_xscale('symlog', linthresh=5, linscale=1)
            ax.set_xlim(-bound, bound)
            ax.set_ylim(-.05, 2.25)
            ax.set_yticks([1.4, .4], ['RX0', 'RX1'])
            ticks = [-100, -30, -10, -5, 0, 5, 10, 30, 100]
            ax.set_xticks(ticks, [str(t) for t in ticks])
            ax.set_xlabel('Frequency drift (Hz/s)', fontsize=10)
            ax.axvline(0, color='#888888', lw=.7, zorder=0)
            ax.grid(axis='x', alpha=.15)
            ax.spines[['top', 'right', 'left']].set_visible(False)
    fig.legend(handles=[Line2D([], [], marker='o', color='#666666', ls='', label='One selected scan fit'),
                        Line2D([], [], marker='x', color='black', ls='', label='Unconverged or boundary fit')],
               loc='lower center', bbox_to_anchor=(.5, .083), ncol=2, frameon=False, fontsize=10)
    description = ('Slopes added after frozen calibration; comparable to the earlier −129.15 Hz/s diagnostic.'
                   if metric == 'additional' else
                   'Calibration linear slope + final correction; excludes time-varying piecewise-linear calibration.')
    fig.text(.5, .055, description + '\nBox = middle 50%; whiskers = full range. Axis is linear within ±5 Hz/s, logarithmic outside.',
             ha='center', va='top', fontsize=9, color='#444444')
    finish(fig, 'drift_distribution' if metric == 'additional' else 'total_linear_distribution')


def timeline(rows, snapshot, summary):
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), sharex=True, sharey=True)
    fig.subplots_adjust(left=.075, right=.98, top=.82, bottom=.16, hspace=.28, wspace=.12)
    fig.suptitle('When the large drift corrections occurred', fontsize=20, weight='bold', y=.98)
    fig.text(.5, .925, summary['window_label'] + '\nAll selected fits shown; pending scans have no drift estimate',
             ha='center', va='top', fontsize=11, color='#444444')
    pending = [dt.datetime.fromtimestamp(c['capture_start_s'], LOCAL) for c in snapshot['captures']
               if not c.get('regional_document')]
    limits = [dt.datetime.fromisoformat(t).astimezone(LOCAL) for t in snapshot['capture_window_utc']]
    for ai, arm in enumerate(ARMS):
        for mi, method in enumerate(METHODS):
            ax = axes[ai, mi]
            group = [r for r in rows if r['method'] == method and r['arm'] == arm]
            ts = [dt.datetime.fromtimestamp(r['capture_start_s'], LOCAL) for r in group]
            for rx in (0, 1):
                data = [r[f'rx{rx}_additional_hz_s'] for r in group]
                ax.plot(ts, data, 'o-', ms=4, lw=.8, color=COLORS[rx], label=f'RX{rx}')
                bad = [i for i, r in enumerate(group) if not r['converged'] or r['boundary']]
                ax.scatter([ts[i] for i in bad], [data[i] for i in bad], marker='x', s=55, c='black', zorder=4)
            if pending:
                ax.scatter(pending, [.035] * len(pending), transform=ax.get_xaxis_transform(),
                           marker='|', s=120, c='#888888', clip_on=False)
                if min(pending) > max(ts):
                    ax.axvspan(min(pending), limits[1], color='#eeeeee', zorder=-1)
                    ax.text(.97, .93, '9 pending', ha='right', va='top', transform=ax.transAxes, color='#777777', fontsize=10)
            ax.set_title(f'{method}  ·  {"fitted c" if arm == "fitted-c" else "c = 0"}', loc='left', fontsize=13, weight='bold')
            ax.set_yscale('symlog', linthresh=5)
            ax.set_ylim(-150, 150)
            ax.set_yticks([-100, -30, -5, 0, 5, 30, 100], ['−100', '−30', '−5', '0', '5', '30', '100'])
            ax.set_xlim(*limits)
            ax.xaxis.set_major_locator(mdates.HourLocator(tz=LOCAL))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=LOCAL))
            ax.grid(alpha=.2)
            ax.spines[['top', 'right']].set_visible(False)
            if mi == 0:
                ax.set_ylabel('Additional drift (Hz/s)')
            if ai == 1:
                ax.set_xlabel('Capture start, Oct 6 (PDT)')
    fig.legend(handles=[Line2D([], [], color=COLORS[rx], marker='o', label=f'RX{rx}') for rx in (0, 1)] +
               [Line2D([], [], marker='x', color='black', ls='', label='Unconverged / boundary')],
               loc='lower center', bbox_to_anchor=(.5, .065), ncol=3, frameon=False)
    fig.text(.5, .035, 'Linear scale within ±5 Hz/s; logarithmic outside. Connecting lines only guide the eye.', ha='center', fontsize=9, color='#444444')
    finish(fig, 'drift_timeline')


def main():
    raw = (HERE / 'snapshot.json').read_bytes()
    snapshot = json.loads(raw)
    assert not [c for c in snapshot['captures'] if c.get('collection_error')]
    rows = extract(snapshot)
    write_csv('per_scan.csv', rows)
    start, end = [dt.datetime.fromisoformat(t).astimezone(LOCAL) for t in snapshot['capture_window_utc']]
    complete = [c for c in snapshot['captures'] if c.get('regional_document')]
    summary = dict(snapshot_sha256=hashlib.sha256(raw).hexdigest(), snapshot_utc=snapshot['snapshot_utc'],
                   capture_window_utc=snapshot['capture_window_utc'],
                   capture_window_local=[start.isoformat(), end.isoformat()],
                   window_label=f'{start:%b %d, %Y · %H:%M}–{end:%H:%M %Z} (8 hours)',
                   capture_count=len(snapshot['captures']), completed_count=len(complete),
                   regional_status_counts=dict(Counter(c['regional_status'] for c in snapshot['captures'])),
                   pending_sessions=[c['session_id'] for c in snapshot['captures'] if not c.get('regional_document')],
                   configuration_counts=dict(Counter(c['regional_document']['configuration_sha256'] for c in complete)),
                   definitions=dict(additional='Final physical vector b0 = vector[3], b1 = vector[5], in Hz/s, added to frozen receiver baseline.',
                                    total_linear='Calibration postfit b + final-fit b. Nonlinear piecewise correction remains separate; not an instantaneous total derivative.',
                                    differential='RX1 minus RX0 for the same selected fit.'), grouped={},
                   limitations=[
                       'Empirical scan-level fitted-parameter distribution, not a hardware clock measurement or posterior uncertainty distribution.',
                       'Only published selected results, one per scan/method/arm. No offline repair trials or other optimizer starts included.',
                       'Missing recent regional results can bias coverage; no missing value was imputed.',
                       'Unconverged and boundary selections are retained and marked, not silently filtered.',
                       'Both c arms use the published shared fitted-c upstream calibration protocol; winning basins can differ.',
                       'These are original published fits, not the offline sigma=1s, cones, or paired-clock experiments.',
                       'Extra correction can be small despite a large upstream calibration slope.',
                       'Scan estimates are correlated and cannot directly define a Kalman process-noise prior.'
                   ])
    for method in METHODS:
        for arm in ARMS:
            group = [r for r in rows if r['method'] == method and r['arm'] == arm]
            entry = dict(n=len(group), converged=sum(r['converged'] for r in group),
                         boundary=sum(r['boundary'] for r in group),
                         relative_sigma_s=sorted({r['relative_sigma_s'] for r in group}), metrics={})
            for metric in ['additional', 'total_linear']:
                entry['metrics'][metric] = {rx: statistics([r[f'{rx}_{metric}_hz_s'] for r in group])
                                           for rx in ['rx0', 'rx1', 'differential']}
                entry['metrics'][metric]['converged_interior'] = {
                    rx: statistics([r[f'{rx}_{metric}_hz_s'] for r in group if r['converged'] and not r['boundary']])
                    for rx in ['rx0', 'rx1', 'differential']}
            summary['grouped'][f'{method}/{arm}'] = entry
    outliers = []
    for row in rows:
        for rx in (0, 1):
            outliers.append(dict(row, receiver=rx, additional_hz_s=row[f'rx{rx}_additional_hz_s']))
    outliers.sort(key=lambda r: abs(r['additional_hz_s']), reverse=True)
    summary['largest_additional_drift'] = outliers[:12]
    write_csv('ranked_receiver_slopes.csv', outliers)
    (HERE / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    # This frozen request has 22 complete and 9 pending; catch stale captions.
    assert len(complete) == 22 and len(snapshot['captures']) == 31
    assert all(e['n'] == 22 for e in summary['grouped'].values())
    assert all(r['rx0_total_linear_hz_s'] is not None for r in rows)
    distributions(rows, summary, 'additional')
    distributions(rows, summary, 'total_linear')
    timeline(rows, snapshot, summary)
    report = [summary['window_label'], f"{len(complete)} completed of {len(snapshot['captures'])} scans; 9 pending.", '',
              'Additional final-fit drift, Hz/s:']
    for name, entry in summary['grouped'].items():
        report.append(f"{name}: {entry['converged']}/{entry['n']} converged; {entry['boundary']} boundary; relative timing sigma {entry['relative_sigma_s']} s")
        for rx in ['rx0', 'rx1', 'differential']:
            st = entry['metrics']['additional'][rx]
            report.append(f"  {rx}: median {st['median']:+.3f}; min {st['minimum']:+.3f}; max {st['maximum']:+.3f}; |b|>10: {st['absolute_over_10']}/{st['n']}")
    report += ['', 'Largest additional receiver slopes:']
    for row in outliers[:8]:
        report.append(f"{row['capture_start_local']} {row['session_id']} {row['method']}/{row['arm']} RX{row['receiver']}: {row['additional_hz_s']:+.3f} Hz/s; converged={row['converged']}; position error={row['horizontal_error_km']:.3f} km")
    report += ['', 'Definitions:'] + list(summary['definitions'].values())
    report += ['', 'Limitations:'] + summary['limitations']
    report += ['', 'Validation: exact published selection reproduced for all 88 scan/method/arm rows; input digests and calibration checkpoint digests verified; no nonfinite slopes; zero-c coefficients equal zero.',
               'Run collect.py once with deployed worker PYTHONPATH; run analyze.py using API virtualenv. Source snapshot is frozen and collection refuses to overwrite it.']
    (HERE / 'report.txt').write_text('\n'.join(report) + '\n')
    print('\n'.join(report))


if __name__ == '__main__':
    main()
