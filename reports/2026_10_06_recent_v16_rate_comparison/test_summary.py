"""Reporting tests keep unavailable and unconverged scans visible."""
import json
import pytest
import summarize as module

SCAN = dict(label='test', session_id='synthetic', sample_rate_hz=2500000,
            capture_utc='2026-10-05T18:00:00+00:00')


def write_pair(tmp_path, second_hash='same', converged=True):
    folder = tmp_path/'positions/test'
    folder.mkdir(parents=True)
    for arm, digest in [('fitted-c','same'), ('zero-c',second_hash)]:
        row = dict(distance_m=100., converged=converged, boundary=False,
            objective=40.,data_nll=39.,timing_prior_nll=1., kkt=.0001 if converged else 1.,
            windows=30, owner_rms_hz=60.,posterior_weighted_residual_rms_hz=50.,
            mean_signal_posterior=.9,input_sha256=digest,spec={'sigma_hz':125.},
            strong_soft_windows=27,strong_original_owner_windows=25,strong_changed_owner_windows=2,
            maximum_budgets_s={'search_s':8.},radius_km=4.,numbers=[1,2],best={'point_km':[.1,0.]})
        (folder/f'{arm}.json').write_text(json.dumps(row))


def test_missing_fit_not_zero_error(tmp_path, monkeypatch):
    monkeypatch.setattr(module,'WORK',tmp_path)
    row = module.inspect(SCAN)
    assert row['positions'] == {}
    assert row['passing_windows'] is None
    assert row['status'] == 'awaiting GLRT export'


def test_incomplete_json_is_visible_as_warning(tmp_path):
    path=tmp_path/'partial.json'
    path.write_text('{')
    module.READ_WARNINGS.clear()
    assert module.read(path) is None
    assert module.READ_WARNINGS[0]['path'] == str(path)


def test_unmatched_inputs_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(module,'WORK',tmp_path)
    write_pair(tmp_path, second_hash='different')
    with pytest.raises(AssertionError,match='input_sha256'):
        module.inspect(SCAN)


def test_unconverged_case_not_reported_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(module,'WORK',tmp_path)
    write_pair(tmp_path,converged=False)
    row = module.inspect(SCAN)
    assert row['status'] == 'position results: convergence incomplete'
    assert len(row['positions']) == 2
