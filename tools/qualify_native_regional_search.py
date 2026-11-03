"""Bounded full regional replay; published memberships are an oracle control."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import time

from leo.native_pipeline.runner import digest, finite_json, write_json


def compare_trace(actual, reference, prior):
    trace = reference.get('diagnostics', {}).get('search_trace', {}).get(prior)
    if trace is None:
        return {'server_trace_available': False}
    expected = [event for event in trace if event['event'] == 'evaluate']
    ordered = actual['evaluations']
    sites = {(event['east_km'], event['north_km']): math.sqrt(event['weighted_mse_hz2'])
             for event in expected}
    deltas = [abs(row[2] - sites[tuple(row[:2])]) for row in ordered if tuple(row[:2]) in sites]
    return {'server_trace_available': True,
            'same_ordered_sites': len(ordered) == len(expected) and all(
                row[:2] == [event['east_km'], event['north_km']]
                for row, event in zip(ordered, expected)),
            'common_site_count': len(deltas),
            'max_common_site_score_delta_hz': max(deltas) if deltas else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--authority', required=True, type=Path)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--prior', choices=['sacramento', 'reno'], required=True)
    parser.add_argument('--published-memberships', action='store_true')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    reference = finite_json(args.authority / 'server-reference.json')
    prior = next(p for p in reference['priors'] if p['name'] == args.prior)
    region = prior['region']
    if args.published_memberships and digest(args.input) != digest(args.authority / 'published-reference.loc1'):
        raise ValueError('Published-membership control requires the exact oracle checkpoint')
    args.output.mkdir(parents=True, exist_ok=False)
    argv = [str(args.binary.resolve()), 'search', str(args.input.resolve()),
            str(region['center_latitude_deg']), str(region['center_longitude_deg']),
            str(region['radius_km']), '2']
    protocol = {'argv': argv, 'timeout_s': 300, 'prior': args.prior,
                'input_sha256': digest(args.input), 'binary_sha256': digest(args.binary),
                'reference_sha256': digest(args.authority / 'server-reference.json'),
                'published_memberships': args.published_memberships,
                'scope': 'Full 400-point bounded regional search, not global convergence'}
    write_json(args.output / 'protocol.json', protocol)
    start = time.monotonic()
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=300, check=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
        write_json(args.output / 'receipt.json', {'status': 'failed', 'error': str(error),
                                                'wall_s': time.monotonic() - start})
        raise
    elapsed = time.monotonic() - start
    (args.output / 'search.json').write_text(result.stdout)
    (args.output / 'search.stderr').write_text(result.stderr)
    actual = json.loads(result.stdout)
    selected = actual['selected']; expected = prior['selected']
    receipt = {'status': 'complete', 'wall_s': elapsed,
               'evaluated_points': actual['evaluated_points'],
               'search_complete': actual['complete'], 'stop_reason': actual['stop_reason'],
               'selected': selected, 'server_selected': expected,
               'same_selected_grid_point': all(selected[k] == expected[k] for k in ['east_km', 'north_km']),
               'selected_score_delta_hz': selected['score_hz'] - expected['capped_weighted_rmse_hz'],
               'deferred_cell_delta': actual['deferred_cells'] - prior['accounting']['deferred_cell_count'],
               'comparison_is_same_memberships': args.published_memberships}
    if actual['evaluated_points'] != 400 or len(actual['evaluations']) != 400:
        receipt['status'] = 'failed'
    receipt['trace_comparison'] = compare_trace(actual, reference, args.prior)
    write_json(args.output / 'receipt.json', receipt)
    print(json.dumps(receipt))
    if receipt['status'] != 'complete':
        raise ValueError('Full regional search did not evaluate 400 points')


if __name__ == '__main__':
    main()
