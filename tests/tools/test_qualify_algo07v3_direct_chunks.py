import json
import os
import threading

import pytest
import qualify_algo07v3_direct_chunks as probe
from qualify_algo07v3_direct_chunks import choose, signature

from tests.analysis.test_joint_predictive_families import fixture


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('optimized', [True, False])
@pytest.mark.parametrize('owner', [True, False])
def test_only_direct_main_owner_receives_parallel_slots(enabled, optimized, owner):
    original, parallel = object(), object()
    selected = choose(original, parallel, enabled=enabled, optimized=optimized,
                      owner_pid=os.getpid() if owner else os.getpid() + 1000000,
                      owner_thread=threading.get_ident())
    assert (selected is parallel) == (enabled and not optimized and owner)


def test_other_thread_keeps_serial_and_sequence_ignores_only_measurements():
    original, parallel = object(), object()
    assert choose(original, parallel, enabled=True, optimized=False, owner_pid=os.getpid(),
                  owner_thread=threading.get_ident() + 1) is original
    assert signature([dict(optimized=False, phase_pairs=10, seconds=1, parallel=True)]) == \
        [(False, 10)]


@pytest.mark.parametrize('side', ['baseline', 'candidate'])
@pytest.mark.parametrize('fail', [False, True])
def test_native_hook_restores_both_aliases_and_preserves_actual_capture(
        monkeypatch, tmp_path, side, fail):
    original = probe.joint_density.two_family_phase_evidence
    recovery = probe.joint_recovery.two_family_phase_evidence
    monkeypatch.setattr(probe.os, 'sched_getaffinity', lambda pid: {0, 1, 2})
    monkeypatch.setattr(probe, 'library_info', lambda: [{'threads': 1}])

    def worker(*args):
        assert probe.joint_recovery.two_family_phase_evidence is not recovery
        probe.joint_recovery.two_family_phase_evidence(*fixture(), optimize_contractions=False)
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
    assert len(calls) == 1 and calls[0]['phase_pairs'] == 12
    assert calls[0]['parallel'] == (side == 'candidate')
    captured = json.loads((tmp_path / 'captures.json').read_bytes())
    assert captured['12']['sha256'] == probe.hashlib.sha256(
        (tmp_path / 'captures/12.npz').read_bytes()).hexdigest()
