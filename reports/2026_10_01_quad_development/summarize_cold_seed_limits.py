"""Summarize all predeclared cold gates, preserving audit failures."""
import json
from pathlib import Path

import numpy as np
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent
UNITS = ('DS9-B01-S1', 'DS9-B01-D1', 'DS9-B01-Q')


def arm_row(unit, limit, result):
    launch, audit = result['launch'], result['audit_launch']
    evaluation = result.get('evaluation')
    rows = evaluation.get('rows', []) if evaluation else []
    if rows and (len(rows) != 1 or rows[0]['unit'] != unit):
        raise ValueError('Wrong audit binding')
    valid_launches = all(r['returncode'] == 0 and r['within_budget'] and not r['timed_out']
                         for r in (launch, audit))
    accepted = bool(valid_launches and rows and rows[0]['accepted'])
    failures = list(rows[0]['failures']) if rows else ['Missing audit']
    if not valid_launches:
        failures.append('Inference or audit launch failed its process/budget gate')
    return dict(unit=unit, seed_limit=limit, accepted=accepted,
                wall_seconds=launch['elapsed_seconds'],
                cpu_seconds=rows[0]['cpu_s'] if rows else None,
                audit_seconds=audit['elapsed_seconds'],
                error_m=rows[0]['error_m'] if accepted else None,
                failures=failures)


def main():
    output = HERE/'cold-seed-limit-summary-v1.json'
    if output.exists():
        raise FileExistsError(output)
    inputs, rows, comparisons = {}, [], []

    def read(path):
        value = sealed(path)
        inputs[str(path)] = digest(path)
        return value

    for unit in UNITS:
        directory = HERE/'cold-seed-limit-v1'/unit
        result = read(directory/'comparison.json')
        baseline = read(HERE/'independent-v2/DS9-B01'/(unit+'.json'))
        checks = dict(result['equivalence_checks'])
        for limit in (1, 3):
            arm = directory/str(limit)
            r = result['results'][str(limit)]
            freeze = read(arm/'sources.json')
            for mapping in ('source_sha256', 'inputs'):
                for path, expected in freeze[mapping].items():
                    if digest(path) != expected:
                        raise ValueError(f'Changed frozen source/input: {path}')
            launch = read(arm/(unit+'.launch.json'))
            if launch['freeze_sha256'] != digest(arm/'sources.json'):
                raise ValueError('Launch/freeze mismatch')
            audit_launch = read(arm/'audit-launch.json')
            if launch != r['launch'] or audit_launch != r['audit_launch']:
                raise ValueError('Comparison/launch mismatch')
            if (arm/'evaluation.json').exists():
                if read(arm/'evaluation.json') != r['evaluation']:
                    raise ValueError('Comparison/audit mismatch')
            row = arm_row(unit, limit, r)
            if (arm/(unit+'.json')).exists():
                receipt = read(arm/(unit+'.json'))
                if launch['receipt_sha256'] != digest(arm/(unit+'.json')):
                    raise ValueError('Launch/receipt mismatch')
                candidate = receipt['best']
                original = baseline['fits'][0] if limit == 1 else baseline['best']
                checks[f'{limit}_state_matches_saved'] = bool(candidate and np.allclose(candidate['mean'], original['mean'], rtol=0, atol=1e-5))
                checks[f'{limit}_labels_match_saved'] = bool(candidate and candidate['associations'] == original['associations'])
                checks[f'{limit}_objective_matches_saved'] = bool(candidate and abs(candidate['objectives'][-1]-original['objectives'][-1]) < 1e-6)
            rows.append(row)
        comparisons.append(dict(unit=unit, checks=checks, all_checks_pass=bool(checks) and all(checks.values())))
    result = dict(rows=rows, comparisons=comparisons, inputs=inputs,
                  sources={str(Path(__file__).resolve()): digest(__file__)},
                  qualification='Three related DS9 windows, not three independent geographic trials. Fresh processes from prepared inputs; alternating order, no host/cache randomization. Failure errors are null.')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    x = np.arange(3)
    for limit, offset, color in ((1, -.18, 'tab:blue'), (3, .18, 'tab:orange')):
        local = [r for r in rows if r['seed_limit'] == limit]
        axes[0].bar(x+offset, [r['wall_seconds'] for r in local], .36, label=f'{limit} start(s)', color=color)
        for i, row in enumerate(local):
            if row['accepted']:
                axes[1].bar(i+offset, row['error_m'], .36, color=color)
            else:
                axes[1].text(i+offset, 0, 'failed', rotation=90, ha='center')
    axes[0].legend()
    axes[0].set_ylabel('Fresh inference wall time (s)')
    axes[1].set_ylabel('Audited reference error (m)')
    for ax in axes:
        ax.set_xticks(x, ['Single', 'Pair', 'Quad'])
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Start-count ablation: first DS9 block only')
    fig.savefig(HERE/'cold-seed-limit-v1.png', dpi=160)
    print(json.dumps(result['rows'], indent=2))


if __name__ == '__main__':
    main()
