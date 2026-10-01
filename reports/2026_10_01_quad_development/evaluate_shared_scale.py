"""Account for six preset pilot arms before separate geographic scoring."""
import importlib.util
from pathlib import Path
import numpy as np
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from regression_batch import verify_sources
from screen_seed_prefix import sealed, digest
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def main():
    inputs = {}; rows = []
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    for unit in UNITS:
        arms = {}
        for arm in ('control', 'shared'):
            directory = HERE/'shared-scale-pilot-v1'/unit/arm
            launch = read(directory/'launch.json')
            value = read(directory/'result.json') if (directory/'result.json').exists() else None
            if value:
                freeze = read(directory/'sources.json'); verify_sources(freeze['source_sha256']); verify_sources(freeze['inputs'])
            arms[arm] = dict(accepted=bool(process_ok(launch) and value and value['audit']['accepted']), result=value, launch=launch)
        rows.append(dict(unit=unit, arms=arms))
    # All preset numeric outcomes bound before reference loading.
    reference = read(HERE/'reference-admission-v1.json'); verify_sources(reference['source_sha256'])
    locations = {r['unit']: r['reference_latlon'] for r in reference['rows']}
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec = importlib.util.spec_from_file_location('shared_geo', helper); geo = importlib.util.module_from_spec(spec); spec.loader.exec_module(geo)
    for row in rows:
        errors = {}
        for arm, record in row['arms'].items():
            value = record['result']
            errors[arm] = geo.distance_m(geo.latlon_from_enu(*value['fit']['mean'][:2]), locations[value['binding']['scans'][0]]) if record['accepted'] else None
        row['errors_m'] = errors
        row['paired_change_m'] = errors['shared']-errors['control'] if all(v is not None for v in errors.values()) else None
    valid = all(r['paired_change_m'] is not None for r in rows)
    changes = [r['paired_change_m'] for r in rows] if valid else []
    result = dict(rows=rows, planned_fits=6, accepted_fits=sum(a['accepted'] for r in rows for a in r['arms'].values()),
        gate_passed=bool(valid and np.median(changes) < 0 and max(changes) <= 1),
        median_paired_change_m=float(np.median(changes)) if valid else None,
        inputs=inputs, sources={str(p): digest(p) for p in (Path(__file__).resolve(), helper)},
        qualification='Three exposed first singles; fixed-identity warm shared-scale pilot. No cold association or heldout claim.')
    verify_sources(inputs); save(HERE/'shared-scale-pilot-evaluation-v1.json', result)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    for i, arm in enumerate(('control', 'shared')):
        ax.bar(np.arange(3)+(i-.5)*.32, [r['errors_m'][arm] if r['errors_m'][arm] is not None else np.nan for r in rows], .32, label=arm)
    ax.set_xticks(range(3), ['DS9', 'DS10', 'DS11']); ax.set_ylabel('Horizontal error against operator reference (m)')
    ax.set_title('Conditional shared residual scale: first single per dataset'); ax.legend(); ax.grid(axis='y', alpha=.2)
    fig.savefig(HERE/'shared-scale-pilot-evaluation-v1.png', dpi=160)
    for row in rows: print(row['unit'], row['errors_m'], row['paired_change_m'])
    print('accepted', result['accepted_fits'], 'gate', result['gate_passed'])


if __name__ == '__main__': main()
