"""Run the unchanged production stage chain in an isolated public-store clone.

Research only. Does not publish into production or claim DS26 equivalence.
The runtime specification must be covered by a frozen manifest that also pins
the installed worker implementations. Publication is a subsequent adapter.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path

from leo.application.algo07_star import ALGORITHMS, Stage, run
from leo.cli.algo07_profile import verify, write_new


def read(path):
    return json.loads(Path(path).read_text())


def worker_environment(spec, algorithm):
    """Carry explicit deployment pins, without inheriting another stage's pin."""
    environment = spec.get('environment', {})
    allowed = {f'LEO_ALGO{i:02d}_RUNTIME_MANIFEST_SHA256' for i in (3, 7)}
    if set(environment)-allowed or any('=' in k or not isinstance(v, str)
                                      for k, v in environment.items()):
        raise ValueError('Unexpected worker environment override')
    runtime = Path(spec['runtime']).resolve(strict=True)
    manifest = runtime/'runtime-manifest.json'
    if manifest.exists() and algorithm in ('ALGO03', 'ALGO07'):
        key = f'LEO_{algorithm}_RUNTIME_MANIFEST_SHA256'
        if environment.get(key) != hashlib.sha256(manifest.read_bytes()).hexdigest():
            raise ValueError('Explicit deployment runtime pin required')
    return [f'{key}={value}' for key, value in sorted(environment.items())]


def verify_coverage(specifications, manifest):
    """Reject partial source pins and archive additions between paired runs."""
    from leo.operations.tle_archive import TleArchiveReader

    members = {Path(row['path']).resolve() for row in manifest['files']}
    for algorithm, spec in specifications.items():
        worker_environment(spec, algorithm)
        runtime = Path(spec['runtime']).resolve(strict=True)
        required = {p.resolve() for folder in ('src', 'tools', 'deploy')
                    for p in (runtime / folder).rglob('*') if p.is_file()}
        for folder in spec.get('watcher_pythonpath', '').split(':'):
            if folder:
                required.update(p.resolve() for p in Path(folder).rglob('*') if p.is_file())
        if (runtime/'runtime-manifest.json').exists():
            required.add(runtime/'runtime-manifest.json')
        required.add(Path(spec['python']).resolve(strict=True))
        if not required <= members:
            raise ValueError('Complete worker source and interpreter must be frozen')
    archive = TleArchiveReader(Path('/var/lib/leo/tle'))
    current = {str(s.path.resolve()) for s in archive.list_snapshots()}
    if not current or current != set(manifest['metadata']['tle_snapshot_paths']):
        raise ValueError('TLE archive membership changed; freeze a new paired fixture')
    if not {Path(p) for p in current} <= members:
        raise ValueError('TLE snapshot bytes must be frozen')


def stages_for(root, specifications):
    stages = []
    for number, algorithm in enumerate(ALGORITHMS, 1):
        suffix = '' if number == 1 else f'_v{number}'
        module = importlib.import_module('leo.storage.fast_graph_position'+suffix)
        store = getattr(module, 'FastGraphPositionStore'+
                        ('' if number == 1 else f'V{number}'))(root)
        process = importlib.import_module('leo.application.automatic_fast_graph'+suffix).process
        spec = specifications[algorithm]
        runtime = Path(spec['runtime']).resolve(strict=True)
        python = Path(spec['python']).absolute()
        worker = ('fast_graph_worker.py' if number == 1 else
                  f'algo{number+1:02d}_production_worker.py')
        command = ['/usr/bin/env', *worker_environment(spec, algorithm),
                   f'PYTHONPATH={runtime / "src"}:{runtime / "tools"}',
                   str(python), '-B', str(runtime / 'tools' / worker)]
        if number > 1:
            command += ['--bulk-root', str(root)]

        def job(previous, store=store, first=number == 1):
            if first:
                candidates = [j for j in store.inputs() if j['run_id'] == previous['run_id']]
                if len(candidates) != 1:
                    raise ValueError('Exactly one matching native input required')
                return candidates[0]
            return store.job(previous)

        def completed(previous, store=store, job=job):
            status = store.status(job(previous)['job_id'])
            return status is not None and status['state'] == 'complete'

        def execute(previous, store=store, process=process, job=job,
                    command=command, budget=spec['maximum_seconds']):
            current = job(previous)
            result = process(current, store=store, command=command, maximum_seconds=budget)
            if result and result['state'] == 'complete':
                # The application's resume path can return a cached status;
                # force the public terminal check at every coordinator boundary.
                store.terminal(current)
            return result

        stages.append(Stage(algorithm, spec['maximum_seconds'], completed, execute))
    return stages


def main(args):
    root = args.root.resolve(strict=True)
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    receipt = read(root / 'algo07-star-input.json')
    if receipt['kind'] != 'algo07-star-native-evidence' or root == Path(receipt['source_root']):
        raise ValueError('A private native-evidence export is required')
    for row in receipt['files']:
        path = (root / row['path']).resolve(strict=True)
        if (not path.is_relative_to(root) or
                hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']):
            raise ValueError('Frozen native evidence changed')
    spec_path = args.runtimes.resolve(strict=True)
    manifest_hash = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    manifest = read(args.manifest)
    members = {Path(row['path']).resolve(): row for row in manifest['files']}
    specifications = read(spec_path)
    if spec_path not in members or set(specifications) != set(ALGORITHMS):
        raise ValueError('Complete runtime specification must be frozen')
    verify_coverage(specifications, manifest)
    if not verify(args.manifest)['verified']:
        raise ValueError('Frozen runtime changed')
    from leo.storage.fast_graph_position import FastGraphPositionStore
    with FastGraphPositionStore(root).owner('algo07-star-coordinator') as owned:
        if not owned:
            raise ValueError('Private coordinator already owned')
        result = run(stages_for(root, specifications), dict(run_id=receipt['run_id']),
                     through=args.through, maximum_seconds=args.maximum_seconds)
        verify_coverage(specifications, manifest)
        after = verify(args.manifest)
        if (not after['verified'] or
                hashlib.sha256(args.manifest.read_bytes()).hexdigest() != manifest_hash):
            raise ValueError('Runtime changed during execution')
        output = dict(result, runtime_verification=after, production_modified=False,
                      ds26_equivalence_verified=False, artifacts_published=False,
                      source_receipt_sha256=hashlib.sha256(
                          (root / 'algo07-star-input.json').read_bytes()).hexdigest(),
                      runtime_manifest_sha256=manifest_hash)
        write_new(args.output, output)
        print(json.dumps({k:v for k,v in output.items() if k != 'incumbent'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--runtimes', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--through', choices=ALGORITHMS, default='ALGO07')
    parser.add_argument('--maximum-seconds', type=int, default=1800)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args())
