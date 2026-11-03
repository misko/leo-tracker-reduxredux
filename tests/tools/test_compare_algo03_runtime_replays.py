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


@pytest.mark.parametrize('relative', [False, True])
def test_runtime_sources_must_match_receipt_and_runtime_manifest(tmp_path, relative):
    a, b = tmp_path/'a', tmp_path/'b'
    r0, r1 = tmp_path/'r0', tmp_path/'r1'
    for root, runtime in [(a, r0), (b, r1)]:
        fixture(root)
        source = runtime/'tools/retry.py'
        source.parent.mkdir(parents=True)
        source.write_text('tested source '+runtime.name)
        sha = hashlib.sha256(source.read_bytes()).hexdigest()
        write(runtime/'runtime-manifest.json', dict(files_sha256={'tools/retry.py': sha}))
        key = 'tools/retry.py' if relative else str(source)
        write(root/'recovery/source.json', dict(source_hashes={key: sha}))
    assert compare(a, b, r0, r1)['passed']
    source = r1/'tools/retry.py'
    source.write_text('unqualified change')
    with pytest.raises(ValueError, match='Changed runtime source receipt'):
        compare(a, b, r0, r1)
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    key = 'tools/retry.py' if relative else str(source)
    write(b/'recovery/source.json', dict(source_hashes={key: sha}))
    with pytest.raises(ValueError, match='Changed runtime source receipt'):
        compare(a, b, r0, r1)


def test_elapsed_deadlines_only_accounted_when_both_stages_finish(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    for root, budget in [(a, 350.), (b, 600.)]:
        fixture(root)
        write(root/'recovery/stage.json', dict(status='complete', returncode=0,
                                             seconds=20., budget_seconds=budget))
    r = compare(a, b, tmp_path/'r0', tmp_path/'r1')
    assert r['passed'] and len(r['completed_stage_deadline_differences']) == 1
    write(b/'recovery/stage.json', dict(status='complete', returncode=0,
                                     seconds=600., budget_seconds=600.))
    assert not compare(a, b, tmp_path/'r0', tmp_path/'r1')['passed']
