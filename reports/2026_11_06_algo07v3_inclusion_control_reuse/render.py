"""Verify and render prepared complete recovery and duplicate control evidence."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parent
    result = json.loads((root / 'prepared-result.json').read_bytes())
    assert result['exact'] and result['saved_native_audit_exact']
    for name, sha in result['plan']['bindings'].items():
        paths = [Path(name)]
        if '/src/' in name:
            paths.append(root / 'baseline-src' / name.split('/src/', 1)[1])
        if name.endswith('/tools/probe_algo07v3_inclusion_controls.py'):
            paths.append(root / 'measured-probe.py')
        assert any(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == sha
                   for p in paths), name
    rows = result['rows']
    for row in rows:
        assert row['exact']
        assert len(row['controls']) == 4
        assert len({r['key'] for r in row['controls']}) == 1
        assert len({r['complete_output_signature'] for r in row['controls']}) == 1
    metrics = []
    for row in rows:
        metrics.append(dict(side=row['side'], recovery_s=row['seconds'],
                            cpu_s=row['cpu_seconds'],
                            control_s=sum(r['seconds'] for r in row['controls']),
                            key_s=sum(r['key_seconds'] for r in row['controls']),
                            reused=sum(r['reused'] for r in row['controls'])))
    (root / 'prepared-summary.json').write_text(json.dumps(metrics, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    axes[0].bar([r['side'] for r in metrics], [r['recovery_s'] for r in metrics],
                color=['tab:blue', 'tab:orange'])
    axes[0].set_ylabel('Complete prepared recovery: wall seconds')
    for j, row in enumerate(rows):
        axes[1].bar([i+(j-.5)*.35 for i in range(4)],
                    [r['seconds'] for r in row['controls']], width=.35, label=row['side'])
        for i, control in enumerate(row['controls']):
            if control['reused']:
                axes[1].annotate('reused\n~5 ms', (i+(j-.5)*.35, .1),
                                 ha='center', va='bottom', fontsize=9, color='tab:orange')
    axes[1].set_xticks(range(4), ['Target 2', 'Target 4', 'Target 5', 'Target 7'])
    axes[1].set_ylabel('Control pair: wall seconds (key check excluded)')
    axes[1].legend()
    fig.suptitle('DS26-0066: exact reuse of identical inclusion controls')
    fig.savefig(root / 'prepared.png', dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
