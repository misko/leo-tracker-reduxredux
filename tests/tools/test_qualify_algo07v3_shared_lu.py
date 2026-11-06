import json

import pytest
import qualify_algo07v3_shared_lu as probe

from tests.analysis.test_joint_predictive_families import fixture


@pytest.mark.parametrize('side', ['baseline', 'candidate'])
@pytest.mark.parametrize('fail', [False, True])
def test_external_backend_is_restored_and_calls_retained(monkeypatch, tmp_path, side, fail):
    original = probe.joint_density.two_family_phase_evidence
    recovery = probe.joint_recovery.two_family_phase_evidence
    monkeypatch.setattr(probe, 'bind', lambda *args: (None, [], []))
    monkeypatch.setattr(probe, 'candidate', lambda factor: (original, ''))

    def worker(*args):
        assert probe.joint_recovery.two_family_phase_evidence is not recovery
        probe.joint_recovery.two_family_phase_evidence(*fixture())
        if fail:
            raise RuntimeError('failed worker')
        return 0

    monkeypatch.setattr(probe, 'worker', worker)
    if fail:
        with pytest.raises(RuntimeError, match='failed worker'):
            probe.native_worker(tmp_path, side)
    else:
        assert probe.native_worker(tmp_path, side) == 0
    assert probe.joint_density.two_family_phase_evidence is original
    assert probe.joint_recovery.two_family_phase_evidence is recovery
    calls = json.loads((tmp_path / 'kernel-calls.json').read_bytes())
    assert len(calls) == 1 and calls[0]['phase_pairs'] > 0
    assert calls[0]['optimized'] is True
