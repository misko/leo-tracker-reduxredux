"""Matched warm evidence-density outcomes; preserve every planned failure."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed
from summarize_cold_seed_limits import arm_row

HERE = Path(__file__).resolve().parent
UNITS = ('DS9-B01-S1', 'DS10-B01-S1', 'DS11-B01-S1')


def main():
    output = HERE/'denser-pilot-summary-v1.json'
    if output.exists():
        raise FileExistsError(output)
    inputs, frozen, rows = {}, {}, []

    def read(path):
        value = sealed(path)
        inputs[str(path)] = digest(path)
        return value

    for unit in UNITS:
        pair = {}
        for limit in (8, 16):
            directory = HERE/'denser-pilot-v1'/unit/str(limit)
            outcome = read(directory/'outcome.json')
            freeze = read(directory/'sources.json')
            for mapping in ('source_sha256', 'inputs'):
                for path, expected in freeze[mapping].items():
                    if path in frozen and frozen[path] != expected:
                        raise ValueError('Inconsistent source or input binding')
                    frozen[path] = expected
            launch = read(directory/(unit+'.launch.json'))
            audit_launch = read(directory/'audit-launch.json')
            assert launch == outcome['launch'] and audit_launch == outcome['audit_launch']
            assert launch['freeze_sha256'] == digest(directory/'sources.json')
            if (directory/'evaluation.json').exists():
                assert read(directory/'evaluation.json') == outcome['evaluation']
            row = arm_row(unit, limit, outcome)
            row['point_limit'] = row.pop('seed_limit')
            row['original_seconds'] = launch['original_seconds']
            row['incremental_seconds'] = launch['incremental_seconds']
            assert abs(row['wall_seconds']-row['original_seconds']-row['incremental_seconds']) < 1e-8
            if (directory/(unit+'.json')).exists():
                receipt = read(directory/(unit+'.json'))
                assert launch['receipt_sha256'] == digest(directory/(unit+'.json'))
                assert receipt['denser_pilot']['point_limit'] == limit
                parent = read(Path(freeze['parent_receipt']))
                assert receipt['denser_pilot']['initial_state'] == parent['best']['mean']
                assert receipt['denser_pilot']['parent_sha256'] == digest(freeze['parent_receipt'])
                row['iterations'] = receipt['best']['iterations']
                row['reason'] = receipt['best']['reason']
                row['points'] = sum(len(p) for p in receipt['observations'])
                row['changed_labels_from_parent'] = sum(a != b for a, b in zip(receipt['best']['associations'], parent['best']['associations']))
                row['parent_sha256'] = digest(freeze['parent_receipt'])
                row['selected_ids'] = receipt['observations']
            pair[str(limit)] = row
        if all('selected_ids' in r for r in pair.values()):
            assert pair['8']['parent_sha256'] == pair['16']['parent_sha256']
            assert len(pair['8']['selected_ids']) == len(pair['16']['selected_ids'])
            assert all(set(a) <= set(b) for a, b in zip(pair['8']['selected_ids'], pair['16']['selected_ids']))
        pair['error_change_m'] = pair['16']['error_m']-pair['8']['error_m'] if all(pair[str(l)]['accepted'] for l in (8, 16)) else None
        rows.append(dict(unit=unit, **pair))
    for path, expected in frozen.items():
        assert digest(path) == expected, path
    result = dict(rows=rows, inputs=inputs, frozen_sources_and_inputs=frozen,
        sources={str(Path(__file__).resolve()): digest(__file__),
                 str(HERE/'summarize_cold_seed_limits.py'): digest(HERE/'summarize_cold_seed_limits.py')},
        qualification='Three exposed singles; warm refits from identical original states, original inference charged. No cross-dimension objective comparison, no cold-runtime or geographic generalization claim.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for limit, offset, color in ((8, -.18, 'tab:blue'), (16, .18, 'tab:orange')):
        for i, row in enumerate(rows):
            arm = row[str(limit)]
            if arm['accepted']:
                axes[0].bar(i+offset, arm['error_m'], .36, color=color)
            else:
                axes[0].text(i+offset, 0, 'failed', rotation=90, ha='center')
        axes[1].bar(np.arange(3)+offset, [r[str(limit)]['wall_seconds'] for r in rows], .36,
                    label=f'{limit}-point cap', color=color)
    axes[0].set_ylabel('Accepted reference error (m)')
    axes[1].set_ylabel('Charged inference time (s)')
    axes[1].axhline(90, linestyle='--', color='black')
    axes[1].legend()
    for ax in axes:
        ax.set_xticks(range(3), ['DS9', 'DS10', 'DS11'])
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Nested 8-versus-16 evidence pilot: warm fits, same initial state')
    fig.savefig(HERE/'denser-pilot-v1.png', dpi=160)
    print(json.dumps([{k: ({a:b for a,b in v.items() if a != 'selected_ids'} if isinstance(v,dict) else v)
                       for k,v in r.items()} for r in rows], indent=2))


if __name__ == '__main__':
    main()
