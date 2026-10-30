"""Replay native graph ownership and bind recovery to published ALGO02 support."""

import argparse
from pathlib import Path

from algo03_shadow_worker import read, write, scientific_receipts
from inventory_all_large_tracks import one


def publication_support(baseline, replayed):
    result = {}
    for arm in ('c0', 'fitted_c'):
        actual = replayed[arm]
        published = set()
        known = {}
        for track in baseline['arms'][arm]['gates']['tracks'] + baseline['arms'][arm].get('linear_gates', []):
            for oid in track['observation_ids']:
                published.add(oid)
                if track.get('norad') is not None:
                    if oid in known and known[oid] != track['norad']:
                        raise ValueError('Conflicting published baseline owner')
                    known[oid] = track['norad']
        if not published <= actual.keys() or any(actual[o] != n for o, n in known.items()):
            raise ValueError('Published baseline does not replay its original ownership')
        result[arm] = dict(owners={o: actual[o] for o in sorted(published)},
                           unreported_postfit_ids=sorted(actual.keys() - published))
    if result['c0']['owners'] != result['fitted_c']['owners']:
        raise ValueError('Published c-arm ownership differs')
    return result


def run(args):
    one(args)
    from benchmark_graph_covariance import load_case
    from debug_fast_graph_unassociated import memberships
    descriptor = read(args.descriptor)
    inv = read(args.output / 'inventory.json')
    d = load_case(Path(inv['job']['root']), inv['job']['case'])
    replayed = {}
    for arm, (problem, x) in d['problems'].items():
        _, _, ids, replayed[arm] = memberships(problem, x, d['entries'])
        if ids != set(inv['policy'][arm]['proposed_associated_ids']):
            raise ValueError('Inventory ownership changed during replay')
    support = publication_support(descriptor['terminal'], replayed)
    write(args.output / 'publication_support.json', dict(arms=support, all_verified=True,
          baseline_objective_replay=d['replay'],
          source_receipts=scientific_receipts([args.descriptor, args.output / 'inventory.json'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('job', 'output', 'descriptor'):
        parser.add_argument('--' + name, type=Path, required=True)
    run(parser.parse_args())
