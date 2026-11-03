from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.cli import algo07_sample as module


def test_private_target_rejects_unrelated_or_production_process():
    with pytest.raises(ValueError, match='private research root'):
        module.private_target(dict(command=['python', '/srv/bulk/leo/output']),
                              Path('/srv/bulk/leo'))
    with pytest.raises(ValueError, match='does not name'):
        module.private_target(dict(command=['python', '/srv/bulk/leo/production']),
                              Path('/srv/bulk/leo/research/one'))


def test_sampling_records_corrupt_stacks_without_claiming_parity(tmp_path, monkeypatch):
    identity = dict(pid=42, start_ticks=111,
                    command=['python', '/srv/bulk/leo/research/one/worker.py'])
    monkeypatch.setattr(module, 'process_identity', lambda pid: identity)
    sampler = tmp_path/'py-spy'
    sampler.touch()
    output = tmp_path/'sample'

    def run(command, **kwargs):
        assert '--nonblocking' in command and kwargs['timeout'] == 35
        (output/'stacks.folded').write_bytes(b'worker;fit 12\ncorrupt\xff 7\n')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, 'run', run)
    result = module.sample(Namespace(pid=42, research_root=Path('/srv/bulk/leo/research/one'),
                                     output=output, duration=20, sampler=sampler))
    assert result['successful_sampling']
    assert result['valid_samples'] == 12 and result['corrupted_lines'] == 1
    assert not result['scientific_parity_checked'] and not result['descendant_coverage']


@pytest.mark.parametrize('timed_out', [False, True])
def test_reused_pid_or_sampler_timeout_cannot_pass(tmp_path, monkeypatch, timed_out):
    identities = iter([dict(pid=42, start_ticks=t,
                            command=['python', '/srv/bulk/leo/research/one/worker.py'])
                       for t in (111, 111 if timed_out else 222)])
    monkeypatch.setattr(module, 'process_identity', lambda pid: next(identities))
    sampler = tmp_path/'py-spy'
    sampler.touch()
    output = tmp_path/'sample'

    def run(command, **kwargs):
        if timed_out:
            raise module.subprocess.TimeoutExpired(command, kwargs['timeout'])
        (output/'stacks.folded').write_bytes(b'worker;fit 12\n')
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, 'run', run)
    result = module.sample(Namespace(pid=42, research_root=Path('/srv/bulk/leo/research/one'),
                                     output=output, duration=20, sampler=sampler))
    assert not result['successful_sampling']
    assert result['sampler_timed_out'] is timed_out
