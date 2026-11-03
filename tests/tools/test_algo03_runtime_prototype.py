"""Research compositions must fail closed on unbound or changed numerical files."""

import hashlib
import json

import pytest
from algo03_runtime_prototype_verify import verify


def bind(tmp_path, monkeypatch, files):
    raw = json.dumps(dict(kind='algo03-runtime-research-prototype-v1', files_sha256=files))
    (tmp_path/'runtime-manifest.json').write_text(raw)
    monkeypatch.setenv('LEO_ALGO03_RESEARCH_RUNTIME_SHA256',
                       hashlib.sha256(raw.encode()).hexdigest())


def test_explicit_pin_and_member_bytes_required(tmp_path, monkeypatch):
    path = tmp_path/'kernel.py'
    path.write_text('original')
    bind(tmp_path, monkeypatch, {'kernel.py': hashlib.sha256(path.read_bytes()).hexdigest()})
    assert verify(tmp_path)['kind'] == 'algo03-runtime-research-prototype-v1'
    path.write_text('changed')
    with pytest.raises(ValueError, match='Changed runtime member'):
        verify(tmp_path)
    monkeypatch.delenv('LEO_ALGO03_RESEARCH_RUNTIME_SHA256')
    with pytest.raises(ValueError, match='pin'):
        verify(tmp_path)


def test_empty_or_escaping_inventory_rejected(tmp_path, monkeypatch):
    bind(tmp_path, monkeypatch, {})
    with pytest.raises(ValueError, match='Empty'):
        verify(tmp_path)
    bind(tmp_path, monkeypatch, {'../outside': '0'*64})
    with pytest.raises(ValueError, match='Changed runtime member'):
        verify(tmp_path)
