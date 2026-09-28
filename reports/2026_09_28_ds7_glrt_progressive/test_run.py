"""The replay watchdog must escape per-call failure handling."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('progressive_runner', Path(__file__).with_name('run.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_deadline_escapes_call_failure_collection():
    with pytest.raises(runner.ReplayDeadline):
        try:
            runner.deadline(None, None)
        except Exception:
            pytest.fail('watchdog was swallowed by per-call exception collection')
