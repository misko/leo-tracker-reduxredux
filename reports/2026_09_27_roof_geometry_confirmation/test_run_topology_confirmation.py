import json
import pytest
import run_topology_confirmation as runner


def configs(tmp_path,monkeypatch,frequency,reception):
    monkeypatch.setattr(runner,'HERE',tmp_path)
    monkeypatch.setattr(runner.original,'LOCATION',tmp_path)
    (tmp_path/'topology_frequency_parameters.json').write_text(json.dumps(frequency))
    (tmp_path/'topology_calibration.json').write_text(json.dumps(reception))


def test_both_models_must_bind_identical_filtered_population(tmp_path,monkeypatch):
    frequency=dict(topology_audit_sha256='audit',calibration_sessions=['cal'])
    reception=dict(frequency,topology_audit_sha256='old-population')
    configs(tmp_path,monkeypatch,frequency,reception)
    with pytest.raises(ValueError,match='exact audited calibration track population'):
        runner.frozen_models({'sessions':[dict(session_id='cal',split='calibration')]},'audit')


def test_unconverged_refit_never_enters_search(tmp_path,monkeypatch):
    frequency=dict(topology_audit_sha256='audit',calibration_sessions=['cal'],converged=False)
    reception=dict(topology_audit_sha256='audit',calibration_sessions=['cal'])
    configs(tmp_path,monkeypatch,frequency,reception)
    with pytest.raises(ValueError,match='has not converged'):
        runner.frozen_models({'sessions':[dict(session_id='cal',split='calibration')]},'audit')
