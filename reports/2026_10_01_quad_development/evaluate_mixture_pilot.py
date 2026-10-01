"""Separate post-audit geographic scoring for fixed equal-prior mixture."""
import importlib.util
from pathlib import Path
import numpy as np
from run_window import prepare_window
from check_shared_scale import UNITS
from check_receiver_curvature import save
from screen_seed_prefix import sealed, digest
from regression_batch import verify_sources
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def main():
    inputs = {}; rows = []
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    for unit in UNITS:
        arms = {}
        for arm in ('independent', 'mixture'):
            directory = HERE/'mixture-localization-pilot-v1'/unit/arm
            launch = read(directory/'launch.json')
            value = read(directory/'result.json') if (directory/'result.json').exists() else None
            if value:
                freeze = read(directory/'sources.json'); verify_sources(freeze['source_sha256']); verify_sources(freeze['inputs'])
            arms[arm] = dict(accepted=bool(process_ok(launch) and value and value['audit']['accepted']), result=value, launch=launch)
        rows.append(dict(unit=unit, arms=arms))
    ref = read(HERE/'reference-admission-v1.json'); verify_sources(ref['source_sha256'])
    locations = {r['unit']:r['reference_latlon'] for r in ref['rows']}
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec = importlib.util.spec_from_file_location('mixture_geo', helper); geo = importlib.util.module_from_spec(spec); spec.loader.exec_module(geo)
    for row in rows:
        errors = {}
        for arm, record in row['arms'].items():
            r = record['result']
            errors[arm] = geo.distance_m(geo.latlon_from_enu(*r['fit']['mean'][:2]), locations[r['binding']['scans'][0]]) if record['accepted'] else None
        row['errors_m'] = errors
        row['paired_change_m'] = errors['mixture']-errors['independent'] if all(v is not None for v in errors.values()) else None
    valid = all(r['paired_change_m'] is not None and r['arms']['independent']['result']['control_equivalent'] for r in rows)
    changes = [r['paired_change_m'] for r in rows] if valid else []
    value = dict(rows=rows, accepted_fits=sum(a['accepted'] for r in rows for a in r['arms'].values()), planned_fits=6,
        gate_passed=bool(valid and np.median(changes) < 0 and max(changes) <= 1),
        inputs=inputs, sources={str(p):digest(p) for p in (Path(__file__).resolve(), helper)},
        qualification='Three exposed conditional fixed-identity warm pilots; no cold or heldout claim.')
    verify_sources(inputs); save(HERE/'mixture-localization-evaluation-v1.json', value)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 4.5), constrained_layout=True)
    for i, arm in enumerate(('independent', 'mixture')):
        ax.bar(np.arange(3)+(i-.5)*.34, [r['errors_m'][arm] if r['errors_m'][arm] is not None else np.nan for r in rows], .34, label=arm)
    ax.set_xticks(range(3), ['DS9', 'DS10', 'DS11']); ax.set_ylabel('Horizontal error against operator reference (m)')
    ax.set_title('Equal-prior residual-scale mixture: first-single pilot'); ax.legend(); ax.grid(axis='y', alpha=.2)
    fig.savefig(HERE/'mixture-localization-evaluation-v1.png', dpi=160)
    for r in rows: print(r['unit'], r['errors_m'], r['paired_change_m'])
    print('accepted',value['accepted_fits'],'gate',value['gate_passed'])


if __name__ == '__main__': main()
