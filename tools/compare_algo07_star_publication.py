"""Compare both-arm published science, all PNGs, grid and optimizer path exactly."""
import argparse
import copy
import json
import math
from pathlib import Path

from diff_algo07_star_evidence import differences

from leo.cli.algo07_profile import write_new
from leo.contracts.fast_standard_analysis import PLOTS
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


def science_document(document):
    result = copy.deepcopy(document)
    elapsed = result.pop('replay_seconds')
    if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
        raise ValueError('Invalid publication accounting')
    # This link is checked against the actual public terminal by run(), and PNG
    # metadata plus bytes are checked independently rather than discarded.
    result.pop('terminal_sha256')
    result.pop('artifacts')
    return result


def presentation_document(document, *, grid):
    result = copy.deepcopy(document)
    # The storage port validates the complete binding before this normalization.
    result['binding'].pop('terminal_sha256')
    if grid:
        elapsed = result.pop('elapsed_seconds')
        if type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('Invalid grid accounting')
        if not result['complete']:
            raise ValueError('Incomplete diagnostic grid cannot qualify')
    return result


def run(args):
    roots = [p.resolve(strict=True) for p in (args.reference, args.candidate)]
    if roots[0] == roots[1]:
        raise ValueError('Independent private publications required')
    packages = []
    for root in roots:
        marker = json.loads((root/'algo07-star-input.json').read_text())
        if marker['kind'] != 'algo07-star-native-evidence' or marker['run_id'] != args.run_id:
            raise ValueError('Private native replay root required')
        target = FastStandardAnalysisStore(root)
        document = target.detail(args.run_id)
        if document['state'] != 'complete':
            raise ValueError('Complete public artifact set required')
        source = FastGraphPositionStoreV6(root)
        jobs = [j for j in source.completed_jobs() if j['run_id'] == args.run_id]
        if len(jobs) != 1:
            raise ValueError('One corresponding scientific job required')
        _, receipt = source.terminal(jobs[0])
        if document['terminal_sha256'] != receipt['sha256']:
            raise ValueError('Publication bound to another scientific terminal')
        entries = {a['name']: a for a in document['artifacts']}
        if set(entries) != set(PLOTS) or len(document['artifacts']) != len(PLOTS):
            raise ValueError('All eight unique standard artifacts required')
        pngs = {name: target.artifact(args.run_id, name, entries[name]['sha256']) for name in PLOTS}
        packages.append(dict(document=document, entries=entries, pngs=pngs,
                             grid=target.position_grid(args.run_id),
                             path=target.position_path(args.run_id)))
    a, b = packages
    science = list(differences(science_document(a['document']), science_document(b['document'])))
    pngs = {name: a['pngs'][name] == b['pngs'][name] and a['entries'][name] == b['entries'][name]
            for name in PLOTS}
    if a['grid']['complete'] and b['grid']['complete']:
        grid = list(differences(presentation_document(a['grid'], grid=True),
                                presentation_document(b['grid'], grid=True)))
    else:
        grid = [dict(kind='incomplete_grid',
                     reference_evaluated=a['grid']['evaluated_points'],
                     candidate_evaluated=b['grid']['evaluated_points'],
                     reference_planned=a['grid']['planned_points'],
                     candidate_planned=b['grid']['planned_points'])]
    locations = [{(p['east_km'], p['north_km']): p for p in package['grid']['points']}
                 for package in packages]
    shared = sorted(locations[0].keys() & locations[1].keys())
    shared_differences = [dict(location=list(xy), differences=delta)
                          for xy in shared
                          if (delta := list(differences(locations[0][xy], locations[1][xy])))]
    path = list(differences(presentation_document(a['path'], grid=False),
                            presentation_document(b['path'], grid=False)))
    result = dict(publication_exact=not science and all(pngs.values()) and not grid and not path,
                  science_differences=science, png_bytes_equal=pngs,
                  grid_differences=grid, path_differences=path,
                  shared_grid_points=len(shared), shared_grid_differences=shared_differences,
                  arms=a['document']['arms'], selected_model=a['document']['selected_model'],
                  glrt_points=a['document']['glrt_points'], tolerance=0,
                  source_terminals_independently_verified=True,
                  all_internal_decisions_qualified=False, ds26_equivalence_verified=False)
    write_new(args.output, result)
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'candidate', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    result = run(parser.parse_args())
    if not result['publication_exact']:
        raise SystemExit(1)
