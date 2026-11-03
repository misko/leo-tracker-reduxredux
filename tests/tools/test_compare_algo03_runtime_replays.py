import hashlib
import json

import pytest
from compare_algo03_runtime_replays import compare


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture(root):
    trial = root/'recovery/trial/control.json'
    write(trial, dict(arms={a: dict(objective=2.5, owners={'point': 42})
                            for a in ('c0', 'fitted_c')}, seconds=1.))
    write(root/'recovery/read_receipts/42.json', dict(pid=42, parent_pid=41,
                                                    python_spawns=[], denied_paths=[]))
    write(root/'terminal.json', dict(state='complete', failure=None, read_audit=dict(
        verified=True, all_launched_processes_accounted=True, receipts=1,
        expected=1, root_process_id=42, supervisor_process_id=41, denied_paths=[]),
        source_receipts={
            str(trial): hashlib.sha256(trial.read_bytes()).hexdigest()}))
    return trial


def test_exact_science_with_relocated_verified_receipts(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    fixture(a)
    p = fixture(b)
    d = json.loads(p.read_text())
    d['seconds'] = 99.
    write(p, d)
    t = json.loads((b/'terminal.json').read_text())
    t['source_receipts'][str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    write(b/'terminal.json', t)
    assert compare(a, b, tmp_path/'r0', tmp_path/'r1')['passed']
    d['arms']['c0']['objective'] += 1e-10
    write(p, d)
    with pytest.raises(ValueError, match='changed result receipt'):
        compare(a, b, tmp_path/'r0', tmp_path/'r1')
    t['source_receipts'][str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    write(b/'terminal.json', t)
    result = compare(a, b, tmp_path/'r0', tmp_path/'r1')
    assert not result['passed']
    assert result['differences'][0]['path'].endswith('/c0/objective')


def test_missing_arm_rejected(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    fixture(a)
    p = fixture(b)
    d = json.loads(p.read_text())
    del d['arms']['fitted_c']
    write(p, d)
    with pytest.raises(ValueError, match='Missing calibration arm'):
        compare(a, b, tmp_path/'r0', tmp_path/'r1')


def test_missing_process_receipt_rejected(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    fixture(a)
    fixture(b)
    (b/'recovery/read_receipts/42.json').unlink()
    with pytest.raises(ValueError, match='Process read receipts'):
        compare(a, b, tmp_path/'r0', tmp_path/'r1')
