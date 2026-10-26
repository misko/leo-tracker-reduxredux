"""Reporting-only addendum: all-probe weights and explicit unavailable panels."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / 'report02'
read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
CASES = ('DS24-0011', 'DS24-0012')
ARMS = ('c0', 'fitted_c')
PROBES = ('minus', 'center', 'plus')
PRIORS = (.25, .5, .75)


def verify(path):
    for name, digest in read(path)['files'].items():
        if sha(name) != digest:
            raise ValueError('bound file changed: ' + name)


def main():
    verify(HERE / 'RF_seal.json')
    verify(HERE / 'report/seal.json')
    OUT.mkdir(exist_ok=False)
    weights, discrimination = [], []
    for case in CASES:
        for probe in PROBES:
            for arm in ARMS:
                path = HERE / case / probe / (arm + '_summary.json')
                if not path.exists():
                    continue
                row = read(path)
                labels = [model['norad'] for model in row['models']] + ['unknown']
                for prior in PRIORS:
                    for label, value in zip(labels, row['mixture'][str(prior)]['conditional_model_weights'], strict=True):
                        weights.append(dict(case=case, probe=probe, arm=arm,
                            offset_km={'minus': -.1, 'center': 0., 'plus': .1}[probe],
                            physical_class_prior=prior, hypothesis=label,
                            conditional_density_weight=value, calibrated_identity_probability=False))
                models = sorted(row['models'], key=lambda model: model['objective'])
                discrimination.append(dict(case=case, probe=probe, arm=arm,
                    hard_nominee=58175 if case == 'DS24-0011' else 57743,
                    best_point_nominee=row['best_physical_point_norad'],
                    second_point_nominee=models[1]['norad'],
                    second_minus_best_objective=models[1]['objective'] - models[0]['objective'],
                    unknown_minus_hard_objective=row['unknown']['objective'] - row['hard']['objective'],
                    hard_minus_best_objective=row['hard']['objective'] - row['best_physical_point_objective']))
    for name, rows in [('all_probe_model_weights.csv', weights), ('discrimination.csv', discrimination)]:
        with (OUT / name).open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)

    with (HERE / 'report/profiles.csv').open() as stream:
        profiles = list(csv.DictReader(stream))
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    for i, case in enumerate(CASES):
        for j, arm in enumerate(ARMS):
            ax = axes[i, j]
            if case == 'DS24-0012':
                ax.text(.5, .55, 'Budget-limited at center reference check\nNo side-probe profile or secant',
                    ha='center', va='center', transform=ax.transAxes)
                ax.set_xticks([-.1, 0, .1]); ax.set_xlim(-.12, .12)
            else:
                for model, label, color, style in [
                    ('hard', 'Fixed hard nominee 58175', '#333333', '-'),
                    ('best_physical_point_envelope', 'Best of eight (same 58175)', '#d48724', '--'),
                    ('mixture_0.5', 'Mixture: physical mass 0.5', '#00796b', '-'),
                    ('unknown', 'Fixed proper unresolved model', '#65758b', '-')]:
                    rows = [r for r in profiles if r['case'] == case and r['arm'] == arm and r['model'] == model]
                    center = float(next(r for r in rows if r['probe'] == 'center')['conditional_target_objective'])
                    ax.plot([float(r['offset_km']) for r in rows],
                        [float(r['conditional_target_objective']) - center for r in rows],
                        marker='o', ls=style, color=color, label=label, ms=4)
                ax.legend(fontsize=8)
            ax.axhline(0, lw=.6, color='gray'); ax.grid(alpha=.2)
            ax.set_title(case + ' · ' + ('c=0' if arm == 'c0' else 'fitted c'))
            ax.set_xlabel('Offset along frozen c0 RF weak axis (km)')
            ax.set_ylabel('Target objective minus its own center')
    fig.suptitle('Fixed RF profiles: point estimates, not position fits\nShared parent factor cancels from the mixture-minus-hard comparison.', fontsize=11)
    fig.savefig(OUT / 'fixed_RF_profiles02.png', dpi=180); plt.close(fig)

    summary = read(HERE / 'report/summary.json')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout='constrained')
    for ax, case in zip(axes, CASES, strict=True):
        ax.axhspan(-25, 25, color='gray', alpha=.12, label='±25 m research screen')
        rows = [r for r in summary['secants'] if r['case'] == case]
        for arm, color, shift in [('c0', '#00796b', -.012), ('fitted_c', '#b34c32', .012)]:
            for index, row in enumerate(r for r in rows if r['arm'] == arm):
                x = row['physical_class_weight'] + shift
                ax.vlines(x, row['proxy_lower_m'], row['proxy_upper_m'], color=color, lw=2)
                ax.plot([x, x], [row['proxy_lower_m'], row['proxy_upper_m']], '_', color=color)
                ax.plot(x, row['point_proxy_m'], 'o', color=color, label=arm if index == 0 else None)
        if not rows:
            ax.text(.5, .5, 'Budget-limited\nNo secant result', ha='center', va='center', transform=ax.transAxes)
        ax.axhline(0, color='black', lw=.6); ax.set_ylim(-420, 45); ax.set_xlim(.19, .81)
        ax.set_xticks(PRIORS); ax.grid(axis='y', alpha=.2); ax.set_title(case)
        ax.set_xlabel('Predeclared total physical-class prior mass')
        ax.set_ylabel('Archived-curvature-scaled secant proxy (m)'); ax.legend(fontsize=8)
    fig.suptitle('Mixture minus the fixed hard nominee\nDots: point proxies; lines: full-evidence intervals. Neither is achieved movement.', fontsize=11)
    fig.savefig(OUT / 'secant_proxy_bounds02.png', dpi=180); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    for ax, arm in zip(axes, ARMS, strict=True):
        for label, color in [(58175, '#00796b'), (63312, '#b34c32')]:
            rows = [r for r in weights if r['case'] == 'DS24-0011' and r['arm'] == arm
                and r['physical_class_prior'] == .5 and r['hypothesis'] == label]
            ax.plot([r['offset_km'] for r in rows], [r['conditional_density_weight'] for r in rows],
                'o-', color=color, label=str(label))
        ax.set_xticks([-.1, 0, .1]); ax.set_ylim(.35, .65); ax.grid(alpha=.2)
        ax.set_title('DS24-0011 · ' + ('c=0' if arm == 'c0' else 'fitted c'))
        ax.set_xlabel('Offset along frozen c0 RF weak axis (km)')
        ax.set_ylabel('Conditional model density weight'); ax.legend()
        ax.text(.02, .03, 'Other physical weights total < 0.00001\nUnresolved weight < 5×10⁻¹³',
            fontsize=8, transform=ax.transAxes)
    fig.suptitle('Alternatives reweight without a best-label switch\nPhysical prior mass 0.5; point diagnostic, not calibrated identity probabilities.', fontsize=11)
    fig.savefig(OUT / 'model_weights02.png', dpi=180); plt.close(fig)
    bindings = {str(path): sha(path) for path in OUT.iterdir() if path.is_file()}
    bindings[str(Path(__file__))] = sha(__file__)
    for path in [HERE / 'RF_seal.json', HERE / 'report/seal.json']:
        bindings[str(path)] = sha(path)
    with (OUT / 'seal.json').open('x') as stream:
        json.dump(dict(files=bindings, reporting_only=True, new_scientific_evaluations=0), stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(weight_rows=len(weights), discrimination_rows=len(discrimination))))


if __name__ == '__main__':
    main()
