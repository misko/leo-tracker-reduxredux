"""One bounded offline ALGO04 replay through the exact installed scientific tools.

Inputs are a completed ALGO03/v2 terminal and its retained recovery directory.
Only private study artifacts are written. Geographic truth is never consumed.
"""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

DEFAULT_RELEASE = Path('/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef')
ARMS = ('c0', 'fitted_c')


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def no_links(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Offline sources and outputs may not traverse symbolic links')
    return path.resolve()


def inventory(root):
    root = no_links(root)
    if not root.is_dir():
        raise FileNotFoundError(root)
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Recovery export cannot contain symbolic links')
        if path.is_file() and '__pycache__' not in path.parts:
            result[str(path.relative_to(root))] = digest(path)
    return result


def verify_sources(terminal, recovery, terminal_hash, hashes):
    if digest(no_links(terminal)) != terminal_hash or inventory(recovery) != hashes:
        raise ValueError('ALGO03 source terminal or recovery changed during offline replay')


def export_recovery(terminal_path, recovery, destination, incumbent):
    """Mirror the public v2 private-byte export layout, with no source rewriting."""
    terminal_path, recovery, destination = map(no_links, (terminal_path, recovery, destination))
    if destination.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP adapters are read-only')
    if destination.is_relative_to(recovery) or recovery.is_relative_to(destination):
        raise ValueError('Private export overlaps its source recovery')
    if destination.is_relative_to(terminal_path.parent):
        raise ValueError('Private export must be outside its source terminal directory')
    before, hashes = digest(terminal_path), inventory(recovery)
    if read(terminal_path) != incumbent:
        raise ValueError('ALGO03 source changed before private export')
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    destination.chmod(0o700)
    files = {}
    for name, expected in hashes.items():
        target = destination / 'recovery' / name
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        shutil.copyfile(recovery / name, target)
        target.chmod(0o600)
        if digest(target) != expected:
            raise ValueError('Private export bytes changed: ' + name)
        files['recovery/' + name] = expected
    target = destination / 'incumbent-terminal.json'
    shutil.copyfile(terminal_path, target)
    target.chmod(0o600)
    if digest(target) != before:
        raise ValueError('ALGO03 incumbent changed while exporting')
    files[target.name] = before
    verify_sources(terminal_path, recovery, before, hashes)
    descriptor = dict(
        schema_version=1, kind='fast-graph-recovery-export',
        model_version='algo03-causal-predictive-v1', root=str(destination),
        source_recovery_root=str(recovery), files=files, incumbent=incumbent,
        incumbent_receipt=dict(path=str(terminal_path), sha256=before),
        source_job=dict(job_id=incumbent.get('job_id'), offline_explicit_source=True),
        input_sha256=incumbent['input_sha256'], session_id=incumbent['session_id'])
    write(destination / 'descriptor.json', descriptor)
    return descriptor, before, hashes


def load_release(release):
    """Import only the selected immutable installation, rejecting cached aliases."""
    release = no_links(release)
    for path in (release / 'src', release / 'tools'):
        sys.path.insert(0, str(path))
    names = ('algo04_production_worker', 'algo03_production_worker',
             'leo.contracts.fast_graph_position_v2', 'leo.contracts.fast_graph_position_v3',
             'stage_algo04_release')
    modules = [importlib.import_module(name) for name in names]
    for module in modules:
        if not Path(module.__file__).resolve().is_relative_to(release):
            raise ValueError('Offline adapter imported another scientific installation: ' + module.__name__)
    worker, proof, v2, v3, staging = modules
    worker.verify_release()
    return SimpleNamespace(
        release=release, guarded_replay=worker.guarded_replay, verify_selected=proof.verify_selected,
        proof_envelope=proof.envelope, envelope=worker.envelope, validate_v2=v2.validate_terminal,
        published_owners=v3.published_owners, manifest=release / staging.MANIFEST,
        manifest_sha256='sha256:' + staging.MANIFEST_SHA256)


def arm_summary(backend, terminal):
    chosen = terminal['candidate'] if terminal['decision'] == 'ALGO04_additive' else terminal['incumbent']
    fits = chosen['selected']['arms'] if chosen.get('selected') else chosen['baseline']['arms']
    result = {}
    for arm in ARMS:
        ownership = {}
        try:
            old = backend.published_owners(terminal['incumbent'], arm)
            new = backend.published_owners(chosen, arm)
            ownership.update(incumbent_associated_points=len(old), associated_points=len(new),
                             added_points=len(set(new) - set(old)),
                             incumbent_owners_preserved=all(new.get(i) == n for i, n in old.items()))
        except (KeyError, TypeError, ValueError) as error:
            ownership['ownership_not_provable'] = str(error)
        result[arm] = dict(**ownership, endpoint_east_north_km=fits[arm]['endpoint_east_north_km'],
                          negative_twice_elbo=fits[arm].get('negative_twice_elbo'))
    return result


def run_one(source_terminal, source_recovery, output, *, maximum_seconds=1200,
            release=DEFAULT_RELEASE, backend=None):
    """Write a complete failure receipt even when no qualified source exists."""
    if isinstance(maximum_seconds, bool) or not isinstance(maximum_seconds, int) or not 1 <= maximum_seconds <= 1200:
        raise ValueError('Matched per-case budget must be 1..1200 seconds')
    began = time.monotonic()
    source_terminal, source_recovery = map(Path, (source_terminal, source_recovery))
    output = no_links(output)
    if output.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP adapters are read-only')
    if (output.is_relative_to(source_terminal.resolve().parent)
            or output.is_relative_to(source_recovery.resolve())
            or source_recovery.resolve().is_relative_to(output)):
        raise ValueError('Study output overlaps its immutable ALGO03 source')
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(state='failed', source_terminal=str(source_terminal.absolute()),
                   source_recovery=str(source_recovery.absolute()), maximum_seconds=maximum_seconds,
                   arms=list(ARMS), no_GPS_inference=True, production_changed=False,
                   matched_observations_candidates_priors_budgets=True)
    terminal = None
    try:
        backend = backend if backend is not None else load_release(release)
        receipt.update(release=str(backend.release), release_manifest_sha256=backend.manifest_sha256)
        incumbent = read(no_links(source_terminal))
        backend.validate_v2(incumbent, input_sha256=incumbent['input_sha256'])
        if incumbent['state'] != 'complete':
            raise ValueError('Completed ALGO03/v2 source required')
        terminal_hash = digest(source_terminal)
        hashes = inventory(source_recovery)
        recovery = output / 'recovery'
        recovery.mkdir()
        candidate, failure, result = None, None, {}
        try:
            if (incumbent.get('read_audit') or {}).get('verified') is not True:
                raise ValueError('Historical incumbent read audit not verified; retain ALGO03')
            _, terminal_hash, hashes = export_recovery(
                source_terminal, source_recovery, recovery / 'source-export', incumbent)
            result = backend.guarded_replay(recovery, deadline=began + maximum_seconds)
            if result.get('baseline') != incumbent['baseline']:
                raise ValueError('Replay changed the original ALGO02 comparator')
            checks = backend.verify_selected(result, recovery) if result.get('selected') else None
            candidate = backend.proof_envelope(incumbent['baseline'], result,
                                               recovery_seconds=time.monotonic() - began,
                                               proof_checks=checks)
        except Exception as error:
            failure = f'{type(error).__name__}: {error}'
        for saved in (recovery / 'guarded-result.json', recovery / 'decision.json'):
            if not result and saved.exists():
                result = read(saved)
        verify_sources(source_terminal, source_recovery, terminal_hash, hashes)
        terminal = backend.envelope(incumbent, candidate,
                                    numerical_seconds=time.monotonic() - began, failure=failure)
        write(output / 'terminal.json', terminal)
        # Inference is sealed before any downstream geographic evaluation.
        write(output / 'inference-seal.json', dict(
            source_hashes={str(source_terminal.absolute()): terminal_hash,
                           **{str(source_recovery.absolute() / n): h for n, h in hashes.items()}},
            output_hashes={str(output / 'terminal.json'): digest(output / 'terminal.json')},
            adapter_sha256=digest(__file__), installed_release=str(backend.release),
            installed_manifest_sha256=backend.manifest_sha256, no_GPS_inference=True,
            source_unchanged=True,
            fresh_process_read_guard=bool((result.get('read_audit') or {}).get('verified'))))
        receipt.update(state='complete', decision=terminal['decision'], failure=failure,
                       acceptance_reason=terminal['acceptance_reason'],
                       terminal_path=str(output / 'terminal.json'), source_unchanged=True,
                       published_arms=arm_summary(backend, terminal),
                       read_audit=result.get('read_audit'),
                       stage_failures=[s for s in result.get('stages', [])
                                       if s.get('status') in ('failed', 'timeout', 'budget_exhausted')])
    except Exception as error:
        receipt.update(state='unavailable' if isinstance(error, FileNotFoundError) else 'failed',
                       reason=f'{type(error).__name__}: {error}')
    receipt['seconds'] = time.monotonic() - began
    write(output / 'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-terminal', 'source-recovery', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--release', type=Path, default=DEFAULT_RELEASE)
    parser.add_argument('--maximum-seconds', type=int, choices=range(1, 1201), default=1200)
    args = parser.parse_args()
    receipt = run_one(args.source_terminal, args.source_recovery, args.output,
                      maximum_seconds=args.maximum_seconds, release=args.release)
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
