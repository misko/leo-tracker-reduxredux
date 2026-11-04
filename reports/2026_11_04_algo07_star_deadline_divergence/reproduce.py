"""Diagnose DS26-0102's failed qualification; never replace the strict check."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path

from compare_algo07_star_receipts import load_catalogue
from diff_algo07_star_evidence import differences

from leo.cli.algo07_profile import write_new
from leo.contracts.fast_graph_position_v6 import owners
from leo.storage.graph_position_view_v6 import completed_view


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = {}
    for side in ('reference', 'candidate'):
        catalogue, bindings = load_catalogue(args.check / f'{side}-evidence')
        terminals = {}
        for version, algorithm in enumerate(bindings, 1):
            name = 'leo.contracts.fast_graph_position' + (f'_v{version}' if version > 1 else '')
            entry = catalogue[algorithm + '/worker/terminal.json']
            terminal = json.loads(entry['path'].read_text())
            importlib.import_module(name).validate_terminal(
                terminal, input_sha256=bindings[algorithm]['input_sha256'])
            assert terminal['state'] == 'complete'
            terminals[algorithm] = terminal
        terminal = terminals['ALGO07']
        decision = json.loads(catalogue['ALGO03/worker/recovery/decision.json']['path'].read_text())
        elapsed = 0.
        timeline = []
        for stage in decision['stages']:
            elapsed += stage.get('seconds', 0.)
            timeline.append(dict(name=stage['name'], seconds=stage.get('seconds', 0.),
                                 cumulative_stage_seconds=elapsed))
        records[side] = dict(
            bindings=bindings,
            exported_files_rehashed=len(catalogue),
            terminal_hashes={a: catalogue[a + '/worker/terminal.json']['sha256'] for a in bindings},
            selected=completed_view('diagnostic-only', terminal)['selected'],
            owners=owners(terminal),
            decisions={a: t.get('decision') for a, t in terminals.items()},
            algo03_selected_arms=decision['selected']['arms'],
            algo04_selected_arms=terminals['ALGO04']['candidate']['selected']['arms'],
            attempts=[{k: a[k] for k in ('track_id', 'points', 'status')}
                      for a in decision['attempts']],
            recovery_maximum_seconds=decision['maximum_seconds'],
            discovery_budget_seconds=min(600., decision['maximum_seconds'] * .7),
            timeline=timeline)
    assert records['reference']['bindings'] == records['candidate']['bindings']
    # This deliberately limited projection diagnoses outcome impact. It is not
    # an alternative comparator for accepting a failed scientific-work check.
    checked = ('selected', 'owners', 'decisions', 'algo03_selected_arms', 'algo04_selected_arms')
    comparison = {key: list(differences(records['reference'][key], records['candidate'][key]))
                  for key in checked}
    output = dict(kind='algo07-star-deadline-divergence-diagnostic',
                  strict_qualification='FAIL: Process provenance differs',
                  scientific_parity_qualified=False, artifact_parity_qualified=False,
                  compared_fields=list(checked), differences=comparison, records=records)
    args.output.mkdir(parents=True, exist_ok=True)
    write_new(args.output / 'diagnostic.json', output)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.8), layout='constrained')
    for side, color in [('reference', '#2166ac'), ('candidate', '#d6604d')]:
        rows = records[side]['timeline']
        prefix = rows[:next(i for i, r in enumerate(rows) if r['name'] == 'joint-probe')]
        ax.plot(range(1, len(prefix)+1), [r['cumulative_stage_seconds'] for r in prefix],
                marker='o', label=side.title(), color=color)
        before = next(r for r in rows if r['name'] == 'target-4-retry-audit')
        ax.annotate(f"{side}: {before['cumulative_stage_seconds']:.3f} s",
                    (16, before['cumulative_stage_seconds']),
                    xytext=(9, 500 if side == 'reference' else 700),
                    arrowprops={'arrowstyle': '->', 'color': color}, color=color)
    ax.axhline(600, color='black', linestyle='--', label='600 s discovery admission limit')
    ax.set(xlabel='Completed recovery stage count', ylabel='Sum of recorded stage durations (s)',
           title='DS26-0102: unchanged workers cross a discovery-time boundary', ylim=(0, 760))
    ax.grid(alpha=.2)
    ax.legend(loc='upper left')
    fig.text(.5, -.035, 'Stage sums exclude bookkeeping. Admission uses elapsed wall time; '
             'this is not a speed benchmark.',
             ha='center', fontsize=9)
    fig.savefig(args.output / 'discovery-boundary.png', dpi=160, bbox_inches='tight')
    plt.close(fig)
    summary = dict(strict_qualification=output['strict_qualification'],
                   diagnostic_equal={k: not v for k, v in comparison.items()},
                   final_endpoints={a: v['endpoint_latlon']
                                    for a, v in records['reference']['selected']['arms'].items()},
                   owner_counts={a: len(v) for a, v in records['reference']['owners'].items()},
                   diagnostic_sha256=hashlib.sha256(
                       (args.output / 'diagnostic.json').read_bytes()).hexdigest())
    write_new(args.output / 'summary.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
