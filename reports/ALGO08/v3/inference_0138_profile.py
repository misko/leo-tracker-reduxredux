"""Measure disjoint original inference scopes on the staged DS30-0138 recording."""

import argparse
from collections import defaultdict
from contextlib import ExitStack, contextmanager
import cProfile
import json
import os
from pathlib import Path
import pstats
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import history_risk_0138 as active


ORIGINAL = Path('/dev/shm/leo-v3-history-risk-0138-pair02')
ORIGINAL_SEAL = '8bd0bbd2b6f2d9382f4bb9bd4ac0fdd216a16f38de73cdc2b68b2bb75f9f9b68'
ORIGINAL_BINDING = '61a0a5f5e5e5c697117d59a5aed17148a50e8000c5ee94375895c069c8546f5b'
PROTOCOL = HERE/'inference-0138-profile-protocol.md'
DRIVER = Path(__file__).resolve()


def clock(start):
    return dict(cpu_ns=process_time_ns()-start[0], elapsed_ns=perf_counter_ns()-start[1])


def capture(operation, record, *args, **kwargs):
    profile = cProfile.Profile(timer=process_time_ns, timeunit=1e-9)
    start = process_time_ns(), perf_counter_ns()
    try:
        return profile.runcall(operation, *args, **kwargs)
    finally:
        record['scope'] = clock(start)
        rows = pstats.Stats(profile).stats
        record['functions'] = [dict(path=path, line=line, name=name, calls=values[1], exclusive_s=values[2],
                                    inclusive_s=values[3], callers=[dict(path=k[0], line=k[1], name=k[2], calls=v[1],
                                                                     exclusive_s=v[2], inclusive_s=v[3])
                                                                     for k,v in sorted(values[4].items())])
                               for (path,line,name), values in sorted(rows.items())]


class Responses:
    """Recognize repeat responses without reworking any predictions or likelihoods."""

    def __init__(self, original):
        self.original = original
        self.seen = set()
        self.by_method = defaultdict(lambda: dict(calls=0, response_repeats=0, rows=0, repeat_rows=0,
                                                  cpu_ns=0, repeat_cpu_ns=0, key_cpu_ns=0))

    def __call__(self, scan, i, y, predicted, method, *, shortlist=False):
        cpu = process_time_ns()
        counts = self.by_method[method]
        key = id(scan), i, method, y.dtype.str, y.shape, predicted.shape, shortlist, y.tobytes()
        repeat = key in self.seen
        self.seen.add(key)
        timed = process_time_ns()
        result = self.original(scan, i, y, predicted, method, shortlist=shortlist)
        paid = process_time_ns()-timed
        counts['calls'] += 1
        counts['rows'] += predicted.shape[0]
        counts['key_cpu_ns'] += timed-cpu
        counts['cpu_ns'] += paid
        if repeat:
            counts['response_repeats'] += 1
            counts['repeat_rows'] += predicted.shape[0]
            counts['repeat_cpu_ns'] += paid
        return result


@contextmanager
def instrument(observed):
    import cold_finalist_race
    from leo.analysis.localization_v3.scan import ScanLikelihood
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    original_refine = cold_finalist_race.refine
    original_packet = algo08_position.selected_packet

    def cold(*args, **kwargs):
        original_rank = v5_core.ranked_initial_nodes
        responses = Responses(ScanLikelihood.curve)
        receipt = dict(rank_calls=[])
        observed.setdefault('cold', []).append(receipt)

        def rank(scan):
            start = process_time_ns(), perf_counter_ns()
            try:
                def curve(*values, **options):
                    return responses(*values, **options)

                with patch.object(ScanLikelihood, 'curve', curve):
                    return original_rank(scan)
            finally:
                receipt['rank_calls'].append(clock(start))

        with patch.object(v5_core, 'ranked_initial_nodes', rank):
            result = capture(original_refine, receipt, *args, **kwargs)
        receipt['responses'] = dict(responses.by_method)
        return result

    def packet(*args, **kwargs):
        receipt = {}
        observed.setdefault('standard_evidence', []).append(receipt)
        return capture(original_packet, receipt, *args, **kwargs)

    with (patch.object(cold_finalist_race, 'refine', cold), patch.object(algo08_position, 'selected_packet', packet)):
        yield


