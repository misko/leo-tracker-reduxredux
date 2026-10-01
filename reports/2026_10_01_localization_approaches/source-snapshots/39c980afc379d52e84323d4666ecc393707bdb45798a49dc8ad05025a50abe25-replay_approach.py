"""Single bounded scan fit; no evaluator reference is imported or read."""
from __future__ import annotations
import time
START = time.monotonic()
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import sys
import numpy as np

from adapter import HERE, OLD, prepare, propose
from common import digest, seal

ROOT = HERE.parents[1]
PLAN = ROOT / 'plans/localization-approaches-2026-10-01/benchmark.json'


def read_sealed(path):
    path = Path(path)
    if json.loads(path.with_suffix('.seal.json').read_text())['prediction_sha256'] != digest(path):
        raise ValueError('parent seal mismatch')
    return json.loads(path.read_text())


def sources():
    paths = {Path(__file__).resolve(), PLAN, HERE / 'batch.py', ROOT / 'pyproject.toml', ROOT / 'uv.lock'}
    if (HERE / 'PROTOCOL.md').exists():
        paths.add(HERE / 'PROTOCOL.md')
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            p = Path(name).resolve()
            if p.suffix == '.py' and (p.is_relative_to(ROOT / 'src') or p.is_relative_to(ROOT / 'reports')):
                paths.add(p)
    return {str(p): digest(p) for p in sorted(paths)}


def choose_best(fits):
    scored = [f for f in fits if f['objectives']]
    return min(scored, key=lambda f: f['objectives'][-1]) if scored else None


