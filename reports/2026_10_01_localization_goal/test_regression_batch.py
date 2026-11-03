import json
import sys

import pytest
from regression_batch import digest, execute, verify_sources


def test_supervisor_enforces_short_deadline_and_records_failure(tmp_path):
    result = execute([sys.executable, '-c', 'import time; time.sleep(5)'],
                     tmp_path, 'test', timeout_s=.05)
    assert result['timed_out'] and not result['within_budget']
    assert result['returncode'] < 0
    assert (tmp_path/'test.stdout.txt').exists()


def test_supervisor_success_and_existing_launch_guard(tmp_path):
    result = execute([sys.executable, '-c', 'print(42)'], tmp_path, 'test', timeout_s=5.)
    assert result['returncode'] == 0 and result['within_budget']
    assert (tmp_path/'test.stdout.txt').read_text().strip() == '42'
    (tmp_path/'test.launch.json').write_text(json.dumps(result))
    with pytest.raises(FileExistsError):
        execute([sys.executable, '-c', 'raise RuntimeError'], tmp_path, 'test')


def test_source_change_rejected(tmp_path):
    path = tmp_path/'source.py'
    path.write_text('x = 1\n')
    binding = {str(path): digest(path)}
    verify_sources(binding)
    path.write_text('x = 2\n')
    with pytest.raises(ValueError):
        verify_sources(binding)