def worker(root):
    from aperture_trial import write
    import empty_bootstrap as startup

    body = json.loads((root/'profile-binding.json').read_bytes())
    if active.digest(DRIVER) != body['driver_sha256'] or active.digest(PROTOCOL) != body['protocol_sha256']:
        raise ValueError('Frozen profile observer changed')
    original = startup.load_runtime
    observations = {}
    with ExitStack() as live:
        def load():
            loaded = original()
            live.enter_context(instrument(observations))
            return loaded

        live.enter_context(patch.object(startup, 'load_runtime', load))
        active.worker(root, 'routed')
    write(root/'profiles.json', observations)


def run(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from history_risk_route_trial import sources
    from exact_named_route import checked_catalogue

    if root.parent.resolve(strict=True) != Path('/dev/shm') or root.exists():
        raise ValueError('Expected a fresh private profile root')
    machine = host()
    ordinary = json.loads(active.checked(ORIGINAL/'pair-binding.json', ORIGINAL_BINDING))
    active.checked(ORIGINAL/'result.json', ORIGINAL_SEAL)
    bound, req = active.bound_request()
    _archive, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    residency = json.loads(subprocess.check_output(
        ['fincore', '--json', '--bytes', '-o', 'RES,SIZE', *(ref.path for ref in refs)], text=True))['fincore']
    if len(residency) != len(refs) or any(row['res'] < row['size'] for row in residency):
        raise ValueError('Saved causal catalogue must remain resident')
    if ordinary['input'] != bound:
        raise ValueError('Profile input and source must reproduce the sealed ordinary route')
    root.mkdir(mode=0o700)
    (root/'tmp').mkdir()
    (root/'fonts').mkdir()
    for path in (ORIGINAL/'fonts').glob('fontlist-*.json'):
        os.link(path, root/'fonts'/path.name)
    command = ['/usr/bin/timeout', '--kill-after=2s', '95s', RELEASE/'venv/bin/python', '-IB', DRIVER, 'worker', root]
    write(root/'profile-binding.json', dict(driver_sha256=active.digest(DRIVER), protocol_sha256=active.digest(PROTOCOL),
          source_bound=bound, original_result_sha256=ORIGINAL_SEAL, command=list(map(str,command)), machine=machine))
    write(root/'binding.json', dict(input=bound))
    write(root/'route-binding.json', dict(cutoff_utc_ns=req['causal_cutoff_utc_ns'], sources=sources('0138')))
    env = environment(root) | {'TMPDIR': str(root/'tmp'), 'XDG_CACHE_HOME': str(root/'tmp')}
    exited = measure(command, env, root/'candidate')
    write(root/'clock.json', exited)
    if exited['exit_code']:
        raise ValueError('Profile worker failed; its external CPU and exit are sealed')


def score(root):
    from aperture_trial import write
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified

    profile = json.loads((root/'profiles.json').read_bytes())
    pair = json.loads(active.checked(ORIGINAL/'result.json', ORIGINAL_SEAL))
    request = json.loads(active.checked(active.STAGE/'request.json', active.REQUEST_PIN))
    elapsed = json.loads((root/'clock.json').read_bytes())
    previous = verified(ORIGINAL/'routed/candidate', pair['clock'], 'worker.json', request)
    actual = verified(root/'candidate', elapsed, 'worker.json', request)
    same = parity(previous, actual)
    if not all(same.values()):
        raise ValueError('Observer changed the scientific outcome, standard products or roster')
    cold, = profile['cold']
    evidence, = profile['standard_evidence']
    rank, = cold['rank_calls']
    observed, = json.loads((root/'risk-route.json').read_bytes())['solves']
    attempt, = observed['lean_attempts']
    if not cold['responses'] or not observed['inference_calls']:
        raise ValueError('Expected one original rank and whole standard evidence')
    write(root/'verification.json', dict(clock=elapsed, ordinary=pair['clock'], parity=same, rank=rank,
          cold=cold['scope'], evidence=evidence['scope'], responses=cold['responses'],
          attempt={k:v for k,v in attempt.items() if 'clocks' in k}, profile_sha256=active.digest(root/'profiles.json'),
          binding_sha256=active.digest(root/'profile-binding.json')))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('run', 'worker', 'score'))
    p.add_argument('root', type=Path)
    x = p.parse_args()
    {'run': run, 'worker': worker, 'score': score}[x.action](x.root)
