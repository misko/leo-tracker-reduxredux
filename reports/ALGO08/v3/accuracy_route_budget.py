"""Price an accuracy-informed solver choice on three previously scored named packets."""

import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


DATA = Path(__file__).resolve().parent / 'measurements'
PINS = {
    'acquisition-throughput.json': 'fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a',
    'prospective-0155-solver.json.gz': '1b733f5e331df70bad20e1075dff45bdf18ad2070811de859a519c7af4e52b36',
    'prospective-0316-solver.json.gz': 'a253e1733851a84cf6cd08b619e99e82f64de5addf57dd43734ea26bf2f4963b',
    'prospective-0160-partial-pair.json.gz': '4f73e1f275cc884f6a660f24b883fca8deae997a90521de7ffbbecde6142c5b1',
    'prospective-0160-confirmation.json.gz': '69ac592b164395a5942fd5aef9f592b5aa070c15855f8bcb2dec266200d3feff',
}


def read(name):
    data = (DATA / name).read_bytes()
    if sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f'Unexpected receipt for {name}')
    return json.loads(gzip.decompress(data) if name.endswith('.gz') else data)


def prefer_cumulative(errors):
    return all(errors['cumulative'][arm] <= errors['stock'][arm] for arm in ('c0', 'fitted_c'))


def budgets(rows, clock, route):
    """For an odd roster each case crosses 0.5 at its own rate; the middle crossing sets the median."""
    if not rows or len(rows) % 2 == 0:
        raise ValueError('Expected an odd, nonempty diagnostic roster')
    seconds = [r[route if route != 'hindsight' else r['hindsight']][clock] for r in rows]
    allowances = [r['baseline_s'] / 2 - used for r, used in zip(rows, seconds)]
    rates = [r['compressed_MB'] / allowance if allowance > 0 else float('inf')
             for r, allowance in zip(rows, allowances)]
    median_rate = median(rates)
    sum_rate = sum(r['compressed_MB'] for r in rows) / sum(allowances) if sum(allowances) > 0 else float('inf')
    at_weak_rate = [r['compressed_MB'] / 292.39 + used for r, used in zip(rows, seconds)]
    original = sum(r['baseline_s'] for r in rows)
    return dict(median_gate_MB_s=median_rate if median_rate != float('inf') else None,
                summed_gate_MB_s=sum_rate if sum_rate != float('inf') else None,
                at_292_39_MB_s=dict(median_ratio=median(t / r['baseline_s'] for t, r in zip(at_weak_rate, rows)),
                                    summed_ratio=sum(at_weak_rate) / original,
                                    summed_seconds_above_half=sum(at_weak_rate) - original / 2),
                seconds_left_by_case=allowances,
                individual_gate_MB_s=[rate if rate != float('inf') else None for rate in rates])


def study():
    archives = {row['case']: row for row in read('acquisition-throughput.json')['rows']}
    rows = []
    for number in ('0155', '0160', '0316'):
        if number == '0160':
            pair = read('prospective-0160-partial-pair.json.gz')
            confirmed = read('prospective-0160-confirmation.json.gz')
            if not confirmed['reproduced_first_publication'] or pair['runs']['cumulative']['process']['exit_code'] != 1:
                raise ValueError('Expected failed audit followed by equivalent successful publication')
            inputs, runs = pair['original_inputs'], pair['runs'] | {'cumulative': confirmed['candidate']}
            errors = {key: row['horizontal_error_km'] for key, row in pair['runs'].items()}
        else:
            pair = read(f'prospective-{number}-solver.json.gz')
            inputs, runs = pair['inputs'], pair['runs']
            errors = pair['scores'].get('horizontal_error_km') or {
                key: {arm: value['horizontal_error_km'] for arm, value in estimates.items()}
                for key, estimates in pair['scores'].items()}
        case = 'DS30-' + number
        raw = archives[case]
        if case != pair['case'] or inputs['inventory'] != raw['inventory_sha256']:
            raise ValueError('Saved numerical input and historical raw run must share the inventory')
        row = dict(case=case, baseline_s=sum(raw['stages']), compressed_MB=raw['compressed_MB'],
                   raw_initial_residency=raw['initial_residency'], inventory=inputs['inventory'],
                   named_packet=inputs['native_sha256'], horizontal_errors_km=errors,
                   hindsight='cumulative' if prefer_cumulative(errors) else 'stock')
        for key, run in runs.items():
            if (run['process']['exit_code'] != 0 or run['terminal']['decision'] != 'ok'
                    or run['science']['receipt']['decision'] != 'complete'
                    or run['terminal']['native_sha256'].removeprefix('sha256:') != inputs['native_sha256']):
                raise ValueError(f'Incomplete or unmatched saved process for {case} {key}')
            row[key] = dict(saved_elapsed_s=run['process']['elapsed_s'], solve_elapsed_s=run['worker']['solve']['elapsed_s'])
        rows.append(row)
    return dict(sources=PINS, cases=rows, assumptions={clock: {route: budgets(rows, clock, route)
                for route in ('stock', 'cumulative', 'hindsight')} for clock in ('saved_elapsed_s', 'solve_elapsed_s')})


if __name__ == '__main__':
    print(json.dumps(study(), indent=2, allow_nan=False))
