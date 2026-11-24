"""Price regional horizon admission using already sealed raw clocks and saved traces."""

import gzip
import json
from hashlib import sha256
from math import fsum, isfinite
from pathlib import Path
from statistics import median


REPORT = Path(__file__).resolve().parent
RELEASE = Path('/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo')
RAW = {
    'DS30-0016': ('leo-v3-history-risk-0016-raw-score02.json',
                  '920456558c3b3ed29fcad552ee9b369b1b5ca0fda456211b85c6ee73748f662f'),
    'DS30-0107': ('leo-v3-history-risk-0107-score01.json',
                  '19a54239fad54185b0cf18bbf5b75b4cb8981e3be101087ddb53005d5c5d40e3'),
}
EVIDENCE = {
    'census': ('acquisition-throughput.json', 'fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a'),
    'weak_saved': ('live-orbit-setup-audit.json', '4ffa145b0770faed152948dc3de367746a7e805f4586f32290929cd5d7ceb336'),
    'medium_profile': ('named-shared-cpu-0316.json.gz', '7a95b522bfbb822f92133d9e9536a61095bb11a4251a7a676288129d64c72b47'),
}
SOURCE = {
    'analysis/localization_v3/orbits.py': '6d2b3db52f68abb93bd3a72211e6e8bc6030d5b939981287922a2beebc4f028d',
    'sky/frames.py': 'b6c98c11d25957c8f535d09a4f4cc47f3f82745b63ca57c61f9e8d5949fbb8e0',
}


def checked(path, expected):
    payload = path.read_bytes()
    if sha256(payload).hexdigest() != expected:
        raise ValueError(f'Unrecognized evidence at {path}')
    return payload


def ratios(reference, contender):
    pairs = list(zip(reference, contender, strict=True))
    if not pairs or any(not (isfinite(run) and run >= 0 and isfinite(stock) and stock > 0) for stock, run in pairs):
        raise ValueError('Expected positive reference and nonnegative contender elapsed times')
    stock_s = fsum(stock for stock, _ in pairs)
    contender_s = fsum(run for _, run in pairs)
    return dict(reference_s=stock_s, contender_s=contender_s, relative_total=contender_s/stock_s,
                median_paired_ratio=median(run/stock for stock, run in pairs),
                positive_gap_to_half_s=max(0., contender_s-stock_s/2))


def raw_case(score):
    if not score['qualified'] or not score['same_opportunities']:
        raise ValueError('Expected qualified raw pair')
    receipt = {}
    for name, arm in score['runs'].items():
        process = score['measured_exits'][name]
        clock, cache = process['clock'], process['cache_before']
        if clock['exit_code'] or any(
            record['unavailable'] or not 0 < record['cached_pages'] == record['observed_file_pages']
            or not 0 < record['observed_members'] == record['members'] for record in (cache, cache['index_cache'])
        ):
            raise ValueError('Expected completed warm raw pair')
        decision = arm['science']['receipt']['decision']
        counts = arm['science']['receipt']['counts']
        receipt[name] = dict(clock={field: clock[field] for field in ('cpu_s', 'elapsed_s', 'input_blocks')},
                             decision=decision, reason=arm['science']['reason'], figures=len(arm['figures']),
                             issued=counts['processed']+counts['invalid_capture'], admitted=counts['processed'],
                             payload_pages=cache['cached_pages'], index_pages=cache['index_cache']['cached_pages'])
    candidate = score['runs']['candidate']
    route = candidate['route']
    if not route and receipt['candidate']['reason'] != 'no_active_curvature':
        raise ValueError('Unexplained absence of numerical route accounting')
    history = route['history'] if route else None
    scopes = {}
    for name in ('prepare', 'infer'):
        samples = history[name] if history else []
        if any(s['status'] != 'returned' for s in samples):
            raise ValueError(f'Incomplete {name} accounting')
        scopes[name] = {field[:-3]+'_s': sum(s[field] for s in samples)/1e9 for field in ('elapsed_ns', 'cpu_ns')}
    scopes.update({name: candidate['phases'][name] for name in ('authenticated_raw_acquisition', 'decision_and_publication')})
    if fsum(scopes[name]['elapsed_s'] for name in ('prepare', 'infer')) > scopes['decision_and_publication']['elapsed_s']:
        raise ValueError('Nested numerical stages exceed their enclosing phase')
    return dict(case=score['case'], **receipt, candidate_scopes=scopes)


