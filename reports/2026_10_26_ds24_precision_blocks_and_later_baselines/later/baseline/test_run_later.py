import json
from pathlib import Path
import sys
import time
import pytest

import run_later as r


def test_stages_run_full_discovery_and_original_retained_engine():
    stages = r.stages('LATER4-0001')
    assert [s[0] for s in stages] == ['algo02','cavity']
    assert stages[0][1][-2:] == ['--stage','all']
    assert stages[1][1][1] == str(r.OLD/'engine/ds24_engine.py')
    assert str(r.WORK) in stages[0][1] and str(r.WORK) in stages[1][1]


def test_aggregate_budget_does_not_reset_between_stages():
    began = time.monotonic()-179
    assert 0 < r.remaining_cap(began) <= 1
    with pytest.raises(TimeoutError):
        r.remaining_cap(time.monotonic()-181)


def test_unready_member_is_explicit_and_never_launched(tmp_path, monkeypatch):
    monkeypatch.setattr(r, 'HERE', tmp_path)
    out = r.one('LATER4-0002', {'prepared_ready':{'LATER4-0002':False}})
    assert out['status'] == 'not_ready' and out['stages'] == []
    assert out['arms'] == ['c0','fitted_c']
    assert json.loads((tmp_path/'LATER4-0002_baseline_execution.json').read_text()) == out
