"""Fresh-process timing rejects worker failures and isolates paired measurements."""

import json
import subprocess
from pathlib import Path

import benchmark_algo07v3_covariance_threads as benchmark
import pytest
from probe_algo07v3_blas_threads import digest


@pytest.mark.parametrize('fail', [False, True])
@pytest.mark.parametrize('timeout', [None, 4])
def test_each_side_gets_a_new_process_and_failure_is_not_a_timing(
    monkeypatch, tmp_path, fail, timeout
):
    capture, output = tmp_path / 'capture', tmp_path / 'output'
    capture.mkdir()
    (capture / 'hardest.npz').write_bytes(b'fake input for orchestration only')
    (capture / 'hardest.json').write_text(json.dumps(
        dict(arrays_sha256=digest(capture / 'hardest.npz'))))
    argv = ['probe', '--capture', str(capture), '--output', str(output), '--threads', '2']
    if timeout is not None:
        argv += ['--thread-timeout', str(timeout)]
    monkeypatch.setattr(benchmark.sys, 'argv', argv)
    monkeypatch.setenv('OPENBLAS_THREAD_TIMEOUT', '31')
    calls = []

    def run(command, **kwargs):
        target = Path(command[command.index('--worker') + 1])
        assert target not in calls
        assert kwargs['env']['OPENBLAS_NUM_THREADS'] == '1'
        assert kwargs['env']['OMP_NUM_THREADS'] == '1'
        assert kwargs['env'].get('OPENBLAS_THREAD_TIMEOUT') == (
            None if timeout is None else str(timeout))
        assert kwargs['check'] and kwargs['timeout'] == 60
        calls.append(target)
        if fail and len(calls) == 2:
            raise subprocess.CalledProcessError(1, command)
        side = command[command.index('--side') + 1]
        (target / 'result.json').write_text(json.dumps(dict(
            side=side, seconds=1., cpu_seconds=1., exact=True)))

    monkeypatch.setattr(benchmark.subprocess, 'run', run)
    if fail:
        with pytest.raises(subprocess.CalledProcessError):
            benchmark.main()
        assert not (output / 'result.json').exists()
        assert (calls[0] / 'result.json').exists()
    else:
        benchmark.main()
        result = json.loads((output / 'result.json').read_bytes())
        assert len(calls) == 12 and result['fresh_process_per_side']
        assert [r['side'] for r in result['rows'][:4]] == [
            'baseline', 'candidate', 'candidate', 'baseline']