def main(args):
    output = Path(args.output)
    if output.exists() or output.with_suffix('.seal.json').exists():
        raise FileExistsError(output)
    if args.arm == 'A1':
        from leo.analysis.localization_fast import fit_localization_fast as solver
    elif args.arm == 'B1':
        import batch_physics  # Bind optional bulk numerical source before receipt freeze.
        from leo.analysis.localization_soft import fit_joint_soft as solver
    elif args.arm == 'C1':
        from leo.analysis.localization_profiled import fit_localization_profiled as solver
    else:
        from leo.analysis.greedy_joint_location import fit_joint_greedy as solver
    config = dict(arm=args.arm, predictor=args.predictor, seed_source=args.seed_source,
                  degrees_of_freedom=4., seed_limit=3, max_iterations=24,
                  primary_external_s=90, continuation_external_s=90,
                  acquisition_budget_seconds=args.acquisition_budget)
    receipt = dict(schema='localization-approach-attempt/v1', unit_id=args.unit,
        config=config, status='running', fits=[], source_sha256=sources(),
        qualification='local mode search; no calibrated posterior',
        numpy_version=np.__version__, prior_manifest_sha256=digest(PLAN))
    try:
        scan, height, ports = prepare(args.unit, predictor=args.predictor)
        expected = next(u for u in json.loads(PLAN.read_text())['ordered_units'] if u['unit_id'] == args.unit)
        if scan.session_id != expected['session_id']:
            raise ValueError('benchmark session binding mismatch')
        receipt.update(session_id=scan.session_id, inputs=scan.inputs,
            height_input_bindings=height.input_bindings, planned_factors=len(ports),
            physical_observation_ids=[list(p.observation_ids) for p in ports],
            candidate_ids=list(scan.bank.norad_ids))
        dimension = 5 + len(scan.bank.norad_ids)
        precision = np.r_[0., 0., 1., np.full(dimension-3, 4.)]
        parent = None
        if args.parent:
            parent = read_sealed(args.parent)
            if parent['unit_id'] != args.unit or parent['config'] != config or parent.get('parent'):
                raise ValueError('continuation parent identity/config/stage mismatch')
            if parent['status'] != 'unresolved':
                raise ValueError('continuation only for an unresolved primary')
            if parent['source_sha256'] != receipt['source_sha256'] or parent['inputs'] != scan.inputs:
                raise ValueError('continuation sources or evidence changed')
            receipt['parent'] = dict(path=str(Path(args.parent).resolve()), sha256=digest(args.parent))
            receipt['proposal'] = parent['proposal']
            receipt['fits'] = json.loads(json.dumps(parent['fits']))
            jobs = [(i, f['seed'], np.r_[f['mean'], f['satellite_epoch_s']])
                    for i, f in sorted(enumerate(parent['fits']), key=lambda pair: pair[1]['objectives'][-1] if pair[1]['objectives'] else float('inf'))
                    if not f['converged']]
        else:
            proposal_start = time.monotonic()
            if args.seed_source == 'cached':
                manifest = json.loads(PLAN.read_text())
                binding = next(r for r in manifest['historical_primary_receipts'] if r['unit_id'] == args.unit)
                proposal_path = ROOT / binding['path']
                if digest(proposal_path) != binding['sha256']:
                    raise ValueError('historical proposal authority changed')
                original = read_sealed(proposal_path)
                if original['inputs'] != scan.inputs:
                    raise ValueError('cached proposal evidence differs')
                receipt['proposal'] = original['proposal']
                receipt['proposal_binding'] = binding
                receipt['qualification'] += '; cached-seed diagnostic, not independent end-to-end timing'
            else:
                receipt['proposal'] = asdict(propose(scan, height, max_tracks=len(scan.tracks),
                                                     deadline_s=args.acquisition_budget, degrees_of_freedom=4.))
            receipt['acquisition_seconds'] = time.monotonic() - proposal_start
            jobs = []
            for i, seed in enumerate(receipt['proposal']['seeds'][:3]):
                state = np.zeros(dimension)
                state[:2] = seed['east_km'], seed['north_km']
                jobs.append((i, seed, state))
                receipt['fits'].append(dict(seed_index=i, seed=seed, mean=state[:5].tolist(),
                    satellite_epoch_s=state[5:].tolist(), objectives=[], associations=[],
                    converged=False, iterations=0, reason='not_started', accepted_step_norms=[], fit_seconds=0.))
        receipt['setup_seconds'] = time.monotonic() - START
        for i, seed, state in jobs:
            if time.monotonic() - START > 80.:
                break
            kwargs = dict(max_iterations=24, deadline=START+85., degrees_of_freedom=4.)
            fit_start = time.monotonic()
            support = lambda x: bool(np.linalg.norm(x[:2]) <= 250.)
            if args.arm == 'oracle':
                result = solver(state, [p.oracle_factor() for p in ports],
                                [p.score_all for p in ports], precision, support, **kwargs)
            else:
                if args.arm == 'B1':
                    kwargs['max_active_branches_per_factor'] = None
                result = solver(state, ports, precision, support, **kwargs)
            associations = (tuple(int(np.argmax(p)) for p in result.responsibilities)
                            if args.arm == 'B1' and result.responsibilities is not None
                            else (() if args.arm == 'B1' else result.associations))
            fit = dict(seed_index=i, mean=result.mean[:5].tolist(), satellite_epoch_s=result.mean[5:].tolist(),
                associations=[str(scan.bank.norad_ids[j]) if j < len(scan.bank.norad_ids) else 'background'
                              for j in associations],
                objectives=list(result.objectives), converged=bool(result.converged),
                iterations=result.iterations, reason=result.reason,
                accepted_step_norms=list(result.accepted_step_norms), seed=seed,
                fit_seconds=time.monotonic()-fit_start)
            if args.arm == 'B1':
                fit['soft_diagnostics'] = dict(max_omitted_responsibility=result.max_omitted_responsibility,
                    proposal_is_approximate=result.proposal_is_approximate,
                    responsibilities_at_mean=result.responsibilities_at_mean,
                    admissible_for_official_benchmark=result.admissible_for_official_benchmark)
            if parent:
                before = parent['fits'][i]
                fit['iterations'] += before['iterations']
                fit['objectives'] = before['objectives'] + fit['objectives']
                fit['accepted_step_norms'] = before['accepted_step_norms'] + fit['accepted_step_norms']
                receipt['fits'][i] = fit
            else:
                receipt['fits'][i] = fit
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_suffix('.progress.json').write_text(json.dumps(receipt, allow_nan=False))
        receipt['best'] = choose_best(receipt['fits'])
        receipt['status'] = 'converged_local_mode' if receipt['best'] and receipt['best']['converged'] else 'unresolved'
        receipt['port_calls'] = {key: sum(p.calls[key] for p in ports) for key in ports[0].calls}
        if receipt['source_sha256'] != sources():
            raise ValueError('scientific source changed during fit')
    except Exception as error:
        receipt.update(status='error', exception=dict(type=type(error).__name__, message=str(error)))
    snapshots = HERE / 'source-snapshots'
    snapshots.mkdir(exist_ok=True)
    receipt['source_snapshots'] = {}
    for source, expected_hash in receipt['source_sha256'].items():
        path = Path(source)
        target = snapshots / (expected_hash.split(':')[1] + '-' + path.name)
        if digest(path) != expected_hash:
            receipt.update(status='error', exception=dict(type='SourceChanged', message=source))
            continue
        if not target.exists():
            try:
                with target.open('xb') as stream:
                    stream.write(path.read_bytes())
            except FileExistsError:
                pass
        receipt['source_snapshots'][source] = str(target)
    receipt['wall_seconds_before_sealing'] = time.monotonic() - START
    usage = resource.getrusage(resource.RUSAGE_SELF)
    receipt['cpu_seconds'] = usage.ru_utime + usage.ru_stime
    receipt['max_rss_kib'] = usage.ru_maxrss
    seal(output, receipt)
    print(json.dumps(dict(unit_id=args.unit, arm=args.arm, status=receipt['status'],
                          seconds=receipt['wall_seconds_before_sealing'], exception=receipt.get('exception'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--arm', choices=['A1', 'B1', 'C1', 'oracle'], required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--seed-source', choices=['cached', 'fresh'], default='cached')
    parser.add_argument('--predictor', choices=['oracle', 'selected'], default='selected')
    parser.add_argument('--parent')
    parser.add_argument('--acquisition-budget', type=float, choices=[40., 50.], default=50.)
    main(parser.parse_args())
