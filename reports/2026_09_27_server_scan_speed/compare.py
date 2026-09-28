"""Compare full scanner evidence, with a strict absolute floating tolerance."""
import argparse
import json
import math
from pathlib import Path
import statistics


def differences(a, b, path='', tolerance=1e-12):
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return [path + ': keys differ']
        return [e for k in a for e in differences(a[k], b[k], path+'/'+k, tolerance)]
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [path + ': length differs']
        return [e for i, (x, y) in enumerate(zip(a, b))
                for e in differences(x, y, path+'/'+str(i), tolerance)]
    if type(a) is float and type(b) is float:
        return [] if math.isclose(a, b, rel_tol=0, abs_tol=tolerance) else [path+': float differs']
    return [] if type(a) is type(b) and a == b else [path+': value differs']


def compare(before, after):
    if not before.get('complete') or not after.get('complete'):
        raise ValueError('incomplete run')
    if before['scope'] != after['scope'] or before['affinity'] != after['affinity']:
        raise ValueError('different workload/affinity')
    if before['backend'] != after['backend'] or before.get('full_analysis', False) != after.get('full_analysis', False):
        raise ValueError('different backend/analysis mode')
    if len(before['cases']) != len(after['cases']):
        raise ValueError('different cohort')
    rows = []
    for a, b in zip(before['cases'], after['cases']):
        if not a['measurements'] or not b['measurements']:
            raise ValueError('missing measurements')
        counts = {(r['acquisition_calls'], r['glrt_calls'])
                  for c in (a, b) for r in c['measurements']}
        if len(counts) != 1:
            raise ValueError('different acquisition/scoring workload')
        for k in ('case_id', 'raw_sha256', 'configuration'):
            if a[k] != b[k]:
                raise ValueError('different input/configuration')
        errors = differences(a['result'], b['result'])
        row = {'case_id': a['case_id'], 'rate_hz': a['rate_hz'],
               'exact_output_equal': a['result'] == b['result'],
               'scientific_passed': not errors, 'errors': errors}
        for metric in ('cpu_s', 'wall_s', 'acquisition_s', 'glrt_s'):
            old = statistics.median(x[metric] for x in a['measurements'])
            new = statistics.median(x[metric] for x in b['measurements'])
            row[metric] = {'before': old, 'after': new, 'speedup': old/new}
        rows.append(row)
    return {'passed': all(r['scientific_passed'] for r in rows),
            'absolute_float_tolerance': 1e-12, 'rows': rows}


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('before', type=Path)
    p.add_argument('after', type=Path); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = compare(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)
