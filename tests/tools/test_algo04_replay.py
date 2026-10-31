"""ALGO04 cache relocation preserves scientific proof edges and frozen schedules."""

import json
import os
from pathlib import Path
import shutil

import pytest

import algo04_cache as cache
import algo04_replay_worker as replay
from algo03_production_worker import verify_selected
from algo03_shadow_worker import scientific_receipts, single_candidate, write


def exported_files(root):
    return {str(p.relative_to(root)): cache.digest(p)
            for p in root.rglob('*') if p.is_file()}


def test_relocation_rehashes_snapshot_relative_files_and_nested_proofs(tmp_path):
    source, destination = tmp_path / 'source', tmp_path / 'current/cache'
    origin = Path('/published/recovery')
    data = source / 'snapshot/inference/SCAN/data.json'
    write(data, dict(observation_ids=['b', 'a'], aliases=[-1, 0],
                     partitions={'held_blocks': [3, 1]}, bank=str(origin / 'bank.npz')))
    write(source / 'snapshot/descriptor.json', dict(
        root=str(origin / 'snapshot/inference'), files={'SCAN/data.json': 'sha256:' + cache.digest(data)}))
    write(source / 'proof.json', dict(source_receipts={
        str(origin / 'snapshot/descriptor.json'): cache.digest(source / 'snapshot/descriptor.json')}))
    original = {p: p.read_bytes() for p in source.rglob('*') if p.is_file()}
    receipt = cache.relocate(source, destination, origin, exported_files(source))
    descriptor = json.loads((destination / 'snapshot/descriptor.json').read_text())
    assert descriptor['root'] == str(destination / 'snapshot/inference')
    assert descriptor['files']['SCAN/data.json'] == 'sha256:' + cache.digest(
        destination / 'snapshot/inference/SCAN/data.json')
    proof = json.loads((destination / 'proof.json').read_text())
    assert proof['source_receipts'] == {
        str(destination / 'snapshot/descriptor.json'): cache.digest(destination / 'snapshot/descriptor.json')}
    moved = json.loads((destination / 'snapshot/inference/SCAN/data.json').read_text())
    assert moved['observation_ids'] == ['b', 'a']
    assert moved['aliases'] == [-1, 0]
    assert moved['partitions'] == {'held_blocks': [3, 1]}
    assert moved['bank'] == str(destination / 'bank.npz')
    assert all(p.read_bytes() == body for p, body in original.items())
    assert all(cache.digest(destination / name) == digest
               for name, digest in receipt['relocated_hashes'].items())


@pytest.mark.parametrize('name', ['/absolute.json', '../escape.json', 'nested/../../escape.json'])
def test_export_member_paths_refuse_escape(tmp_path, name):
    with pytest.raises(ValueError, match='Unsafe exported member'):
        cache.relocate(tmp_path, tmp_path / 'current', '/published/recovery', {name: '0'*64})


def test_original_byte_corruption_is_refused_before_destination_creation(tmp_path):
    source = tmp_path / 'source'
    write(source / 'proof.json', {'support': ['original']})
    files = exported_files(source)
    (source / 'proof.json').write_text('{"support":["changed"]}')
    destination = tmp_path / 'current'
    with pytest.raises(ValueError, match='Export bytes changed'):
        cache.relocate(source, destination, '/published/recovery', files)
    assert not destination.exists()


@pytest.mark.parametrize('snapshot', [False, True])
def test_original_proof_digest_corruption_is_refused(tmp_path, snapshot):
    source = tmp_path / 'source'
    origin = Path('/published/recovery')
    write(source / 'data.json', {'support': ['original']})
    proof = (dict(root=str(origin), files={'data.json': 'sha256:' + '0'*64}) if snapshot
             else dict(source_receipts={str(origin / 'data.json'): '0'*64}))
    write(source / 'proof.json', proof)
    with pytest.raises(ValueError, match='digest mismatch'):
        cache.relocate(source, tmp_path / 'current', origin, exported_files(source))


@pytest.mark.parametrize('ancestor', [False, True])
def test_symlink_members_are_refused_even_with_internal_target(tmp_path, ancestor):
    source = tmp_path / 'source'
    write(source / 'real/data.json', {'support': ['original']})
    if ancestor:
        (source / 'linked').symlink_to(source / 'real', target_is_directory=True)
        name = 'linked/data.json'
    else:
        (source / 'linked.json').symlink_to(source / 'real/data.json')
        name = 'linked.json'
    with pytest.raises(ValueError, match='[Ss]ymlink|escapes'):
        cache.relocate(source, tmp_path / 'current', '/published/recovery',
                       {name: cache.digest(source / name)})


