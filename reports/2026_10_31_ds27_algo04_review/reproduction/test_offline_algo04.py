"""Offline orchestration tests; no RF, fitting, geographic truth or storage writes."""

import copy
import json
from pathlib import Path

import pytest

import offline_algo04 as adapter


def source(tmp_path):
    root = tmp_path / 'source/candidate-v2'
    fits = {a: dict(endpoint_east_north_km=[0., 0.], negative_twice_elbo=10.,
                    owners={'old': 1}) for a in adapter.ARMS}
    incumbent = dict(schema_version=2, input_sha256='sha256:input', session_id='scan',
                     state='complete', baseline={'arms': copy.deepcopy(fits)}, selected={'arms': fits},
                     position={'latitude_deg': 1., 'longitude_deg': 2.}, total_seconds=25.,
                     read_audit={'verified': True})
    adapter.write(root / 'terminal.json', incumbent)
    adapter.write(root / 'recovery/decision.json', {'original_path': str(root / 'recovery')})
    adapter.write(root / 'recovery/snapshot/descriptor.json', {'root': str(root / 'recovery/snapshot')})
    (root / 'recovery/snapshot/bank.npz').write_bytes(b'causal-bank')
    return root, incumbent


class Backend:
    release = Path('/installed/frozen-release')
    manifest_sha256 = 'sha256:manifest'

    def __init__(self, incumbent, failure=None):
        self.incumbent = incumbent
        self.failure = failure
        self.calls = []

    def validate_v2(self, value, *, input_sha256):
        assert value['schema_version'] == 2 and value['input_sha256'] == input_sha256

    def guarded_replay(self, output, *, deadline):
        self.calls.append('guard')
        descriptor = adapter.read(output / 'source-export/descriptor.json')
        assert descriptor['root'] == str(output / 'source-export')
        assert descriptor['incumbent'] == self.incumbent
        for name, expected in descriptor['files'].items():
            assert adapter.digest(Path(descriptor['root']) / name) == expected
        if self.failure == 'guard':
            adapter.write(output / 'guarded-result.json', dict(read_audit={'verified': False},
                stages=[{'name': 'target', 'status': 'failed'}]))
            raise ValueError('process read audit failed')
        if self.failure == 'source_change':
            (Path(descriptor['source_recovery_root']) / 'snapshot/bank.npz').write_bytes(b'changed')
        result = dict(baseline=copy.deepcopy(self.incumbent['baseline']), selected=True,
                      read_audit={'verified': True}, stages=[])
        if self.failure == 'baseline':
            result['baseline'] = {'changed': True}
        adapter.write(output / 'decision.json', result)
        return result

    def verify_selected(self, result, recovery):
        self.calls.append('proof')
        if self.failure == 'proof':
            raise ValueError('owner proof failed')
        return {'all': True}

    def proof_envelope(self, baseline, result, *, recovery_seconds, proof_checks):
        self.calls.append('proof_envelope')
        assert proof_checks == {'all': True}
        candidate = copy.deepcopy(self.incumbent)
        candidate['position']['latitude_deg'] = 1.1
        for arm in adapter.ARMS:
            candidate['selected']['arms'][arm]['owners']['new'] = 2
        return candidate

    def envelope(self, incumbent, candidate, *, numerical_seconds, failure):
        self.calls.append('envelope')
        admitted = candidate is not None
        return dict(incumbent=incumbent, candidate=candidate,
                    decision='ALGO04_additive' if admitted else 'ALGO03_fallback',
                    position=(candidate if admitted else incumbent)['position'],
                    acceptance_reason='qualified' if admitted else 'no_qualified_numerical_candidate',
                    numerical_seconds=numerical_seconds, failure=failure)

    def published_owners(self, terminal, arm):
        return terminal['selected']['arms'][arm]['owners']


def test_private_export_matches_public_port_layout_preserves_original_bytes(tmp_path):
    root, incumbent = source(tmp_path)
    original = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    destination = tmp_path / 'private-export'
    descriptor, terminal_hash, hashes = adapter.export_recovery(
        root / 'terminal.json', root / 'recovery', destination, incumbent)
    assert descriptor['files']['incumbent-terminal.json'] == terminal_hash
    assert set(descriptor['files']) == {'incumbent-terminal.json', *('recovery/' + n for n in hashes)}
    assert destination.stat().st_mode & 0o777 == 0o700
    for name in descriptor['files']:
        p = destination / name
        assert p.stat().st_mode & 0o777 == 0o600
        original_path = root / ('terminal.json' if name == 'incumbent-terminal.json' else name)
        assert p.read_bytes() == original_path.read_bytes()
        assert p.stat().st_ino != original_path.stat().st_ino
    assert all(p.read_bytes() == value for p, value in original.items())


def test_exact_installed_call_order_both_arms_and_inference_seal(tmp_path):
    root, incumbent = source(tmp_path)
    before = adapter.inventory(root)
    backend = Backend(incumbent)
    output = tmp_path / 'candidate-v3'
    receipt = adapter.run_one(root / 'terminal.json', root / 'recovery', output, backend=backend)
    assert receipt['state'] == 'complete' and receipt['decision'] == 'ALGO04_additive'
    assert backend.calls == ['guard', 'proof', 'proof_envelope', 'envelope']
    assert receipt['maximum_seconds'] == 1200
    assert set(receipt['published_arms']) == set(adapter.ARMS)
    assert all(v['added_points'] == 1 and v['incumbent_owners_preserved']
               for v in receipt['published_arms'].values())
    seal = adapter.read(output / 'inference-seal.json')
    assert seal['source_unchanged'] and seal['fresh_process_read_guard'] and seal['no_GPS_inference']
    assert seal['output_hashes'][str(output / 'terminal.json')] == adapter.digest(output / 'terminal.json')
    assert adapter.inventory(root) == before


