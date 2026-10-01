"""Report cap-only recovery and unchanged controls, with historical timing labeled."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed
from summarize_cold_seed_limits import arm_row
from iteration96_checks import compare

HERE = Path(__file__).resolve().parent
CONTROLS = ('DS9-B01-S1', 'DS10-B01-S1', 'DS11-B01-S1')
FAILURES = ('DS9-B05-S2', 'DS9-B05-S3', 'DS11-B04-S1')


def main():
    output = HERE/'iteration96-summary-v1.json'
    if output.exists():
        raise FileExistsError(output)
    rows, inputs, frozen = [], {}, {}

    def read(path):
        value = sealed(path); inputs[str(path)] = digest(path); return value

    for unit in CONTROLS+FAILURES:
        directory = HERE/'iteration96-v1'/unit
        comparison = read(directory/'comparison.json')
        parent_file = Path(comparison['parent_path'])
        parent = read(parent_file)
        assert digest(parent_file) == comparison['parent_sha256']
        arms, receipts = {}, {}
        for cap, folder in ((64, parent_file.parent), (96, directory)):
            freeze = read(folder/'sources.json')
            for key in ('source_sha256', 'inputs'):
                for name, expected in freeze[key].items():
                    assert name not in frozen or frozen[name] == expected
                    frozen[name] = expected
            launch = read(folder/(unit+'.launch.json'))
            audit = read(folder/'audit-launch.json')
            evaluation = read(folder/'evaluation.json') if (folder/'evaluation.json').exists() else None
            assert launch['freeze_sha256'] == digest(folder/'sources.json')
            path = folder/(unit+'.json')
            receipt = read(path) if path.exists() else None
            receipts[cap] = receipt
            if receipt is not None:
                assert digest(path) == launch['receipt_sha256']
            outcome = dict(launch=launch, audit_launch=audit, evaluation=evaluation)
            if cap == 96:
                assert all(outcome[k] == comparison[k] for k in outcome)
            row = arm_row(unit, cap, outcome)
            row['max_iterations'] = row.pop('seed_limit')
            best = (receipt or {}).get('best') or {}
            row.update(iterations=best.get('iterations'), reason=best.get('reason'))
            arms[str(cap)] = row
        checks = compare(parent, receipts[96])
        assert checks == comparison['checks']
        assert arms['96']['accepted'] == comparison['accepted']
        row = dict(unit=unit, cohort='successful_control' if unit in CONTROLS else 'unresolved_case',
                   arms=arms, checks=checks, policy_checks_pass=comparison['policy_equivalent'])
        best = (receipts[96] or {}).get('best')
        if best:
            old = parent['best']
            assert len(best['associations']) == len(old['associations'])
            row['endpoint_assignment_changes'] = sum(a != b for a, b in zip(best['associations'], old['associations']))
            row['local_position_change_m'] = float(1000*np.linalg.norm(np.asarray(best['mean'][:2])-old['mean'][:2]))
        rows.append(row)
    for name, expected in frozen.items():
        assert digest(name) == expected, name
    result = dict(rows=rows, inputs=inputs, frozen_sources_and_inputs=frozen,
        sources={str(p): digest(p) for p in (Path(__file__).resolve(), HERE/'summarize_cold_seed_limits.py',
                                            HERE/'iteration96_checks.py', HERE/'failure_composition_checks.py')},
        qualification='Six exposed development singles: three successful controls and three failure-selected cases. '
        '96 iterations retain the original total budget and physical model. 64-iteration timing is historical. '
        'Numerical acceptance precedes error scoring; no full-panel fresh runtime or acceptance claim.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    errors = [a['error_m'] for r in rows for a in r['arms'].values() if a['accepted']]
    floor = min([100.] + [x*.5 for x in errors])
    for cap, label, offset, color in (
        ('64', '64 iterations (archived)', -.15, 'tab:blue'),
        ('96', '96 iterations (fresh)', .15, 'tab:orange'),
    ):
        for j, r in enumerate(rows):
            a = r['arms'][cap]; x = j+offset
            if a['iterations'] is not None:
                axes[0].bar(x, a['iterations'], .3, color=color, label=label if j == 0 else None)
            if a['accepted']:
                axes[1].scatter(x, a['error_m'], color=color, s=45, label=label if j == 0 else None)
            else:
                axes[1].text(x, floor, 'rejected', color=color, rotation=90, va='bottom', ha='center', fontsize=8)
    axes[0].axhline(64, color='gray', ls='--'); axes[0].axhline(96, color='gray', ls=':')
    axes[0].set_ylabel('Iterations used'); axes[0].legend(fontsize=9)
    axes[1].set_yscale('log'); axes[1].set_ylim(bottom=floor*.8)
    axes[1].set_ylabel('Accepted reference error (m, log scale)'); axes[1].legend(fontsize=9)
    for ax in axes:
        ax.set_xticks(np.arange(6), CONTROLS+FAILURES, rotation=35, ha='right')
        ax.axvline(2.5, color='gray', alpha=.4); ax.grid(axis='y', alpha=.2)
    fig.suptitle('More iterations: numerical acceptance and geographic accuracy are separate')
    fig.savefig(output.with_suffix('.png'), dpi=160)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
