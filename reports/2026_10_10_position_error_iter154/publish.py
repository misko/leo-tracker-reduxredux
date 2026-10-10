"""Postseal presentation only; no model, reference or selection ports."""

import json
import math
from pathlib import Path

LABELS = {'native': 'Control', 'fixed': 'Own-arm repair'}
DISCOVERY = {'native': 'Fitted-c discovery', 'zero': 'Zero-c discovery'}
ARMS = ('fitted-c', 'zero-c')


def admitted(summary):
    if not summary.get('all48_terminal') or set(summary.get('policies', {})) != set(DISCOVERY):
        raise ValueError('all 48 cells must be terminal')
    for policy in summary['policies'].values():
        if len(policy['rows']) != 12 or 'passed' not in policy.get('progression', {}):
            raise ValueError('full membership and frozen progression receipt required')


def num(value):
    return 'unavailable' if value is None or not math.isfinite(value) else f'{value:.6f}'


def text(value):
    return json.dumps(value, sort_keys=True).replace('|', '&#124;').replace('\n', '<br>')


def plot(summary, destination):
    admitted(summary)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    figure, axes = plt.subplots(2, 2, figsize=(15, 9), sharex=True)
    colors = {'native': '#777777', 'fixed': '#136a92'}
    for column, discovery in enumerate(DISCOVERY):
        rows = summary['policies'][discovery]['rows']
        for line, arm in enumerate(ARMS):
            axis = axes[line, column]
            for index, row in enumerate(rows):
                values = row['arms'][arm]
                errors = [values[key].get('error_km') for key in LABELS]
                if all(value is not None for value in errors):
                    axis.plot([index-.15, index+.15], errors, color='#bbbbbb', linewidth=1)
                for offset, key in zip((-.15, .15), LABELS):
                    value = values[key].get('error_km')
                    if value is not None:
                        axis.scatter(index+offset, value, color=colors[key], s=25)
                    else:
                        axis.text(index+offset, .02, 'missing', rotation=90, fontsize=7,
                                  transform=axis.get_xaxis_transform(), color='#a22')
            axis.set_title(f'{DISCOVERY[discovery]} · final {arm}')
            axis.set_yscale('symlog', linthresh=.05)
            axis.set_ylabel('Position error (km)')
            axis.grid(axis='y', alpha=.2)
            axis.set_xticks(range(len(rows)), [row['label'] for row in rows], rotation=55, ha='right')
            axis.legend(handles=[Line2D([], [], color=colors[key], marker='o', linestyle='',
                                       label=LABELS[key]) for key in LABELS])
    figure.suptitle('Sealed discovery · fresh matched continuations · twelve consumed recordings')
    figure.tight_layout()
    figure.savefig(destination, dpi=160)
    plt.close(figure)


def markdown(summary):
    admitted(summary)
    lines = ['# Uniform own-arm repair of retained states', '',
             'Consumed twelve-member experiment. Each discovery policy is evaluated separately; '
             'reference errors do not select a discovery policy. Both final c arms remain matched.', '',
             f"**Frozen progression screen: {'PASS' if summary['progression_passed'] else 'FAIL'}.** "
             'Both discovery policies must independently pass. This is not independent validation, '
             'a full-dataset result or deployment authorization.', '',
             '![Paired position errors](position_errors.png)', '',
             '| Discovery | Dataset | Final arm | Paired / members | Control mean / median / p95 / worst km | Repair mean / median / p95 / worst km |',
             '|---|---|---|---:|---|---|']
    for discovery, policy in summary['policies'].items():
        for dataset, arms in policy['aggregates'].items():
            for arm, metrics in arms.items():
                values = []
                for key in LABELS:
                    m = metrics['branches'][key]
                    values.append('unavailable' if m is None else ' / '.join(
                        num(m[field]) for field in ('mean_km', 'median_km', 'p95_km', 'worst_km')))
                lines.append(f"| {DISCOVERY[discovery]} | {dataset} | {arm} | {metrics['paired']}/{metrics['membership']} | " + ' | '.join(values) + ' |')
    lines += ['', 'Incomplete comparisons describe available pairs only; missing endpoints are never imputed.', '',
              '| Discovery | Member | Final arm | Repair − control km | Control RMS Hz | Repair RMS Hz |',
              '|---|---|---|---:|---:|---:|']
    for discovery, policy in summary['policies'].items():
        for row in policy['rows']:
            for arm in ARMS:
                value = row['arms'][arm]
                rms = [num(value[key].get('frequency', {}).get('posterior_rms_hz')) for key in LABELS]
                lines.append(f"| {DISCOVERY[discovery]} | {row['label']} | {arm} | {num(value.get('delta_km'))} | " + ' | '.join(rms) + ' |')
    lines += ['', 'Positive deltas mean repair regressed. Frequency fit is separate from position accuracy.', '',
              '| Discovery | Member | Condition | Status | Selected qualified / 2 | Recorded continuation seconds | Historical control differences |',
              '|---|---|---|---|---:|---:|---|']
    for discovery, policy in summary['policies'].items():
        for row in policy['rows']:
            for key in LABELS:
                qualified = sum(bool(row['arms'][arm][key].get('qualified')) for arm in ARMS)
                differences = policy.get('historical_control_parity', {}).get(row['label']) if key == 'native' else None
                lines.append(f"| {DISCOVERY[discovery]} | {row['label']} | {LABELS[key]} | {row['statuses'][key]} | {qualified}/2 | {num(row['phase_elapsed_s'].get(key))} | {text(differences)} |")
    lines += ['', 'Times sum recorded invocation slices, including audits; unavailable costs are not zero. '
              'Inherited discovery was reused and is not included in these new continuation times. '
              'Five seconds is the repair optimizer deadline, not a hard total wall-time limit.', '',
              'Failure evidence and regional coverage:', '',
              '| Discovery | Member | Condition | Failure reasons | Regional records |',
              '|---|---|---|---|---|']
    for discovery, policy in summary['policies'].items():
        for row in policy['rows']:
            for key in LABELS:
                lines.append(f"| {DISCOVERY[discovery]} | {row['label']} | {LABELS[key]} | {text(row['failure_reasons'].get(key))} | {text(row['regions'][key])} |")
    lines += ['', 'The [summary](SUMMARY.json) preserves frozen progression decisions, frequency objectives, '
              'joint attempts, repair/audit timing events, original/candidate diagnostics, partial-stage '
              'coverage and receipt hashes. Missing regions remain unavailable. Raw receipts remain local; '
              'published hashes do not provide standalone remote replay. The historical controls are '
              'diagnostic comparisons only and never replace fresh endpoints.', '',
              'The official full-cohort metric and deployed pipeline remain unchanged.']
    return '\n'.join(lines) + '\n'


def publish(summary, directory, render=plot):
    admitted(summary)
    directory = Path(directory)
    body = markdown(summary)
    render(summary, directory/'position_errors.png')
    with (directory/'SUMMARY.json').open('x') as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    with (directory/'RESULTS.md').open('x') as stream:
        stream.write(body)
