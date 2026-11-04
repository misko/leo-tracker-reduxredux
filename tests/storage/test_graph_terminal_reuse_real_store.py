"""Exercise the research port against real six-stage stores and contracts."""
import copy
import importlib
import json
import runpy
from pathlib import Path

import pytest

from leo.contracts.digests import canonical_digest
from leo.storage.fast_graph_position import FastGraphPositionStore
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
from leo.storage.fast_scan import FastScanStore
from leo.storage.graph_terminal_reuse import (
    FastGraphPositionStoreV6ReadReuse,
    GraphTerminalReader,
    terminal_read_chain,
)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False))


@pytest.fixture
def completed_chain(tmp_path):
    # Reuse the existing contract's fixture factory without changing its goldens
    # or importing scientific workers/dependencies into this portable test.
    fixture = Path(__file__).parents[1] / 'contracts/test_fast_graph_position_v2.py'
    v2 = runpy.run_path(str(fixture))['terminal']()
    inventory = dict(kind='fast-scan-source', recording_name='fixture', segments=[{}])
    inventory_path = tmp_path / 'fast-scan-inputs/recording.json'
    write(inventory_path, inventory)
    native = FastScanStore(tmp_path).publish_tracking_input('run', dict(source=dict(
        session_id='recording', input_manifest_sha256=canonical_digest(inventory))))
    store = FastGraphPositionStore(tmp_path)
    job = next(store.inputs())
    v2['input_sha256'] = job['input_sha256']
    v2['baseline']['input_sha256'] = job['input_sha256']
    value = v2['baseline']
    paths = []
    for version in range(1, 7):
        if version > 1:
            module = importlib.import_module(f'leo.storage.fast_graph_position_v{version}')
            store = getattr(module, f'FastGraphPositionStoreV{version}')(tmp_path)
            job = store.job(job)
            if version == 2:
                value = v2
            else:
                contract = importlib.import_module(f'leo.contracts.fast_graph_position_v{version}')
                old = value
                value = dict(schema_version=version, kind=old['kind'],
                             model_version=contract.MODEL_VERSION, state='complete',
                             input_sha256=old['input_sha256'], session_id=old['session_id'],
                             incumbent=old, candidate=None, position=copy.deepcopy(old['position']),
                             decision=f'ALGO{version:02d}_fallback', reference_usage='none',
                             future_TLE_used=False, matched_c_inputs=True, selected_arm='fitted_c',
                             incumbent_seconds=old['total_seconds'],
                             total_seconds=old['total_seconds'] + 1,
                             recovery_policy=getattr(contract, 'POLICY', '72h_30s'))
                value['numerical_seconds' if version == 3 else 'recovery_seconds'] = 1
        path = store.path(job['job_id']) / 'output/terminal.json'
        write(path, value)
        paths.append(path)
        store.update(job, state='complete')
        assert store.terminal(job)[0] == value
    original = FastGraphPositionStoreV6(tmp_path)
    reuse, ports = terminal_read_chain(tmp_path)
    assert original.terminal(job) == reuse.terminal(job)
    assert sum(p.hits for p in ports) > 0
    return original, reuse, job, native, inventory_path, paths


def assert_rejected(pair):
    original, reuse, job, *_ = pair
    errors = []
    for port in (original, reuse):
        with pytest.raises((ValueError, FileNotFoundError)) as caught:
            port.terminal(job)
        errors.append(type(caught.value))
    assert errors[0] is errors[1]


@pytest.mark.parametrize('which', ['native', 'inventory'])
def test_real_source_mutation_is_not_hidden_by_warm_entries(completed_chain, which):
    path = completed_chain[3 if which == 'native' else 4]
    value = json.loads(path.read_text())
    value['changed'] = True
    write(path, value)
    assert_rejected(completed_chain)


@pytest.mark.parametrize('stage', range(6))
def test_real_terminal_corruption_at_each_level(completed_chain, stage):
    path = completed_chain[5][stage]
    value = json.loads(path.read_text())
    value['reference_usage'] = 'GPS'
    write(path, value)
    assert_rejected(completed_chain)


@pytest.mark.parametrize('stage', range(6))
def test_real_deleted_terminal_at_each_level(completed_chain, stage):
    completed_chain[5][stage].unlink()
    assert_rejected(completed_chain)


def test_real_valid_outer_byte_change_preserves_original_result(completed_chain):
    original, reuse, job, *_, paths = completed_chain
    paths[-1].write_text(paths[-1].read_text() + '\n')
    assert original.terminal(job) == reuse.terminal(job)


def test_real_wrong_embedded_incumbent_is_rejected(completed_chain):
    path = completed_chain[5][-1]
    value = json.loads(path.read_text())
    # Both nested and outer accounting remain contract-valid but no longer bind
    # to the separately published incumbent that the job actually names.
    value['incumbent']['recovery_seconds'] += 1
    value['incumbent']['total_seconds'] += 1
    value['incumbent_seconds'] += 1
    value['total_seconds'] += 1
    write(path, value)
    assert_rejected(completed_chain)


@pytest.mark.parametrize('cls', [GraphTerminalReader, FastGraphPositionStoreV6ReadReuse])
def test_public_reader_uses_a_fresh_scope_per_operation(completed_chain, cls):
    original, _, job, native, *_ = completed_chain
    reader = cls(original.root)
    first = reader.terminal(job)
    first[0]['position']['latitude_deg'] = 0
    assert reader.terminal(job) == original.terminal(job)
    value = json.loads(native.read_text())
    value['changed'] = True
    write(native, value)
    with pytest.raises(ValueError):
        reader.terminal(job)
