"""Limited outcome and admission diagnostic; never waives a strict failure."""
import argparse
import importlib
import json
from pathlib import Path

from compare_algo07_star_receipts import load_catalogue
from diff_algo07_star_evidence import differences

from leo.cli.algo07_profile import digest, write_new
from leo.contracts.fast_graph_position_v6 import owners
from leo.storage.graph_position_view_v6 import completed_view

parser = argparse.ArgumentParser(description=__doc__)
for key in ('reference', 'candidate', 'output'):
    parser.add_argument('--' + key, type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(exist_ok=False)
records = {}
for side in ('reference', 'candidate'):
    root = getattr(args, side)
    catalogue, bindings = load_catalogue(root)
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
    decision_entry = catalogue['ALGO03/worker/recovery/decision.json']
    decision = json.loads(decision_entry['path'].read_text())
    elapsed, timeline = 0., []
    for stage in decision['stages']:
        elapsed += stage.get('seconds', 0.)
        timeline.append(dict(name=stage['name'], status=stage['status'],
                             seconds=stage.get('seconds', 0.),
                             cumulative_stage_seconds=elapsed))
    records[side] = dict(
        bindings=bindings, exported_files_rehashed=len(catalogue),
        terminal_hashes={a: catalogue[a + '/worker/terminal.json']['sha256'] for a in bindings},
        decision_sha256=decision_entry['sha256'],
        selected=completed_view('diagnostic-only', terminal)['selected'],
        owners=owners(terminal), decisions={a: t.get('decision') for a, t in terminals.items()},
        attempts=[{k: attempt[k] for k in ('track_id', 'points', 'status')}
                  for attempt in decision['attempts']],
        recovery_maximum_seconds=decision['maximum_seconds'],
        discovery_budget_seconds=min(600., decision['maximum_seconds'] * .7), timeline=timeline)
assert records['reference']['bindings'] == records['candidate']['bindings']
compared = ('selected', 'owners', 'decisions')
delta = {key: list(differences(records['reference'][key], records['candidate'][key]))
         for key in compared}
result = dict(kind='algo07-star-limited-work-diagnostic',
              scientific_parity_qualified=False, artifact_parity_qualified=False,
              strict_comparison_unchanged=True, compared_fields=list(compared),
              source_roots={s: str(getattr(args, s).resolve()) for s in records},
              script_sha256=digest(Path(__file__)), records=records, differences=delta)
write_new(args.output / 'diagnostic.json', result)
summary = dict(diagnostic_equal={k: not v for k, v in delta.items()},
               scientific_parity_qualified=False, strict_comparison_unchanged=True,
               diagnostic_sha256=digest(args.output / 'diagnostic.json'),
               sides={s: dict(attempts=r['attempts'], timeline=r['timeline'],
                              recovery_maximum_seconds=r['recovery_maximum_seconds'],
                              owner_counts={a: len(ids) for a, ids in r['owners'].items()},
                              endpoints={a: v['endpoint_latlon']
                                         for a, v in r['selected']['arms'].items()})
                      for s, r in records.items()})
write_new(args.output / 'summary.json', summary)
print(json.dumps(summary, indent=2))
