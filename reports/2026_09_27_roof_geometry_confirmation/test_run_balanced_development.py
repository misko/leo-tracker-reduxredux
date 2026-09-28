import json
import pytest
import run_balanced_development as runner


def test_existing_development_output_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'HERE', tmp_path)
    monkeypatch.setattr(runner.frozen.original, 'confirmation_entries',
        lambda: ([{'session_id':'scan'}], 'manifest', 'inventory'))
    path = tmp_path/'balanced-development-scan.json'
    path.write_text('original')
    with pytest.raises(FileExistsError):
        runner.run(0)
    assert path.read_text() == 'original'


def test_changed_models_cannot_enter_matched_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'HERE', tmp_path)
    monkeypatch.setattr(runner.frozen.original, 'confirmation_entries',
        lambda: ([{'session_id':'scan'}], 'manifest', 'inventory'))
    (tmp_path/'topology-search-scan.json').write_text(json.dumps(
        dict(finished=True, calibration_sha256='old')))
    monkeypatch.setattr(runner.frozen, 'frozen_audit', lambda: ({}, 'audit'))
    monkeypatch.setattr(runner.frozen, 'frozen_models', lambda *args:
        ({}, None, None, 1., 0., {'calibration_sha256':'changed'}))
    with pytest.raises(AssertionError):
        runner.run(0)
