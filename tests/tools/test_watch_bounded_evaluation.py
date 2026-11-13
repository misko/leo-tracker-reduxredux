import json
import subprocess

import pytest

from tools import watch_bounded_evaluation as watch


def service(monkeypatch, text, code=0):
    monkeypatch.setattr(watch.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(
        a, code, stdout=text, stderr='' if code == 0 else 'manager unavailable'))


def report(root, side, statuses):
    path = root / 'cohort' / 'DS26-0002-r0' / side / 'report.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(statuses=statuses)))


def test_live_service_does_not_finish_with_partial_reports(tmp_path, monkeypatch):
    service(monkeypatch, 'LoadState=loaded\nActiveState=active\nMainPID=123\n')
    report(tmp_path, 'baseline', {'complete': 1})
    status = watch.snapshot('unit', tmp_path, 2)
    assert not status['service_stopped']
    assert not status['all_reports_complete']
    assert status['reported_workers'] == 1


def test_collected_service_requires_all_reports_and_separate_science_audit(tmp_path, monkeypatch):
    service(monkeypatch, 'LoadState=not-found\nActiveState=inactive\n')
    report(tmp_path, 'baseline', {'complete': 1})
    report(tmp_path, 'candidate', {'complete': 1})
    status = watch.snapshot('unit', tmp_path, 2)
    assert status['service_stopped'] and status['all_reports_complete']
    assert 'separate' in status['scientific_validation']


def test_unreachable_manager_does_not_mean_terminal(tmp_path, monkeypatch):
    service(monkeypatch, '', 1)
    status = watch.snapshot('unit', tmp_path, 2)
    assert not status['service_stopped']
    assert status['service_error'] == 'manager unavailable'


def test_manager_timeout_does_not_mean_terminal(tmp_path, monkeypatch):
    def expired(*args, **kwargs):
        raise subprocess.TimeoutExpired('systemctl', 15)
    monkeypatch.setattr(watch.subprocess, 'run', expired)
    status = watch.snapshot('unit', tmp_path, 2)
    assert not status['service_stopped']
    assert status['service_error'] == 'manager query timed out'


def test_terminal_failure_and_unreadable_report_remain_visible(tmp_path, monkeypatch):
    service(monkeypatch, 'LoadState=loaded\nActiveState=failed\nResult=exit-code\n')
    report(tmp_path, 'baseline', {'failed': 1})
    report(tmp_path, 'candidate', {'complete': 1})
    path = tmp_path / 'cohort/DS26-0002-r0/candidate/report.json'
    path.write_text('{')
    status = watch.snapshot('unit', tmp_path, 2)
    assert status['service_stopped'] and not status['all_reports_complete']
    assert status['reports'][0]['statuses'] == {'failed': 1}
    assert len(status['read_errors']) == 1


def test_interval_cannot_poll_more_often_than_five_minutes(tmp_path):
    with pytest.raises(SystemExit) as exc:
        watch.main(['--unit', 'unit', '--archive', str(tmp_path),
                    '--output', str(tmp_path / 'status.json'), '--interval', '30'])
    assert exc.value.code == 2
