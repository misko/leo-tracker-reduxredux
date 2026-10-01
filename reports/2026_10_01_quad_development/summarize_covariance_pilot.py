"""Same-evidence covariance pilot, including the preserved default-covariance arm."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed
from summarize_cold_seed_limits import arm_row

HERE = Path(__file__).resolve().parent
ARMS = ('default_0.5', 'tau10', 'matched_white')


def main():
    output = HERE/'covariance-pilot-summary-v1.json'
    if output.exists():
        raise FileExistsError(output)
    inputs, frozen, rows = {}, {}, []

    def read(path):
        value = sealed(path)
        inputs[str(path)] = digest(path)
        return value

    for dataset in ('DS9', 'DS10', 'DS11'):
        unit = dataset+'-B01-S1'
        arms = {}
        evidence, initial, parent_hash = None, None, None
        for arm in ARMS:
            directory = HERE/'denser-pilot-v1'/unit/'16' if arm == 'default_0.5' else HERE/'covariance-pilot-v1'/unit/arm
            outcome = read(directory/'outcome.json')
            freeze = read(directory/'sources.json')
            for mapping in ('source_sha256', 'inputs'):
                for path, expected in freeze[mapping].items():
                    if path in frozen and frozen[path] != expected:
                        raise ValueError('Inconsistent source/input binding')
                    frozen[path] = expected
            launch, audit_launch = read(directory/(unit+'.launch.json')), read(directory/'audit-launch.json')
            assert launch == outcome['launch'] and audit_launch == outcome['audit_launch']
            assert launch['freeze_sha256'] == digest(directory/'sources.json')
            if (directory/'evaluation.json').exists():
                assert read(directory/'evaluation.json') == outcome['evaluation']
            row = arm_row(unit, arm, outcome)
            row['arm'] = row.pop('seed_limit')
            row.update(original_seconds=launch['original_seconds'], incremental_seconds=launch['incremental_seconds'])
            assert abs(row['wall_seconds']-row['original_seconds']-row['incremental_seconds']) < 1e-8
            path = directory/(unit+'.json')
            if path.exists():
                receipt = read(path)
                assert launch['receipt_sha256'] == digest(path)
                details = receipt['denser_pilot'] if arm == 'default_0.5' else receipt['covariance_pilot']
                parent = read(Path(freeze['parent_receipt']))
                assert details['initial_state'] == parent['best']['mean']
                assert details['parent_sha256'] == digest(freeze['parent_receipt'])
                if evidence is None:
                    evidence, initial, parent_hash = receipt['observations'], details['initial_state'], details['parent_sha256']
                assert (receipt['observations'], details['initial_state'], details['parent_sha256']) == (evidence, initial, parent_hash)
                row.update(iterations=receipt['best']['iterations'], reason=receipt['best']['reason'],
                    points=sum(len(p) for p in receipt['observations']),
                    changed_labels_from_parent=sum(a != b for a,b in zip(receipt['best']['associations'], parent['best']['associations'])))
            arms[arm] = row
        rows.append(dict(unit=unit, arms=arms))
    for path, expected in frozen.items():
        assert digest(path) == expected, path
    result = dict(rows=rows, inputs=inputs, frozen_sources_and_inputs=frozen,
        sources={str(Path(__file__).resolve()): digest(__file__), str(HERE/'summarize_cold_seed_limits.py'): digest(HERE/'summarize_cold_seed_limits.py')},
        qualification='Warm covariance comparison with identical nested16 evidence and original8 initial states, verified by seals. Original work charged. Default covariance fit is historical; no cold speedup or independent geographic validation.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    names = ('Default 0.5 s', 'Correlation 10 s', 'Trace-matched white')
    for arm, label, offset, color in zip(ARMS, names, (-.25, 0, .25), ('gray', 'tab:blue', 'tab:orange')):
        for i, row in enumerate(rows):
            value = row['arms'][arm]
            if value['accepted']:
                axes[0].bar(i+offset, value['error_m'], .25, color=color)
            else:
                axes[0].text(i+offset, 0, 'failed', rotation=90, ha='center')
        axes[1].bar(np.arange(3)+offset, [r['arms'][arm]['wall_seconds'] for r in rows], .25, color=color, label=label)
    axes[0].set_ylabel('Accepted reference error (m)')
    axes[1].set_ylabel('Charged inference time (s)')
    axes[1].axhline(90, color='black', linestyle='--')
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set_xticks(range(3), ['DS9', 'DS10', 'DS11'])
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Fixed sixteen-point covariance pilot: same initial state and evidence')
    fig.savefig(HERE/'covariance-pilot-v1.png', dpi=160)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
