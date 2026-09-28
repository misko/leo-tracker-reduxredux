"""Summarize completed saved-IQ candidates and exact scientific parity."""
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'concurrent'))
from summarize import receiver_science


def summarize(directory):
    completion = json.loads((directory / 'completion.json').read_text())
    if not isinstance(completion, dict) or not completion.get('complete') or not completion.get('passed'):
        raise ValueError('incomplete or failed candidate')
    rows = json.loads((directory / 'assessments.json').read_text())
    if not isinstance(rows, list) or completion.get('cases') != len(rows):
        raise ValueError('assessment count')
    groups = {}
    checked = matched = 0
    case_ids = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get('passed'):
            raise ValueError('failed assessment')
        case_id = row['case_id']
        if case_id in case_ids:
            raise ValueError('duplicate case')
        case_ids.add(case_id)
        current = json.loads((directory / (case_id + '.json')).read_text())
        ref = HERE.parent / 'target_run_01' / (case_id + '-D.json')
        if not ref.exists():
            ref = HERE.parent / 'target_run_02_10m' / (case_id + '-D.json')
        expected = json.loads(ref.read_text())['repetitions'][0]['receivers']
        for repetition in current['repetitions']:
            if len(repetition['receivers']) != len(expected):
                raise ValueError('receiver count')
            for actual, wanted in zip(repetition['receivers'], expected):
                checked += 1
                matched += receiver_science(actual) == receiver_science(wanted)
        key = str(current['rate_hz']) + ('_control' if case_id.startswith('control-') else '_real')
        groups.setdefault(key, []).append(row)
    if not checked:
        raise ValueError('no science comparisons')
    return {'directory': str(directory.relative_to(HERE)), 'completion': completion,
            'exact_science': {'checked': checked, 'matched': matched, 'passed': checked == matched},
            'groups': {key: {'cases': len(rows),
                 'reference_cpu_ms': statistics.fmean(r['reference_cost']['total_cpu_ms'] for r in rows),
                 'candidate_cpu_ms': statistics.fmean(r['candidate_cost']['total_cpu_ms'] for r in rows)}
                 for key, rows in groups.items()}}


if __name__ == '__main__':
    results = [summarize(Path(arg).resolve()) for arg in sys.argv[1:]]
    print(json.dumps(results, indent=2))