def raw_envelope(rows):
    baseline = [row['stock']['clock']['elapsed_s'] for row in rows]
    actual = [row['candidate']['clock']['elapsed_s'] for row in rows]
    summary = dict(actual=ratios(baseline, actual))
    for label, scope_names in (('free_preparation', ('prepare',)), ('free_prepare_and_infer', ('prepare', 'infer'))):
        remaining = [elapsed - fsum(row['candidate_scopes'][name]['elapsed_s'] for name in scope_names)
                     for row, elapsed in zip(rows, actual, strict=True)]
        summary[label] = dict(**ratios(baseline, remaining), remaining_s_by_case=dict(zip(
            (row['case'] for row in rows), remaining, strict=True)))
    return summary


def historical_envelope(rows):
    stages = {'acquisition': [], 'solve': [], 'publication': []}
    unsplit = {}
    baseline, no_solve = [], []
    seen = set()
    for row in rows:
        case = row['case']
        acquisition, solve, tail = row['stages']
        if case in seen or any(not (isfinite(value) and value >= 0) for value in row['stages']) or tail <= 0:
            raise ValueError('Invalid or repeated historical stage clock')
        seen.add(case)
        if acquisition > 0 and solve > 0:
            for label, value in zip(stages, row['stages'], strict=True):
                stages[label].append(value)
        elif acquisition == solve == 0:
            unsplit[case] = tail
        else:
            raise ValueError('Missing one member of a split stage clock')
        baseline.append(fsum(row['stages']))
        no_solve.append(acquisition+tail)
    split_totals = {label: fsum(values) for label, values in stages.items()}
    split_total = fsum(split_totals.values())
    return dict(cases=len(rows), splits=len(stages['solve']), unsplit_elapsed_s=unsplit,
                split_wall_shares={name: total/split_total for name, total in split_totals.items()},
                free_solve=ratios(baseline, no_solve))


def profiled_outer_ceiling(document):
    leaves = document['profile']['profiles']['leaves']
    out = {}
    for kernel, caller, count in (('look_angles', 'regional_bank', 1), ('teme_to_ecef', 'ecef_states', 2)):
        leaf, = [r for r in leaves if r['source'][2] == kernel]
        stage = leaf['stages']['prepare']
        edge, = stage['callers']
        if not (stage['calls'] == edge[1] == count and edge[0][2] == caller):
            raise ValueError(f'Unexpected caller or count for {kernel}')
        out[kernel] = dict(calls=count, caller=caller, inclusive_cpu_s=stage['inclusive_cpu_s'])
    return dict(**out, whole_scope_ceiling_cpu_s=fsum(stage['inclusive_cpu_s'] for stage in out.values()))


def main():
    for path, pin in SOURCE.items():
        checked(RELEASE/path, pin)
    raw = [raw_case(json.loads(checked(Path('/dev/shm')/path, pin))) for path, pin in RAW.values()]
    if [row['case'] for row in raw] != list(RAW):
        raise ValueError('Unexpected raw study roster')
    evidence = {}
    for key, (path, pin) in EVIDENCE.items():
        payload = checked(REPORT/'measurements'/path, pin)
        evidence[key] = json.loads(gzip.decompress(payload) if path.endswith('.gz') else payload)
    weak_bank = [entry for entry in evidence['weak_saved']['bulk_calls'] if entry['stage'] == 'regional_bank']
    result = dict(sources=dict(raw=RAW, evidence=EVIDENCE, installed=SOURCE), measured_raw=raw,
                  raw_optimistic_floors=raw_envelope(raw), historical_floor=historical_envelope(evidence['census']['rows']),
                  weak_earlier_saved_bulk_calls=weak_bank, profiled_medium_outer_ceiling=profiled_outer_ceiling(evidence['medium_profile']))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
