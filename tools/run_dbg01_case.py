"""Bounded, resumable DBG01 adapter for frozen ALGO02 cases.

Reuse the audited numerical engine; keep new artifacts outside frozen results.
"""

import argparse
import gc
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np

import debug_algo02_ds23_0268 as engine
import report_dbg01_algo02_ds23_0268 as report
from dsx01_inference_audit import disk_grid
from run_algo01_ds23_sample import ROOT, read, write, sha

DEFAULT = Path('/srv/bulk/leo/research/dbg01-two-worst-fast-20261021')


def configure(case, root, workers=24):
    out = Path(root) / case
    engine.CASE = report.CASE = case
    engine.OUT = report.OUT = out
    engine.WORKERS = workers
    engine.context.cache_clear()
    return out


def prepare(case, root, workers):
    out = configure(case, root, workers)
    if (out / 'protocol.json').exists():
        return
    out.mkdir(parents=True, exist_ok=True)
    scan, node, keep, base, old = engine.context()
    axis, regional = disk_grid(step_km=1)
    local_axis = np.arange(-2, 2.001, .25)
    local = report.REFERENCE_XY + np.array([(x, y) for y in local_axis for x in local_axis])
    if np.any(abs(local) > 12.5):
        raise ValueError('diagnostic view extends outside original region')
    write(out / 'request.json', dict(case=case, algorithm='ALGO02-v1',
        diagnostic_point=report.REFERENCE_XY, surface_points=np.vstack([regional, local]),
        regional_count=len(regional), regional_axis=axis, local_axis=local_axis,
        reference_xy=report.REFERENCE_XY, no_grid_points_clipped=True,
        GPS_used_only_for_explicit_diagnostic_views=True))
    families = sorted({r['candidate_norad'] for r, sl in zip(base.rows, base.slices, strict=True) if keep[sl].any()})
    tracks = [r['component'] for r, sl in zip(base.rows, base.slices, strict=True) if keep[sl].any()]
    write(out / 'interventions.json', dict(family=families, track=tracks,
        prior=['baseline', 'phase_x2', 'phase_zero_mean', 'bias1000', 'drift1', 'orbit3', 'smooth50']))
    names = ['algo02_result.json', 'result.json', 'tracks.json', 'observations.json',
             'radio_noise.json', 'receipt.json', 'selected.tle', 'previous.tle', 'bank.npz']
    write(out / 'protocol.json', dict(case=case, algorithm='frozen ALGO02-v1',
        input_sha256={n: sha(engine.SOURCE / case / n) for n in names},
        source_sha256={n: sha(ROOT / 'tools' / n) for n in
            ['run_dbg01_case.py', 'debug_algo02_ds23_0268.py', 'report_dbg01_algo02_ds23_0268.py']},
        workers=workers, center=report.CENTER, box_width_km=25, phase_rounds=5,
        steps_per_round=48, starts=engine.STARTS, discovery_starts=engine.DISCOVERY_STARTS,
        original_observations_and_priors_preserved=True,
        future_TLEs_only_in_separate_unassociated_diagnostic=True))
    if case == 'DS23-0268':
        previous = ROOT / 'reports/2026_10_20_dbg01_algo02_ds23_0268'
        reused = {}
        for path in previous.glob('*.json'):
            stem = path.stem
            if stem in ['audit', 'hypothesis_bank'] or any(stem.startswith(k + '_') and stem[-2:].isdigit()
                    for k in ['grid', 'restart', 'discovery', 'family', 'track', 'prior']):
                (out / path.name).symlink_to(path)
                reused[path.name] = sha(path)
        write(out / 'reused_evidence.json', dict(source=str(previous), sha256=reused,
            unchanged_frozen_case_inputs_verified=all(sha(engine.SOURCE / case / n) == digest
                for n, digest in read(previous / 'protocol.json')['input_sha256'].items())))
    print(dict(case=case, families=len(families), curved_tracks=len(tracks), output=str(out)), flush=True)


def execute(job):
    result = engine.execute(job)
    # Per-problem memoized closures form cycles. Release them between jobs
    # rather than keeping multi-gigabyte arrays in idle worker processes.
    gc.collect()
    return result


def run(case, root, workers, stage):
    out = configure(case, root, workers)
    if stage == 'bank':
        if not (out / 'hypothesis_bank.json').exists():
            print(engine.bank(), flush=True)
        return
    if stage == 'figures':
        audit = read(out / 'audit.json')
        coverage = report.glrt_figures(audit)
        report.surfaces(audit)
        stats = report.restarts(audit)
        interventions = report.influence(audit)
        protocol = read(out / 'protocol.json')
        assert all(sha(engine.SOURCE / case / n) == h for n, h in protocol['input_sha256'].items())
        write(out / 'validation.json', dict(case=case, original_inputs_unchanged=True,
            endpoint_replay_difference={a: audit['arms'][a]['objective_replay_difference'] for a in engine.ARMS},
            coverage=coverage, restarts=stats, family_ablations=len([r for r in interventions if r['kind']=='family']) // 2,
            track_ablations=len([r for r in interventions if r['kind']=='track']) // 2,
            source_sha256=protocol['source_sha256']))
        return
    if stage == 'audit':
        jobs = [('audit', 0)]
    elif stage == 'discover':
        jobs = [('discover', i) for i in range(len(engine.DISCOVERY_STARTS))]
    elif stage == 'analyze':
        interventions = read(out / 'interventions.json')
        jobs = [('grid', i) for i in range(workers)] + [('restart', i) for i in range(len(engine.STARTS))]
        jobs += [(kind, i) for kind in ('family', 'track', 'prior') for i in range(len(interventions[kind]))]
    else:
        raise ValueError(stage)
    pending = [j for j in jobs if not (out / ('audit.json' if j[0]=='audit' else f'{j[0]}_{j[1]:02d}.json')).exists()]
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers, initializer=configure, initargs=(case, root, workers)) as pool:
        futures = {pool.submit(execute, j): j for j in pending}
        for i, future in enumerate(as_completed(futures), 1):
            print(future.result(), flush=True)
            write(out / (stage + '_progress.json'), dict(completed=i, requested=len(pending), seconds=time.monotonic()-started))
    write(out / (stage + '_execution.json'), dict(completed=len(pending), reused=len(jobs)-len(pending),
        all_terminal=True, seconds=time.monotonic()-started))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', required=True)
    parser.add_argument('--root', type=Path, default=DEFAULT)
    parser.add_argument('--workers', type=int, default=24)
    parser.add_argument('--stage', choices=['prepare','audit','discover','bank','analyze','figures'], required=True)
    args = parser.parse_args()
    if args.stage == 'prepare':
        prepare(args.case, args.root, args.workers)
    else:
        run(args.case, args.root, args.workers, args.stage)


if __name__ == '__main__':
    main()
