"""Compact publication copying is deterministic, reversible and source preserving."""

import gzip
from pathlib import Path

import pytest

import bundle_publication as bundle


def test_large_json_copy_is_deterministic_roundtrips_and_preserves_source(tmp_path):
    source = tmp_path / 'source.json'
    raw = bundle.json_bytes({'proof': list(range(60000))})
    source.write_bytes(raw)
    first = bundle.copy_artifact(source, tmp_path / 'a', 'proofs/large.json')
    second = bundle.copy_artifact(source, tmp_path / 'b', 'proofs/large.json')
    assert first == second
    assert first['published_path'] == 'proofs/large.json.gz'
    output = tmp_path / 'a' / first['published_path']
    assert gzip.decompress(output.read_bytes()) == raw
    assert output.read_bytes()[4:8] == b'\0'*4
    assert source.read_bytes() == raw
    assert first['source_sha256'] == first['published_content_sha256'] == bundle.sha(raw)
    assert first['published_sha256'] == bundle.sha(output.read_bytes())


@pytest.mark.parametrize('name', ['../escape.json', '/escape.json', 'private/source-export/proof.json',
                                 'bank.npz', 'raw.iq', 'full.npy'])
def test_publication_refuses_unsafe_private_and_full_array_artifacts(tmp_path, name):
    source = tmp_path / 'source.json'
    source.write_text('{}')
    with pytest.raises(ValueError):
        bundle.copy_artifact(source, tmp_path / 'publication', name)


def test_copy_refuses_symlink_sources(tmp_path):
    source = tmp_path / 'source.json'
    source.write_text('{}')
    alias = tmp_path / 'alias.json'
    alias.symlink_to(source)
    with pytest.raises(ValueError, match='symbolic link'):
        bundle.copy_artifact(alias, tmp_path / 'publication', 'proof.json')


def test_compact_job_map_omits_only_redundant_result_and_pins_original(tmp_path):
    source = tmp_path / 'jobs.json'
    original = [{'job': {'job_id': 'id', 'result': {'large': [1]*1000},
                         'input_sha256': 'sha256:input', 'terminal': {'sha256': 'sha256:proof'}},
                 'terminal_receipt': {'sha256': 'sha256:proof'}, 'historical_read_audit_verified': True}]
    raw = bundle.json_bytes(original)
    source.write_bytes(raw)
    compact = bundle.compact_public_jobs(source)
    assert compact['original_file_sha256'] == bundle.sha(raw)
    assert 'result' not in compact['records'][0]['job']
    assert compact['records'][0]['job']['terminal'] == original[0]['job']['terminal']
    assert compact['records'][0]['terminal_receipt'] == original[0]['terminal_receipt']
    assert source.read_bytes() == raw
