import json

import benchmark_algo07v3_reassociation as benchmark
import pytest

from leo.analysis.localization_v3 import reassociation_admission as admission
from leo.application import localization_v3 as policy


@pytest.mark.parametrize('failure', [False, True])
def test_worker_checks_screens_profiles_conservative_and_restores_hooks(
        monkeypatch, tmp_path, failure):
    calls = []

    def baseline(*args):
        calls.append('baseline')
        return dict(answer=42)

    def candidate(*args):
        calls.append('candidate')
        return dict(answer=42)

    def conservative(*args, **kwargs):
        return dict(unchanged=kwargs)

    original_affinity = {2, 3, 4}
    affinities = []
    monkeypatch.setattr(benchmark.os, 'sched_getaffinity', lambda pid: original_affinity)
    monkeypatch.setattr(benchmark.os, 'sched_setaffinity',
                        lambda pid, mask: affinities.append(mask))
    monkeypatch.setattr(benchmark.oracle, 'screen', baseline)
    monkeypatch.setattr(admission, 'screen', candidate)
    monkeypatch.setattr(policy, 'refit_initial_position', conservative)

    def worker(*args):
        assert policy.refit_initial_position('prepared', rounds=3) == dict(unchanged=dict(rounds=3))
        assert admission.screen(None, 123, [1, 2], None) == dict(answer=42)
        if failure:
            raise RuntimeError('cancel')
        return 0

    monkeypatch.setattr(benchmark, 'worker', worker)
    if failure:
        with pytest.raises(RuntimeError, match='cancel'):
            benchmark.observed_worker(tmp_path, 2)
    else:
        assert benchmark.observed_worker(tmp_path, 2) == 0
    assert admission.screen is candidate and policy.refit_initial_position is conservative
    assert calls == ['candidate', 'baseline', 'candidate', 'candidate', 'baseline']
    assert affinities == [{2}, original_affinity]
    assert (tmp_path / 'conservative.pstats').is_file()
    assert json.loads((tmp_path / 'conservative.json').read_text())[0]['completed']
    rows = json.loads((tmp_path / 'screens.json').read_text())
    assert rows[0]['exact'] and len(rows[0]['rows']) == 4


def test_screen_difference_restores_affinity_without_success_receipt(monkeypatch, tmp_path):
    restored = []
    monkeypatch.setattr(benchmark.os, 'sched_getaffinity', lambda pid: {0, 1})
    monkeypatch.setattr(benchmark.os, 'sched_setaffinity', lambda pid, mask: restored.append(mask))
    monkeypatch.setattr(benchmark.oracle, 'screen', lambda *args: 2)
    def original(*args):
        return 1

    monkeypatch.setattr(admission, 'screen', original)
    monkeypatch.setattr(benchmark, 'worker', lambda *args: admission.screen(None, 123, [1], None))
    with pytest.raises(ValueError, match='Complete screen differs'):
        benchmark.observed_worker(tmp_path, 1)
    assert restored == [{0}, {0, 1}]
    assert admission.screen is original
    assert not (tmp_path / 'screens.json').exists()
