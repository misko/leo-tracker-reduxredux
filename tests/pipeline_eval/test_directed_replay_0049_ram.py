import fcntl
import json
import os
from pathlib import Path

import pytest

from reports.ALGO08.v3 import directed_replay_0049_ram as check


def test_requires_locked_inherited_description_and_exact_inode(tmp_path):
    expected = tmp_path/"gauss.lock"
    wrong = tmp_path/"other"
    expected.touch()
    wrong.touch()
    with wrong.open("rb") as file:
        with pytest.raises(ValueError,match="different inode"):
            check.locked_description(file.fileno(),expected)
    with expected.open("rb") as owner, expected.open("rb") as separate:
        with pytest.raises(ValueError,match="not already held"):
            check.locked_description(owner.fileno(),expected)
        fcntl.flock(owner,fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd = os.dup(owner.fileno())
        try:
            check.locked_description(fd,expected)
            with pytest.raises(ValueError,match="different open-file description"):
                check.locked_description(separate.fileno(),expected)
        finally:
            os.close(fd)


def test_readonly_explicit_mounts_and_real_lock_for_actual_worker():
    root = Path("/dev/shm/private")
    operands = ["/tmp/file-a","/tmp/file-b"]
    plan = {"original_source":{"files":operands}}
    for proof in (True,False):
        argv = check.command(root,plan,3 if proof else 2,13,proof=proof)
        mounts = [tuple(argv[i+1:i+3]) for i,name in enumerate(argv) if name=="--ro-bind"]
        scientific = [pair for pair in mounts if pair[0].startswith("/tmp/")]
        assert [(item,item) for item in operands] == scientific[:2]
        bound_lock = str(root/"proof.lock" if proof else check.replay.LOCK)
        assert (bound_lock,str(check.replay.LOCK)) in mounts
        assert "/srv/bulk" not in argv and "/mnt/qnap01" not in argv
        assert argv[-1] == ("proof" if proof else "sweep")


def test_nonresident_admission_declines_before_child_even_under_lock(monkeypatch,tmp_path):
    plan = {"original_source":{"files":["/tmp/a"]}}
    lock = tmp_path/"test.lock"
    lock.touch()
    monkeypatch.setattr(check.replay,"LOCK",lock)
    def nonresident(files):
        raise ValueError("nonresident")
    monkeypatch.setattr(check,"resident",nonresident)
    def unexpected(*args,**kwargs):
        pytest.fail("A nonresident admission started a child")
    monkeypatch.setattr(check,"invoke",unexpected)
    assert check.admitted(tmp_path,plan,{},123,{}) == {
        "admitted":False,"reason":"nonresident","field_event":{},
    }
    assert not (tmp_path/"intent.json").exists()


def test_priority_case_deferral_or_attempt_prevents_lower_priority_dispatch(monkeypatch,tmp_path):
    monkeypatch.setattr(check,"CAMPAIGN",tmp_path)
    case = dict(case="DS30-0218",outcome="pending",admission_state="pending",attempt=None,verified_pair=False)
    rows = tmp_path/"rows.jsonl"
    roles = [dict(case,algorithm=role) for role in ("installed","successor")]
    rows.write_text("\n".join(map(json.dumps,roles)))
    check.priority_clear()
    rows.write_text("\n".join(map(json.dumps,[roles[0],dict(roles[1],admission_state="deferred_storage_busy")])))
    with pytest.raises(ValueError, match="priority DS30-0218"):
        check.priority_clear()
    rows.write_text("\n".join(map(json.dumps,roles)))
    pair = tmp_path/"cases/DS30-0218/pair.json"
    pair.parent.mkdir(parents=True)
    pair.touch()
    with pytest.raises(ValueError, match="priority DS30-0218"):
        check.priority_clear()


def test_resident_source_and_zero_input_are_separate_predeclared_outcomes():
    clock = dict(exit_code=0,elapsed_s=4.,wrapper_input_blocks=24)
    result = dict(isolation=dict(operative_inherited_lock=True,private_probe_lock=False),
                  post_staged_source_mode="verified-tmpfs-only",python_usage=dict(input_blocks=6000),input_blocks=80)
    assert check.qualifications(clock,result,True,allow_code_io=True) == {
        "resident_source":True,"strict_zero_process_input":False,"qualified":True,
    }
    assert not check.qualifications(clock,result,True,allow_code_io=False)["qualified"]
    assert not check.qualifications(clock,result,False,allow_code_io=True)["qualified"]
    assert not check.qualifications(dict(clock,elapsed_s=12.01),result,True,allow_code_io=True)["qualified"]
