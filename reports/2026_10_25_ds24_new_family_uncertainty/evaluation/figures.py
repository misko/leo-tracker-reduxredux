"""Static scientific figures from sealed RF and separate geographic tables."""

import csv
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parent/'.mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCIENCE = ROOT/'scientific'
OUT = ROOT/'figures'
CASES = ('DS24-0095', 'DS24-0087')
ARMS = ('c0', 'fitted_c')
BRANCHES = ('predictive_shape_zero', 'predictive_shape_prior')
LABELS = {'predictive_shape_zero':'Zero shape covariance', 'predictive_shape_prior':'Physical shape prior'}
COLORS = {'predictive_shape_zero':'#0072B2', 'predictive_shape_prior':'#D55E00'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(fig, name, caption):
    fig.text(.5, .015, caption, ha='center', va='bottom', fontsize=9)
    fig.tight_layout(rect=(0, .065, 1, .96))
    for suffix in ('.png', '.pdf'):
        destination = OUT/(name+suffix)
        fig.savefig(destination, dpi=170)
    plt.close(fig)


def profile(case, arm, branch):
    return [read(SCIENCE/'profiles03'/case/f'{arm}_{branch}_{index:02d}.json') for index in range(11)]


def main():
    assert read(ROOT/'audit/terminal_audit.json')['status'] == 'passed'
    assert read(ROOT/'math_audit/terminal03_audit.json')['all_passed']
    assert read(HERE/'summary.json')['status'] == 'complete'
    plt.rcParams.update({'font.size':10, 'axes.titlesize':11, 'axes.labelsize':10})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    components = []
    for row, case in enumerate(CASES):
        for column, arm in enumerate(ARMS):
            ax = axes[row, column]
            for branch in BRANCHES:
                data = profile(case, arm, branch)
                fractions = [point['fraction'] for point in data]
                total = np.array([point['total_negative_twice_elbo'] for point in data])
                parent = np.array([point['parent_negative_twice_elbo'] for point in data])
                ax.plot(fractions, total-total[0], '.-', color=COLORS[branch], label=LABELS[branch])
                if branch == BRANCHES[0]:
                    ax.plot(fractions, parent-parent[0], '--', color='0.35', label='Original parent component')
                first, last = data[0], data[-1]
                before, after = first['target_conditional'], last['target_conditional']
                values = dict(case=case, arm=arm, branch=branch,
                    parent_change=last['parent_negative_twice_elbo']-first['parent_negative_twice_elbo'],
                    target_quadratic_change=after['expected_node_terms']['quadratic']-before['expected_node_terms']['quadratic'],
                    target_logdet_change=after['expected_node_terms']['logdet']-before['expected_node_terms']['logdet'],
                    target_normalization_change=after['expected_node_terms']['normalization']-before['expected_node_terms']['normalization'],
                    phase_KL_change=after['phase_posterior_to_prior_quadrature_penalty']-before['phase_posterior_to_prior_quadrature_penalty'],
                    total_change=last['total_negative_twice_elbo']-first['total_negative_twice_elbo'])
                np.testing.assert_allclose(values['total_change'], sum(values[key] for key in ('parent_change', 'target_quadratic_change',
                    'target_logdet_change', 'target_normalization_change', 'phase_KL_change')), atol=1e-8, rtol=0)
                components.append(values)
            ax.axhline(0, color='0.7', lw=.8)
            ax.set(title=f'{case} · '+('c = 0' if arm == 'c0' else 'fitted c'),
                xlabel='Fraction along baseline to saved support segment', ylabel='Change in normalized objective')
            ax.grid(alpha=.2)
    axes[0, 0].legend(fontsize=9)
    fig.suptitle('Shape uncertainty changes the preference along a fixed position segment')
    save(fig, 'fixed_position_profiles', 'Each branch is relative to its own value at the baseline position; lower is preferred.\nParent phase references are fixed. These segments are diagnostics, not global searches or confidence intervals.')
    with (HERE/'profile_component_changes.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(components[0])); writer.writeheader(); writer.writerows(components)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    keys = ('parent_change', 'target_quadratic_change', 'target_logdet_change', 'phase_KL_change', 'total_change')
    names = ('Parent', 'Target quadratic', 'Target log determinant', 'Phase KL', 'Total')
    for row, case in enumerate(CASES):
        for column, arm in enumerate(ARMS):
            ax = axes[row, column]
            for index, branch in enumerate(BRANCHES):
                values = next(v for v in components if (v['case'], v['arm'], v['branch']) == (case, arm, branch))
                ax.bar(np.arange(len(keys))+(index-.5)*.34, [values[key] for key in keys], width=.34,
                    color=COLORS[branch], label=LABELS[branch])
            ax.axhline(0, color='0.35', lw=.8); ax.set_xticks(range(len(keys)), names, rotation=18, ha='right')
            ax.set(title=f'{case} · '+('c = 0' if arm == 'c0' else 'fitted c'), ylabel='Objective change')
            ax.grid(axis='y', alpha=.2)
    axes[0, 0].legend(fontsize=9)
    fig.suptitle('The target residual quadratic accounts for the main preference reversal')
    save(fig, 'fixed_position_components', 'Changes are saved support position minus baseline position. Expected node terms and phase KL reconstruct the mixture score.\nThese are correlated model components, not independent physical causes; the target normalization change is zero.')

    for arm in ARMS:
        fig, axes = plt.subplots(2, 2, figsize=(12, 8))
        for column, case in enumerate(CASES):
            target = read(ROOT/'audit'/(case+'_target_binding.json'))
            times = np.asarray(target['times_s']); native = np.asarray(target['native_measured_cfo_hz'])
            axes[0, column].scatter(times, native/1000, color='0.25', s=15, label=f'Unqualified source: {len(times)} native points', zorder=3)
            for branch in BRANCHES:
                diagnostic = read(SCIENCE/'fits03'/case/arm/branch/'rf_diagnostics.json')
                assert diagnostic['target_observation_ids'] == target['observation_ids']
                residual = np.asarray(diagnostic['target_phase_marginal_mean_residual_hz'])
                predicted = native-residual
                # Native-ID gauge mapping is pointwise. Never connect a line
                # across an alias wrap or an unobserved gap longer than10s.
                break_before = np.r_[False, (abs(np.diff(native)) > (1/(4.4e-6))/2) | (np.diff(times) > 10)]
                plot_times, plot_prediction = [], []
                for index, (time, prediction) in enumerate(zip(times, predicted, strict=True)):
                    if break_before[index]:
                        plot_times.append(np.nan); plot_prediction.append(np.nan)
                    plot_times.append(time); plot_prediction.append(prediction/1000)
                axes[0, column].plot(plot_times, plot_prediction, '-', color=COLORS[branch], label=LABELS[branch])
                axes[1, column].plot(times, residual, '.-', color=COLORS[branch], label=LABELS[branch])
            axes[0, column].set(title=case+f' / model family {target["norad"]}', ylabel='Native CFO (kHz)', xlabel='Scan time (s)')
            axes[1, column].set(ylabel='Residual before target-local adjustments (Hz)', xlabel='Scan time (s)')
            axes[1, column].axhline(0, color='0.4', lw=.8)
            for ax in axes[:, column]:
                ax.grid(alpha=.2)
        axes[0, 0].legend(fontsize=8)
        fig.suptitle(('c = 0' if arm == 'c0' else 'Fitted c')+': target CFO and phase-integrated residuals at experimental endpoints')
        save(fig, 'target_cfo_residual_'+arm, 'Native-gauge prediction: phase-posterior orbit mean plus parent radio/E-conditional mean; target constant/shape mean adjustments are omitted.\nThis is a descriptive residual, not full-fit RMS or held-out prediction. Target data condition phase; no calibrated orbit correction is claimed.')

    evaluation = read(HERE/'summary.json')['comparisons']
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    names = ('Saved\nbaseline', 'Full-shape graph\n(INVALID)', 'Phase-only\nsupport control', 'Predictive\nshape zero', 'Predictive\nshape prior')
    fields = ('baseline_error_km', 'invalid_shape_present_graph_error_km', 'saved_phase_only_support_error_km',
        'predictive_shape_zero_error_km', 'predictive_shape_prior_error_km')
    for ax, case in zip(axes, CASES, strict=True):
        for index, arm in enumerate(ARMS):
            row = next(v for v in evaluation if v['case'] == case and v['arm'] == arm)
            bars = ax.bar(np.arange(5)+(index-.5)*.35, [row[field] for field in fields], width=.35,
                color=('#56B4E9' if arm == 'c0' else '#E69F00'), label=('c = 0' if arm == 'c0' else 'Fitted c'))
            bars[1].set_hatch('///'); bars[1].set_alpha(.55)
        ax.set_xticks(range(5), names, fontsize=9)
        ax.set(title=case, ylabel='Evaluation error (km)'); ax.grid(axis='y', alpha=.2)
    axes[0].legend()
    fig.suptitle('Preserving shape uncertainty prevents a large 0095 regression, but does not beat its baseline')
    save(fig, 'geographic_control_comparison', 'Geographic reporting followed the RF seal and independent terminal audits. All new target factors remain unqualified.\nThe saved graph control is INVALID; the operational output is the saved baseline for every branch. Two previously examined cases only.')

    receipt = dict(no_new_fits_or_propagation=True, source_sha256=sha(Path(__file__)),
        RF_seal_sha256=sha(SCIENCE/'RF_seal03.json'), evaluation_summary_sha256=sha(HERE/'summary.json'),
        figures={str(path.relative_to(ROOT)):sha(path) for path in sorted(OUT.iterdir()) if path.suffix in ('.png', '.pdf')},
        component_table_sha256=sha(HERE/'profile_component_changes.csv'), native_CFO_mapping='prediction_native=measured_native-descriptive_residual at identical native IDs; alias/gap breaks retained',
        all_new_target_associations_unqualified=True)
    with (HERE/'figure_receipt.json').open('w') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
