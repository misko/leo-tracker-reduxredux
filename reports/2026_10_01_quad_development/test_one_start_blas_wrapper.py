"""The wrapper changes acquisition and the startup timer, not fit configuration."""
import runpy
import sys
import types
from pathlib import Path


def test_wrapper_preserves_cli_and_other_worker_state(monkeypatch):
    runner=types.ModuleType('run_seed_limit');acquirer=types.ModuleType('acquire_blas')
    original_fit=object();runner.fit_localization_fast=original_fit
    runner.START=-1.;runner.acquire=object();acquirer.acquire_blas=object()
    argv=['run_one_start_blas.py','DS10-B01-S1','--seed-limit','1','--output','example.json']
    calls=[]
    def main():
        assert runner.START>0 and runner.acquire is acquirer.acquire_blas
        assert runner.fit_localization_fast is original_fit and sys.argv==argv
        calls.append(True)
    runner.main=main
    monkeypatch.setitem(sys.modules,'run_seed_limit',runner)
    monkeypatch.setitem(sys.modules,'acquire_blas',acquirer)
    monkeypatch.setattr(sys,'argv',argv)
    runpy.run_path(str(Path(__file__).with_name('run_one_start_blas.py')),run_name='__main__')
    assert calls==[True]
