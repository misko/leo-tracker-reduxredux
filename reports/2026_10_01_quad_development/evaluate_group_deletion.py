"""Separate geographic evaluation after all group choices and fits are sealed."""
import importlib.util
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from screen_seed_prefix import sealed, digest
from regression_batch import verify_sources
from check_receiver_curvature import save
from failure_composition_checks import process_ok

HERE = Path(__file__).resolve().parent


def main():
    inputs = {}
    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value
    summary = read(HERE/'group-deletion-summary-v1.json')
    verify_sources(summary['sources']); verify_sources(summary['inputs'])
    assert summary['planned'] == summary['accepted'] == 18
    pairs = {}
    for row in summary['rows']:
        unit = row['unit']; arm = row['arm']; directory = HERE/'group-deletion-v1'/unit/arm
        freeze = read(directory/'sources.json'); verify_sources(freeze['source_sha256']); verify_sources(freeze['inputs'])
        assert process_ok(read(directory/'launch.json'))
        result = read(directory/'result.json'); assert result == row['result'] and result['audit']['accepted']
        pairs.setdefault(unit, {})[arm] = result
    parents = {}
    for unit, arms in pairs.items():
        assert set(arms) == {'fixed', 'reassigned'}
        assert arms['fixed']['fit']['mean'] == arms['reassigned']['fit']['mean']
        campaign = 'one-start-blas-cold-v1' if unit.endswith('S1') else 'one-start-blas-window-cold-v1'
        directory = HERE/campaign/unit/'blas'
        parent = read(directory/(unit+'.json')); audit = read(directory/'evaluation.json')
        assert len(audit['rows']) == 1 and audit['rows'][0]['accepted']
        assert audit['rows'][0]['receipt_sha256'] == digest(directory/(unit+'.json'))
        parents[unit] = parent
    # Choices and numeric acceptance verified before accessing the geographic reference.
    reference = read(HERE/'reference-admission-v1.json'); verify_sources(reference['source_sha256'])
    locations = {r['unit']: r['reference_latlon'] for r in reference['rows']}
    helper = HERE.parent/'2026_10_01_fixed_height_greedy/evaluate.py'
    assert digest(helper) == 'sha256:55ccf852beafb7b88f118c23978edab0aa398ce3a2cbe8607851a964173424a5'
    spec = importlib.util.spec_from_file_location('group_geo', helper); geo = importlib.util.module_from_spec(spec); spec.loader.exec_module(geo)
    rows = []
    for unit, arms in pairs.items():
        parent = parents[unit]; references = [locations[s] for s in parent['binding']['scans']]
        assert all(r == references[0] for r in references)
        base = geo.distance_m(geo.latlon_from_enu(*parent['best']['mean'][:2]), references[0])
        errors = {arm: geo.distance_m(geo.latlon_from_enu(*value['fit']['mean'][:2]), references[0]) for arm, value in arms.items()}
        assert errors['fixed'] == errors['reassigned']
        rows.append(dict(unit=unit, size=parent['binding']['size'], baseline_error_m=base,
            deletion_error_m=errors['fixed'], paired_change_m=errors['fixed']-base, arm_errors_m=errors,
            selected_group=arms['fixed']['selected_group']))
    stats = {}
    for size in (1, 2, 4):
        local = [r for r in rows if r['size'] == size]; assert len(local) == 3
        changes = np.asarray([r['paired_change_m'] for r in local])
        stats[str(size)] = dict(n=3, baseline_median_m=float(np.median([r['baseline_error_m'] for r in local])),
            deletion_median_m=float(np.median([r['deletion_error_m'] for r in local])), median_paired_change_m=float(np.median(changes)),
            improves_over_1m=int(np.sum(changes < -1)), worsens_over_1m=int(np.sum(changes > 1)))
    sources = {str(p): digest(p) for p in (Path(__file__).resolve(), helper, HERE/'GROUP_DELETION_EVALUATION_PLAN.md')}
    verify_sources(inputs); verify_sources(sources)
    result = dict(rows=rows, summary=stats, inputs=inputs, sources=sources,
        qualification='Nine exposed overlapping development windows,18accepted duplicate-arm fits. Unsurveyed operator reference. No group reselection, refits or heldout accuracy claim.')
    save(HERE/'group-deletion-evaluation-v1.json', result)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4.7), constrained_layout=True)
    x = np.arange(len(rows))
    ax.bar(x-.18, [r['baseline_error_m'] for r in rows], .36, label='Baseline', color='#517fa4')
    ax.bar(x+.18, [r['deletion_error_m'] for r in rows], .36, label='Delete highest-influence group', color='#ce8637')
    ax.set_xticks(x, [r['unit'].replace('-B01-', '\n') for r in rows]); ax.set_ylabel('Horizontal error against operator reference (m)')
    ax.set_title('Frozen group deletion: both refit arms give identical positions'); ax.legend(); ax.grid(axis='y', alpha=.2)
    fig.savefig(HERE/'group-deletion-evaluation-v1.png', dpi=160)
    print(json.dumps(result['rows'], indent=2)); print(json.dumps(stats, indent=2))


if __name__ == '__main__': main()
