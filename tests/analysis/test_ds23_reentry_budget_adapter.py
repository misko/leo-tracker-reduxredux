import importlib.util
from pathlib import Path


def test_budget_adapter_only_handles_declared_reentry_timeouts():
    path=Path(__file__).resolve().parents[2]/'reports/2026_10_22_ds23_reentry_family_cavity/full_DS23/repair_budget_fallbacks.py'
    spec=importlib.util.spec_from_file_location('reentry_budget_adapter_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    row=dict(status='failed',error='reentry stage budget_exhausted: TimeoutError(400second owner-reentry budget)')
    reentry=dict(status='budget_exhausted',error='TimeoutError(400second owner-reentry budget)')
    assert module.eligible(row,reentry)
    assert not module.eligible(dict(row,error='nominations failed'),reentry)
    assert not module.eligible(dict(row,status='complete'),reentry)
    assert not module.eligible(row,dict(reentry,status='failed',error='input missing'))
    assert not module.eligible(row,dict(reentry,status='complete'))
