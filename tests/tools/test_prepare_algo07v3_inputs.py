import hashlib
import json
from types import SimpleNamespace

import prepare_algo07v3_inputs as command
import pytest


def arguments(tmp_path):
    native = tmp_path/'native.json'
    native.write_text('{}')
    config = tmp_path/'config.json'
    config.write_text(json.dumps(dict(config={})))
    return SimpleNamespace(native_input=native, input_sha256='sha256:'+hashlib.sha256(
        native.read_bytes()).hexdigest(), track_config=config, output=tmp_path/'output',
        tle_root=tmp_path/'archive', screen_latitude=10., screen_longitude=20.)


def test_changed_native_bytes_fail_before_output_or_archive_access(tmp_path, monkeypatch):
    args = arguments(tmp_path)
    args.native_input.write_text('{"changed":true}')
    monkeypatch.setattr(command, 'prepare_native_scan', lambda *a, **k: pytest.fail('must not run'))
    with pytest.raises(ValueError, match='Native input'):
        command.run(args)
    assert not args.output.exists()


def test_preparation_result_is_not_claimed_as_position(tmp_path, monkeypatch):
    args = arguments(tmp_path)
    monkeypatch.setattr(command, 'prepare_native_scan', lambda *a, **k: dict(
        status='no_active_curvature', sky=None, tracks=dict(observations=[], tracks=[])))
    assert command.run(args) == 0
    result = json.loads((args.output/'summary.json').read_text())
    assert not result['position_estimated']
    assert result['status'] == 'no_active_curvature'
    assert set(result['source_files']) == {'launch.json', 'tracks.json'}
    with pytest.raises(FileExistsError):
        command.run(args)
