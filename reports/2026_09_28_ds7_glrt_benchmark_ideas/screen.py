"""Retrospective evidence screen only; no execution-speed measurement."""
import copy
import json
from pathlib import Path
import sys

BENCH = Path(__file__).resolve().parents[1] / '2026_09_28_ds7_glrt_benchmark'
sys.path.insert(0, str(BENCH))
from scoring import score

rows = [json.loads(line) for line in (BENCH / 'run-01/rows.jsonl').read_text().splitlines()]
reference = [r for r in rows if r['method'] == 'original' and r['repeat'] == 0
             and r['context']['rate_hz'] == 2500000]
designs = [('rank4', 4, None), ('rank6', 6, None),
           ('6windows', 8, {0, 2, 4, 6, 8, 10}),
           ('4windows', 8, {0, 3, 6, 9}), ('3windows', 8, {0, 5, 10}),
           ('6windows_rank2', 2, {0, 2, 4, 6, 8, 10}),
           ('4windows_rank2', 2, {0, 3, 6, 9})]
output = {'scope': 'Retrospective filtering of original outputs, not rerun algorithms or measured speed. '
          'Confirmation metrics recomputed from retained evidence; original first/best result fields '
          'are not updated and must not be used for equivalence. Exposed 16-visit development cohort.',
          'designs': {}}
for name, count, indices in designs:
    candidate = copy.deepcopy(reference)
    for row in candidate:
        row['result']['probes'] = [p for p in row['result']['probes']
                                  if indices is None or p['probe_index'] in indices]
        for probe in row['result']['probes']:
            probe['candidates'] = probe['candidates'][:count]
    output['designs'][name] = {
        'candidate_count': count, 'probe_indices': sorted(indices) if indices else list(range(11)),
        'recovery': score(reference, candidate)['recovery']}
print(json.dumps(output, indent=2))