@pytest.mark.parametrize('pointer', ['/published/recovery/../escape.json',
                                    '/published/recovery/a/../../escape.json'])
def test_embedded_origin_pointer_cannot_escape_current_root(tmp_path, pointer):
    source = tmp_path / 'source'
    write(source / 'proof.json', {'trial': pointer})
    with pytest.raises(ValueError, match='[Uu]nsafe|escape|relative'):
        cache.relocate(source, tmp_path / 'current', '/published/recovery', exported_files(source))


def test_origin_local_hash_edge_requires_exported_proof_member(tmp_path):
    source = tmp_path / 'source'
    write(source / 'proof.json', {'source_receipts': {'/published/recovery/missing.json': '0'*64}})
    with pytest.raises(ValueError, match='[Mm]issing|export|[Uu]nlisted'):
        cache.relocate(source, tmp_path / 'current', '/published/recovery', exported_files(source))


def test_cyclic_hash_edges_are_refused_without_recursion(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    origin = Path('/published/recovery')
    # An actual self-referential SHA256 fixed point is impractical. Stub only
    # the byte digest to exercise the graph cycle guard independently.
    monkeypatch.setattr(cache, 'digest', lambda _: 'a'*64)
    write(source / 'a.json', {'source_receipts': {str(origin / 'b.json'): 'a'*64}})
    write(source / 'b.json', {'source_receipts': {str(origin / 'a.json'): 'a'*64}})
    with pytest.raises(ValueError, match='Cyclic'):
        cache.relocate(source, tmp_path / 'current', origin, exported_files(source))


def scientific_study(root):
    arms = ('c0', 'fitted_c')
    write(root / 'read_receipts/123.json', dict(
        pid=123, parent_pid=os.getpid(), python_spawns=[], denied_paths=[]))
    support = {a: dict(owners={'old': 1}, unreported_postfit_ids=['incidental']) for a in arms}
    inventory = dict(policy={a: dict(proposed_associated_ids=['old', 'incidental']) for a in arms},
                     publication_support=support)
    descriptor = root / 'snapshot/descriptor.json'
    inv = root / 'all-large-track-recovery/job/inventory.json'
    write(descriptor, dict(job_id='job'))
    write(inv, inventory)
    write(root / 'snapshot/inference/SCAN/observations.json',
          [dict(observation_id=i) for i in ('old', 'new', 'incidental')])
    proof = inv.with_name('publication_support.json')
    write(proof, dict(arms=support, all_verified=True,
                      source_receipts=scientific_receipts([descriptor, inv])))
    trial = root / 'target/trial'
    write(trial / 'protocol.json', dict(targets=[dict(norad=2, observation_ids=['new'])]))
    write(trial / 'control.json', dict(paired_valid=True))
    endpoint = dict(endpoint_east_north_km=[0., 0.], endpoint_latlon=[37.906, -122.545],
                    negative_twice_elbo=900.)
    write(trial / 'new_family.json', dict(paired_valid=True, arms={a: endpoint for a in arms}))
    write(trial / 'exact_owner_replay.json', dict(all_verified=True, rows=[
        dict(role=role, arm=arm, verified=True, owners={'old': 1, 'new': 2, 'incidental': 3})
        for role in ('control', 'new_family') for arm in arms]))
    result = dict(selected=single_candidate(inventory, trial, False), source_support=support,
                  source_support_receipt=scientific_receipts([proof]), read_audit=dict(verified=True))
    write(root / 'decision.json', result)
    return result


def test_relocated_selected_and_baseline_support_proofs_reverify(tmp_path):
    source, destination = tmp_path / 'original', tmp_path / 'recovery'
    before = scientific_study(source)
    original = {p: p.read_bytes() for p in source.rglob('*') if p.is_file()}
    assert all(verify_selected(before, source).values())
    cache.relocate(source, destination, source, exported_files(source))
    relocated = json.loads((destination / 'decision.json').read_text())
    assert all(verify_selected(relocated, destination).values())
    assert relocated['selected']['arms'] == before['selected']['arms']
    assert relocated['source_support'] == before['source_support']
    for path in (*relocated['selected']['source_receipts'], *relocated['source_support_receipt']):
        assert Path(path).is_relative_to(destination)
    assert Path(relocated['selected']['trial']).is_relative_to(destination)
    assert all(p.read_bytes() == body for p, body in original.items())


def test_reused_stage_proofs_may_bind_cache_beneath_current_recovery(tmp_path):
    source, recovery = tmp_path / 'original', tmp_path / 'recovery'
    scientific_study(source)
    relocated = recovery / 'cache'
    cache.relocate(source, relocated, source, exported_files(source))
    for name in ('snapshot', 'all-large-track-recovery', 'target', 'read_receipts'):
        shutil.copytree(relocated / name, recovery / name)
    inv = recovery / 'all-large-track-recovery/job/inventory.json'
    proof = inv.with_name('publication_support.json')
    inventory = json.loads(inv.read_text())
    saved_proof = json.loads(proof.read_text())
    assert all(Path(name).is_relative_to(relocated) for name in saved_proof['source_receipts'])
    result = dict(selected=single_candidate(inventory, recovery / 'target/trial', False),
                  source_support=saved_proof['arms'], source_support_receipt=scientific_receipts([proof]),
                  read_audit=dict(verified=True))
    assert all(verify_selected(result, recovery).values())
    assert all(Path(name).is_relative_to(recovery) for name in result['selected']['source_receipts'])


def test_worker_uses_completed_frozen_schedule_and_preserves_patches(tmp_path, monkeypatch):
    output = tmp_path / 'current'
    export_root = output / 'source-export'
    source = export_root / 'recovery'
    origin = Path('/published/recovery')
    write(source / 'decision.json', dict(attempts=[{'track_id': 'done'}, {'track_id': 'omitted'}],
        stages=[dict(name='inventory', seconds=7.), dict(name='target-0-annotation', seconds=9.)],
        maximum_seconds=120))
    write(source / 'snapshot/descriptor.json', {'job_id': 'job'})
    write(source / 'all-large-track-recovery/job/inventory.json', {'unchanged': True})
    write(source / 'done/annotation/result.json', {'phase_outside_reference_window': False})
    write(source / 'done/annotation/protocol.json', {'frozen': True})
    write(output / 'source-export/descriptor.json', dict(
        root=str(export_root), source_recovery_root=str(origin), files={
            'recovery/' + name: digest for name, digest in exported_files(source).items()}))
    monkeypatch.setattr(replay.worker, 'select_targets', lambda inventory, limit=8: (
        [{'track_id': 'done'}, {'track_id': 'omitted'}], 2))
    saved = replay.worker.select_targets, replay.worker.execute, replay.worker.time
    commands = []
    monkeypatch.setattr(replay, 'execute', lambda command, **kwargs: commands.append(command) or 0)

    def worker_run(root, seconds):
        selected, count = replay.worker.select_targets({})
        assert selected == [{'track_id': 'done'}] and count == 2
        assert seconds == 120
        for name, script, relative in (
            ('inventory', 'algo03_inventory.py', 'all-large-track-recovery/job'),
            ('target-0-annotation', 'annotate_predictive_only.py', 'done/annotation'),
            ('target-0-inclusion', 'include_new_predictive_family.py', 'done/trial')):
            with (root / (name + '.log')).open('w') as log:
                assert replay.worker.execute(['python', '-B', script, '--output', str(root / relative)],
                                             log=log, timeout=30) == 0
        return {'schedule': 'unchanged'}

    monkeypatch.setattr(replay.worker, 'run', worker_run)
    assert replay.run(output, 150) == {'schedule': 'unchanged'}
    assert (replay.worker.select_targets, replay.worker.execute, replay.worker.time) == saved
    assert len(commands) == 1
    command = commands[0]
    assert Path(command[2]).name == 'algo04_numerical_stage.py'
    assert command[command.index('--reference-limit-s') + 1] == '30'
    assert '--centered-lbfgsb' in command
    assert Path(command[command.index('--receipt') + 1]).is_relative_to(output)
    assert Path(command[command.index('--receipt') + 2]).name == 'include_new_predictive_family.py'
    records = [json.loads(p.read_text()) for p in sorted((output / 'stage-cache').glob('*.json'))]
    assert [r['reused'] for r in records] == [True, True, False]
    assert [r.get('charged_original_seconds') for r in records[:2]] == [7., 9.]
    assert all(Path(r['source']).is_relative_to(output) for r in records)
