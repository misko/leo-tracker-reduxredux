"""Report computational equivalence without relabeling rejected fits as accepted."""
import json
from pathlib import Path
import numpy as np
from screen_seed_prefix import digest, sealed
from failure_composition_checks import comparison_checks, process_ok

HERE = Path(__file__).resolve().parent
UNITS = ('DS9-B05-S2', 'DS9-B05-S3', 'DS11-B04-S1')


def main():
    output = HERE/'failure-composition-summary-v1.json'
    if output.exists():
        raise FileExistsError(output)
    inputs, frozen, rows = {}, {}, []

    def read(path):
        value = sealed(path)
        inputs[str(path)] = digest(path)
        return value

    for unit in UNITS:
        directory = HERE/'failure-composition-cold-v1'/unit
        parent = read(HERE/'independent-v2'/unit.rsplit('-', 1)[0]/(unit+'.json'))
        comparison = read(directory/'comparison.json')
        receipts, arms = {}, {}
        for arm in ('original', 'blas'):
            folder = directory/arm
            freeze = read(folder/'sources.json')
            for key in ('source_sha256', 'inputs'):
                for name, expected in freeze[key].items():
                    assert name not in frozen or frozen[name] == expected
                    frozen[name] = expected
            launch = read(folder/(unit+'.launch.json'))
            audit = read(folder/'audit-launch.json')
            assert launch == comparison['outcomes'][arm]['launch']
            assert audit == comparison['outcomes'][arm]['audit_launch']
            assert launch['freeze_sha256'] == digest(folder/'sources.json')
            evaluation = read(folder/'evaluation.json') if (folder/'evaluation.json').exists() else None
            assert evaluation == comparison['outcomes'][arm]['evaluation']
            path = folder/(unit+'.json')
            receipt = read(path) if path.exists() else None
            receipts[arm] = receipt
            if receipt is not None:
                assert digest(path) == launch['receipt_sha256']
            fit = (receipt or {}).get('best') or {}
            row = evaluation['rows'][0] if evaluation and len(evaluation['rows']) == 1 else {}
            arms[arm] = dict(processes_completed=process_ok(launch) and process_ok(audit),
                accepted=row.get('accepted', False), failures=row.get('failures'),
                error_m=row.get('error_m'), status=(receipt or {}).get('status'),
                reason=fit.get('reason'), iterations=fit.get('iterations'),
                wall_seconds=launch['elapsed_seconds'], cpu_seconds=(receipt or {}).get('cpu_seconds'),
                audit_seconds=audit['elapsed_seconds'])
        checks = comparison_checks(receipts, parent, comparison['outcomes'])
        assert checks == comparison['checks']
        valid = all(checks.values())
        assert valid == comparison['failure_preserved']
        row = dict(unit=unit, arms=arms, checks=checks, failure_preserved=valid)
        if valid:
            row.update(observed_wall_saving_fraction=1-arms['blas']['wall_seconds']/arms['original']['wall_seconds'],
                observed_cpu_saving_fraction=1-arms['blas']['cpu_seconds']/arms['original']['cpu_seconds'],
                maximum_state_difference=float(np.max(np.abs(np.array(receipts['original']['best']['mean'])
                    -np.array(receipts['blas']['best']['mean'])))),
                maximum_history_difference=float(np.max(np.abs(np.array(receipts['original']['best']['objectives'])
                    -np.array(receipts['blas']['best']['objectives'])))))
        rows.append(row)
    for name, expected in frozen.items():
        assert digest(name) == expected, name
    result = dict(rows=rows, inputs=inputs, frozen_sources_and_inputs=frozen,
        sources={str(p): digest(p) for p in (Path(__file__).resolve(), HERE/'failure_composition_checks.py')},
        qualification='Three failure-selected singles, six cold outcomes. Computational equivalence '
        'is distinct from numerical acceptance. Unresolved states have no geographic error. '
        'Fixed alternating orders and one timing observation per arm; no general speed guarantee.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for arm, label, offset, color in (
        ('original', 'Original acquisition', -.18, 'tab:blue'),
        ('blas', 'Optimized acquisition', .18, 'tab:orange'),
    ):
        x = np.arange(3)+offset
        axes[0].bar(x, [r['arms'][arm]['wall_seconds'] for r in rows], .36, label=label, color=color)
        for j, r in enumerate(rows):
            value = r['arms'][arm]['iterations']
            if value is not None:
                axes[1].bar(x[j], value, .36, color=color)
            else:
                axes[1].text(x[j], 0, 'missing', rotation=90, ha='center')
    axes[0].legend(); axes[0].set_ylabel('Cold inference wall time (s)')
    axes[1].set_ylabel('Iterations used'); axes[1].axhline(64, color='black', ls='--', label='Fixed limit')
    axes[1].legend()
    for ax in axes:
        ax.set_xticks(np.arange(3), UNITS); ax.grid(axis='y', alpha=.2)
    fig.suptitle('Failure-selected singles: computational checks do not imply convergence')
    fig.savefig(output.with_suffix('.png'), dpi=160)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