@pytest.mark.parametrize('failure', ['guard', 'baseline', 'proof'])
def test_replay_failures_publish_exact_incumbent_and_keep_failure_receipts(tmp_path, failure):
    root, incumbent = source(tmp_path)
    output = tmp_path / 'candidate-v3'
    receipt = adapter.run_one(root / 'terminal.json', root / 'recovery', output,
                              backend=Backend(incumbent, failure))
    assert receipt['state'] == 'complete' and receipt['decision'] == 'ALGO03_fallback'
    terminal = adapter.read(output / 'terminal.json')
    assert terminal['position'] == incumbent['position'] and terminal['incumbent'] == incumbent
    assert receipt['failure'] and receipt['source_unchanged']
    if failure == 'guard':
        assert receipt['read_audit']['verified'] is False
        assert len(receipt['stage_failures']) == 1
        assert adapter.read(output / 'inference-seal.json')['fresh_process_read_guard'] is False


def test_historical_guard_failure_never_launches_or_claims_fresh_guard(tmp_path):
    root, incumbent = source(tmp_path)
    incumbent['read_audit']['verified'] = False
    (root / 'terminal.json').write_text(json.dumps(incumbent))
    backend = Backend(incumbent)
    output = tmp_path / 'candidate-v3'
    receipt = adapter.run_one(root / 'terminal.json', root / 'recovery', output, backend=backend)
    assert backend.calls == ['envelope']
    assert receipt['decision'] == 'ALGO03_fallback' and 'Historical' in receipt['failure']
    assert adapter.read(output / 'inference-seal.json')['fresh_process_read_guard'] is False


def test_changed_source_cannot_publish_terminal_or_inference_seal(tmp_path):
    root, incumbent = source(tmp_path)
    output = tmp_path / 'candidate-v3'
    receipt = adapter.run_one(root / 'terminal.json', root / 'recovery', output,
                              backend=Backend(incumbent, 'source_change'))
    assert receipt['state'] == 'failed' and 'source terminal or recovery changed' in receipt['reason']
    assert not (output / 'terminal.json').exists()
    assert not (output / 'inference-seal.json').exists()


@pytest.mark.parametrize('kind', ['leaf', 'ancestor', 'recovery'])
def test_sources_refuse_symlinks_without_scientific_launch(tmp_path, kind):
    root, incumbent = source(tmp_path)
    if kind == 'leaf':
        (root / 'recovery/link.json').symlink_to(root / 'recovery/decision.json')
    elif kind == 'ancestor':
        (root / 'recovery/link').symlink_to(root / 'recovery/snapshot', target_is_directory=True)
    else:
        (root / 'recovery').rename(root / 'real-recovery')
        (root / 'recovery').symlink_to(root / 'real-recovery', target_is_directory=True)
    backend = Backend(incumbent)
    receipt = adapter.run_one(root / 'terminal.json', root / 'recovery', tmp_path / 'candidate-v3', backend=backend)
    assert receipt['state'] == 'failed' and 'symbolic links' in receipt['reason']
    assert not backend.calls


def test_missing_case_still_gets_denominator_receipt(tmp_path):
    receipt = adapter.run_one(tmp_path / 'source/missing-terminal', tmp_path / 'source/missing-recovery',
                              tmp_path / 'candidate-v3', backend=Backend({}))
    assert receipt['state'] == 'unavailable'
    assert (tmp_path / 'candidate-v3/receipt.json').exists()


def test_output_cannot_modify_immutable_source_tree(tmp_path):
    root, incumbent = source(tmp_path)
    with pytest.raises(ValueError, match='overlaps'):
        adapter.run_one(root / 'terminal.json', root / 'recovery', root / 'forbidden',
                        backend=Backend(incumbent))
    assert not (root / 'forbidden').exists()


def test_private_export_detects_source_change_during_byte_copy(tmp_path, monkeypatch):
    root, incumbent = source(tmp_path)
    original_copy = adapter.shutil.copyfile

    def racing_copy(src, dest):
        result = original_copy(src, dest)
        if Path(src) == root / 'recovery/snapshot/bank.npz':
            Path(src).write_bytes(b'changed during copy')
        return result

    monkeypatch.setattr(adapter.shutil, 'copyfile', racing_copy)
    with pytest.raises(ValueError, match='source terminal or recovery changed'):
        adapter.export_recovery(root / 'terminal.json', root / 'recovery',
                                 tmp_path / 'private-export', incumbent)


def test_unprovable_owner_summary_does_not_destroy_valid_fallback(tmp_path, monkeypatch):
    root, incumbent = source(tmp_path)
    backend = Backend(incumbent, 'proof')

    def missing_owners(*args):
        raise ValueError('Missing explicit ownership')

    monkeypatch.setattr(backend, 'published_owners', missing_owners)
    receipt = adapter.run_one(root / 'terminal.json', root / 'recovery',
                              tmp_path / 'candidate-v3', backend=backend)
    assert receipt['state'] == 'complete' and receipt['decision'] == 'ALGO03_fallback'
    assert all('ownership_not_provable' in arm for arm in receipt['published_arms'].values())


def test_installed_release_preflight_imports_frozen_tools_without_running_fits():
    backend = adapter.load_release(adapter.DEFAULT_RELEASE)
    assert backend.release == adapter.DEFAULT_RELEASE
    assert backend.guarded_replay.__module__ == 'algo04_production_worker'
    assert backend.manifest_sha256 == adapter.digest(backend.manifest)
