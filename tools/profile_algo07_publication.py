"""Profile verified ALGO07 figure reconstruction into a private publication store.

This does not rerun position fitting or modify the production result namespace.
Run under an external timeout of at most 30 minutes. Evaluation coordinates are
passed only to the presentation publisher after scientific inference is sealed.
"""
import argparse
import cProfile
import json
import pstats
import time
from pathlib import Path

import render_standard_fast as renderer

from leo.cli.algo07_chain_timing import collect
from leo.cli.algo07_profile import destination
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


def measure(calls, name, function):
    def wrapped(*args, **kwargs):
        start = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            calls.append(dict(stage=name, seconds=time.perf_counter()-start))
    return wrapped


def run(args):
    output = destination(args.output)
    output.mkdir(parents=True, exist_ok=False)
    chain = collect(args)
    source = FastGraphPositionStoreV6(args.bulk_root)
    (output / 'publication').mkdir()
    target = FastStandardAnalysisStore(output / 'publication')
    job = source.status(args.job)
    calls = []
    source.plot_evidence = measure(calls, 'read_and_validate_evidence', source.plot_evidence)
    target.publish = measure(calls, 'write_private_publication', target.publish)
    original_replay, original_render = renderer.replay, renderer.render
    renderer.replay = measure(
        calls, 'reconstruct_predictions_and_conditional_grid', original_replay)
    renderer.render = measure(calls, 'render_eight_pngs', original_render)
    reference = renderer.evaluation_coordinates(args.evaluation_latitude, args.evaluation_longitude)
    profile = cProfile.Profile()
    start = time.perf_counter()
    try:
        result = profile.runcall(renderer.publish, source, target, job,
                                evaluation_reference=reference)
    finally:
        renderer.replay, renderer.render = original_replay, original_render
        profile.dump_stats(str(output / 'publication.pstats'))
    elapsed = time.perf_counter()-start
    if result['terminal_sha256'] != chain['terminal_sha256']:
        raise ValueError('Scientific terminal changed during profiling')
    stats = pstats.Stats(profile)
    hotspots = [dict(function=key[2], path=key[0], line=key[1], calls=value[1],
                     self_seconds=value[2], cumulative_seconds=value[3])
                for key, value in sorted(stats.stats.items(), key=lambda item:-item[1][2])[:35]]
    grid = target.position_grid(job['run_id'])
    summary = dict(chain=chain, publication_wall_seconds=elapsed, calls=calls,
                   grid_seconds=grid['elapsed_seconds'], grid_points=grid['evaluated_points'],
                   hotspots=hotspots, profiled=True, production_modified=False,
                   scope='Fresh figure replay; recorded fitting times; no fresh localization',
                   uninstrumented_publication_seconds=elapsed-sum(c['seconds'] for c in calls))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    (output / 'position.png').write_bytes(target.artifact(job['run_id'], 'position'))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('hotspots', 'chain')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-root', type=Path, required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evaluation-latitude', type=float)
    parser.add_argument('--evaluation-longitude', type=float)
    run(parser.parse_args())
