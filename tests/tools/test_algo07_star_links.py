import copy
import hashlib
import json

import pytest
from algo07_star_links import HashLinks, relocate_paths


def add(catalogue, tmp_path, name, value):
    path = tmp_path/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    catalogue[name] = dict(path=path, source_path='/store/'+name, store_root='/store',
                           sha256='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest())
    return catalogue[name]['sha256']


def test_named_link_is_bound_to_actual_target(tmp_path):
    c = {}
    sha = add(c, tmp_path, 'result.json', {'position': 1.0})
    add(c, tmp_path, 'audit.json', {'source_hashes': {'/store/result.json': sha}})
    index = HashLinks(c, {})
    value = index.document('audit.json', index.read('audit.json'))
    assert value['source_hashes']['<PRIVATE_STORE>/result.json'] == '<VERIFIED_FILE>/result.json'
    assert index.verified_links[0]['target'] == 'result.json'


def test_same_digest_in_wrong_file_does_not_bless_named_target(tmp_path):
    c = {}
    good = add(c, tmp_path, 'other.json', {'position': 1.0})
    add(c, tmp_path, 'result.json', {'position': 2.0})
    add(c, tmp_path, 'audit.json', {'source_hashes': {'/store/result.json': good}})
    index = HashLinks(c, {})
    with pytest.raises(ValueError, match='bytes disagree'):
        index.document('audit.json', index.read('audit.json'))


def test_absent_target_is_rejected(tmp_path):
    c = {}
    add(c, tmp_path, 'audit.json', {'source_hashes': {'/store/missing.json': '0'*64}})
    index = HashLinks(c, {})
    with pytest.raises(ValueError, match='absent'):
        index.document('audit.json', index.read('audit.json'))


def test_mutation_after_inventory_verification_is_rejected(tmp_path):
    c = {}
    add(c, tmp_path, 'result.json', {'position': 1.0})
    index = HashLinks(c, {})
    c['result.json']['path'].write_text('{}')
    with pytest.raises(ValueError, match='changed while reading'):
        index.read('result.json')


def test_unknown_digest_and_scientific_fields_are_preserved(tmp_path):
    c = {}
    value = dict(scientific_hash='a'*64, seconds=2.0, position=3.0,
                 nuisance=dict(seconds=4.0, alpha=5.0), gate=True)
    add(c, tmp_path, 'result.json', value)
    index = HashLinks(c, {})
    assert index.document('result.json', index.read('result.json')) == value


def relocation_fixture(tmp_path, *, corrupt=False):
    c = {}
    old = {'value': 3.0, 'input': '/store/stage1/input.json'}
    new = relocate_paths(old, '/store/stage1', '/store/stage2/cache')
    original_sha = add(c, tmp_path, 'stage1/result.json', old)
    target_sha = add(c, tmp_path, 'stage2/cache/result.json', new)
    original = dict(original_root='/store/stage1', relocated_root='/store/stage2/cache',
                    source_hashes={'result.json': original_sha},
                    relocated_hashes={'result.json': target_sha}, scientific_values_unchanged=True)
    proof_sha = add(c, tmp_path, 'stage2/cache-relocation.json', original)
    copied = relocate_paths(original, '/store/stage2', '/store/stage3/current')
    if corrupt:
        copied['relocated_hashes']['result.json'] = '0'*64
    copied_sha = add(c, tmp_path, 'stage3/current/cache-relocation.json', copied)
    target_copy_sha = add(c, tmp_path, 'stage3/current/cache/result.json',
                          relocate_paths(new, '/store/stage2', '/store/stage3/current'))
    add(c, tmp_path, 'stage3/relocation.json', dict(
        original_root='/store/stage2', relocated_root='/store/stage3/current',
        source_hashes={'cache/result.json': target_sha, 'cache-relocation.json': proof_sha},
        relocated_hashes={'cache/result.json': target_copy_sha,
                          'cache-relocation.json': copied_sha}, scientific_values_unchanged=True))
    return c


def test_historical_relocation_requires_verified_outer_edge_and_path_only_copy(tmp_path):
    c = relocation_fixture(tmp_path)
    index = HashLinks(c, {})
    copied = 'stage3/current/cache-relocation.json'
    assert index.historical_relocations == {copied: 'stage2/cache-relocation.json'}
    value = index.document(copied, index.read(copied))
    assert value['relocated_hashes']['result.json'] == '<VERIFIED_FILE>/stage2/cache/result.json'


def test_corrupt_historical_hash_is_rejected_even_if_outer_copy_binding_matches(tmp_path):
    with pytest.raises(ValueError, match='Unverified historical'):
        HashLinks(relocation_fixture(tmp_path, corrupt=True), {})


def test_historical_copy_without_outer_evidence_is_rejected(tmp_path):
    c = relocation_fixture(tmp_path)
    del c['stage3/relocation.json']
    with pytest.raises(ValueError, match='Unverified historical'):
        HashLinks(c, {})


def test_changed_target_value_remains_visible_to_comparison(tmp_path):
    c = {}
    sha = add(c, tmp_path, 'result.json', {'position': 1.0})
    add(c, tmp_path, 'audit.json', {'path': '/store/result.json', 'sha256': sha})
    original = HashLinks(c, {})
    first = original.document('result.json', original.read('result.json'))
    changed = copy.deepcopy(c)
    sha = add(changed, tmp_path/'changed', 'result.json', {'position': 2.0})
    add(changed, tmp_path/'changed', 'audit.json', {'path': '/store/result.json', 'sha256': sha})
    second = HashLinks(changed, {})
    assert first != second.document('result.json', second.read('result.json'))
    assert second.document('audit.json', second.read('audit.json'))['sha256'] == \
        '<VERIFIED_FILE>/result.json'


def test_opaque_historical_copy_keeps_original_verified_bindings(tmp_path):
    c = relocation_fixture(tmp_path)
    value = json.loads(c['stage3/current/cache-relocation.json']['path'].read_text())
    name = 'stage4/source-export/cache-relocation.json'
    add(c, tmp_path, name, value)
    index = HashLinks(c, {})
    assert name in index.historical_relocations
    assert index.document(name, index.read(name))['relocated_hashes']['result.json'] == \
        '<VERIFIED_FILE>/stage2/cache/result.json'


def test_nested_process_roles_remain_distinct_flat_filenames(tmp_path):
    c = {}
    group = 'ALGO02/worker/read_receipts'
    first = add(c, tmp_path, group+'/100.json', {})
    second = add(c, tmp_path, group+'/200.json', {})
    proofs = {group: {'roles': {100: 'root-0/child-0', 200: 'root-1/child-0'}}}
    index = HashLinks(c, proofs)
    mapped = index.mapping({'read_receipts/100.json': first, 'read_receipts/200.json': second},
                           '/store/ALGO02/worker', 'descriptor.json', '/files', '/store')
    assert set(mapped) == {'read_receipts/root-0.child-0.json',
                           'read_receipts/root-1.child-0.json'}
