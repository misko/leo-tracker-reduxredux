"""Report-only geographic evaluation of sealed, GPS-blind model controls.

This script is intentionally outside the fitting/qualification modules. It
requires every case and numerical replay audit before reading position errors.
"""
from pathlib import Path
import csv
import hashlib
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reporting_counts import likelihood_point_count

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'report'
TRUTH = np.array([37.849061591561885, -122.48574968092912])
MODELS = {
    'baseline': ('Current baseline', '#222222'),
    'receiver_specific_noise': ('Separate RX noise', '#0072B2'),
    'receiver_fast_rx1_rf50': ('Shared RX1, RF-scaled', '#D55E00'),
    'receiver_fast_rx1_hz50': ('Shared RX1, additive Hz', '#009E73'),
}
ARMS = {'c0': 'c = 0', 'fitted_c': 'Fitted c'}


def read(path):
    return json.loads(path.read_text())


def distance(latlon):
    p, q = np.radians(np.asarray([latlon, TRUTH]))
    a = np.sin((p[0]-q[0])/2)**2 + np.cos(p[0])*np.cos(q[0])*np.sin((p[1]-q[1])/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def write_csv(path, rows):
    with path.open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def stat(values):
    v = np.asarray(values)
    return dict(n=len(v), mean_km=float(v.mean()), median_km=float(np.median(v)),
                p95_km=float(np.percentile(v, 95)), max_km=float(v.max()))


def main():
    seal = read(ROOT/'evaluation/batch_seal.json')
    assert seal['passed'] and seal['total_arm_results'] == 144
    cases = read(ROOT/'noise/protocol.json')['cases']
    assert len(cases) == 24
    with (ROOT/'likelihood_count_audit.csv').open() as file:
        id_counts = {(r['case'],r['arm']):r for r in csv.DictReader(file) if r['group']=='all_channels'}
    assert len(id_counts) == 48
    def predictive(fit, case, arm):
        audit = id_counts[case,arm]
        assert fit['active_points'] == int(audit['curved_unique_ids'])
        total = likelihood_point_count(fit, legacy_predictive_points=int(audit['predictive_unique_ids']))
        assert total == int(audit['likelihood_union_ids'])
        return total-fit['active_points']
    sealed = {}
    bindings = {}
    for model in list(MODELS)[1:]:
        folder = ROOT/'evaluation/models'/model
        execution = read(folder/'execution.json')
        audit = read(folder/'independent_replay_audit.json')
        assert execution['all_terminal'] and execution['cases'] == len(cases)
        assert audit['passed'] and audit['replayed_arms'] == 2*len(cases)
        sealed[model] = [read(folder/f'{case}.json') for case in cases]
        assert all(r['status'] == 'complete' and not r['GPS_used'] for r in sealed[model])
        for path in [folder/'execution.json', folder/'independent_replay_audit.json',
                     *[folder/f'{case}.json' for case in cases]]:
            bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    OUT.mkdir(exist_ok=True)
    first = sealed['receiver_specific_noise']
    rows, counts = [], []
    for model, results in sealed.items():
        counts.append(dict(model=model, cases=len(results), adopted=sum(r['adopted'] for r in results),
                           fallback=sum(not r['adopted'] for r in results),
                           runtime_failures=sum(r['status'] != 'complete' for r in results)))
        for index, r in enumerate(results):
            assert r['case'] == cases[index] and r['baseline'] == first[index]['baseline']
            for arm in ARMS:
                base, trial = r['baseline'][arm], r['arms'][arm]
                for variant, result in [('trial', trial), ('policy', trial if r['adopted'] else base)]:
                    assert result['active_points'] == base['active_points']
                    assert predictive(result, r['case'], arm) == predictive(base, r['case'], arm)
                    error, before = distance(result['endpoint_latlon']), distance(base['endpoint_latlon'])
                    rows.append(dict(case=r['case'], model=model, arm=arm, variant=variant,
                        adopted=r['adopted'], policy_source=r['policy_source'],
                        error_km=error, baseline_error_km=before, change_km=error-before,
                        lat=result['endpoint_latlon'][0], lon=result['endpoint_latlon'][1],
                        rms_hz=result['RMS_hz'], rms_change_hz=result['RMS_hz']-base['RMS_hz'],
                        negative_twice_elbo=result['negative_twice_elbo'],
                        objective_change=result['negative_twice_elbo']-base['negative_twice_elbo'],
                        active_curved_points=result['active_points'], predictive_points=predictive(result,r['case'],arm)))
    for r in first:
        for arm in ARMS:
            b = r['baseline'][arm]
            rows.append(dict(case=r['case'], model='baseline', arm=arm, variant='policy',
                adopted=False, policy_source='baseline', error_km=distance(b['endpoint_latlon']),
                baseline_error_km=distance(b['endpoint_latlon']), change_km=0.,
                lat=b['endpoint_latlon'][0], lon=b['endpoint_latlon'][1], rms_hz=b['RMS_hz'], rms_change_hz=0.,
                negative_twice_elbo=b['negative_twice_elbo'], objective_change=0.,
                active_curved_points=b['active_points'], predictive_points=predictive(b,r['case'],arm)))
    summary = []
    for arm in ARMS:
        for model in MODELS:
            for variant in (['policy'] if model == 'baseline' else ['trial', 'policy']):
                chosen = [r for r in rows if (r['model'],r['arm'],r['variant']) == (model,arm,variant)]
                assert len(chosen) == len(cases)
                summary.append(dict(model=model, arm=arm, variant=variant,
                    **stat([r['error_km'] for r in chosen]),
                    improved=sum(r['change_km'] < -1e-6 for r in chosen),
                    worsened=sum(r['change_km'] > 1e-6 for r in chosen),
                    tied=sum(abs(r['change_km']) <= 1e-6 for r in chosen),
                    median_rms_change_hz=float(np.median([r['rms_change_hz'] for r in chosen])),
                    median_objective_change=float(np.median([r['objective_change'] for r in chosen]))))
    write_csv(OUT/'positions.csv', rows)
    write_csv(OUT/'summary.csv', summary)
    write_csv(OUT/'adoption.csv', counts)
    for path in [ROOT/'likelihood_count_audit.csv',ROOT/'reporting_counts.py',Path(__file__)]:
        bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = dict(evaluation_only_GPS=TRUTH.tolist(), models=list(MODELS), cases=cases,
        baseline='ALGO02-v1 + qualified causal signed phase prior + equal-assignment family cavity',
        summary=summary, adoption=counts, source_bindings=bindings,
        no_geographic_selection=True, no_combination_or_GPS_best_policy=True,
        statistical_scope='descriptive development-cohort outcomes, not independent unseen-location accuracy',
        coverage=dict(active_curved=66110, predictive=11957, all_GLRT=108600,
                      associated_percent=100*78067/108600, same_all_models_and_c_arms=True))
    (OUT/'summary.json').write_text(json.dumps(metadata, indent=2)+'\n')
    plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, (arm, title) in zip(axes, ARMS.items()):
        for model, (label, color) in MODELS.items():
            values = sorted(r['error_km'] for r in rows if (r['model'],r['arm'],r['variant'])==(model,arm,'policy'))
            ax.step(values, np.arange(1,len(values)+1)/len(values)*100, where='post', label=label, color=color,
                    linewidth=2, linestyle='--' if model.endswith('hz50') else '-')
        ax.set(title=title, xlabel='Position error (km)', ylim=(0,102), xlim=(0,2.5))
        ax.grid(alpha=.2)
    axes[0].set_ylabel('Cumulative fraction of 24 scans (%)')
    axes[1].legend(fontsize=9, loc='lower right')
    fig.suptitle('DS24: complete paired policies, including baseline fallbacks')
    fig.tight_layout(); fig.savefig(OUT/'position_cdf.png', dpi=180); plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    for ax, (arm, title) in zip(axes, ARMS.items()):
        for k, (model, (label,color)) in enumerate(list(MODELS.items())[1:]):
            selected = {r['case']:r for r in rows if (r['model'],r['arm'],r['variant'])==(model,arm,'policy')}
            x = np.arange(len(cases))+(k-1)*.23
            y = np.array([selected[c]['change_km']*1000 for c in cases])
            ax.bar(x, y, width=.22, color=color, label=label)
            rejected = [i for i,c in enumerate(cases) if not selected[c]['adopted']]
            ax.scatter(x[rejected], y[rejected], s=23, marker='x', color=color, zorder=5)
        ax.axhline(0, color='black', linewidth=.7); ax.grid(axis='y', alpha=.2)
        ax.set(title=title, ylabel='Error change (m)\nnegative = better')
    axes[0].legend(ncol=3, fontsize=9)
    axes[1].set_xticks(range(len(cases)), [c[-4:] for c in cases], rotation=60)
    axes[1].set_xlabel('DS24 scan; × at zero denotes an exact baseline fallback')
    fig.suptitle('Every usable scan retained; no selection by GPS error')
    fig.tight_layout(); fig.savefig(OUT/'position_changes.png', dpi=180); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, (arm, title) in zip(axes, ARMS.items()):
        for model,(label,color) in list(MODELS.items())[1:]:
            rr = [r for r in rows if (r['model'],r['arm'],r['variant'])==(model,arm,'trial')]
            ok = [r for r in rr if r['adopted']]; no = [r for r in rr if not r['adopted']]
            ax.scatter([r['rms_change_hz'] for r in ok], [1000*r['change_km'] for r in ok], color=color, s=40, label=label, alpha=.8)
            ax.scatter([r['rms_change_hz'] for r in no], [1000*r['change_km'] for r in no], color=color, s=40, marker='x')
        ax.axhline(0,color='black',linewidth=.6); ax.axvline(0,color='black',linewidth=.6)
        ax.grid(alpha=.2); ax.set(title=title, xlabel='Trial curved residual RMS change (Hz)')
    axes[0].set_ylabel('Trial position-error change (m)')
    axes[1].legend(fontsize=8)
    fig.suptitle('Frequency fit and position accuracy are separate outcomes; × = rejected trial')
    fig.tight_layout(); fig.savefig(OUT/'frequency_vs_position.png',dpi=180); plt.close(fig)
    noise = read(ROOT/'noise/summary.json')['rows']
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.bar(range(len(noise)), [r['heldout_gain'] for r in noise], color='#0072B2')
    ax.axhline(2*np.log(2), color='black', linestyle='--', linewidth=.8,
               label='Total-gain threshold; also require 2 of 3 positive folds')
    ax.set_xticks(range(len(noise)), [r['case'][-4:] for r in noise], rotation=60)
    ax.set(xlabel='DS24 scan', ylabel='Held-family −2 log-density gain',
           title='Receiver-specific noise predicts graph-residual contrasts better in all 24 scans')
    ax.legend(fontsize=9); ax.grid(axis='y', alpha=.2)
    fig.tight_layout(); fig.savefig(OUT/'noise_validation.png',dpi=180); plt.close(fig)
    print(json.dumps(dict(adoption=counts, summary=[r for r in summary if r['variant']=='policy']),indent=2))


if __name__ == '__main__':
    main()
