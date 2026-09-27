import hashlib
import importlib.util
import json
import subprocess
import time
from pathlib import Path

import pytest

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("arm_remote_run",HERE/"remote_run.py")
r=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(r)


def sha(data): return hashlib.sha256(data).hexdigest()


def binding(tmp_path):
    hosts=tmp_path/"known_hosts"; hosts.write_bytes(b"pinned host key\n")
    password=tmp_path/"password"; password.write_bytes(b"secret\n")
    receipt=tmp_path/"deployment.json"
    deployment={"receipt_id":"current-v059","outcome":"success","returned_serial":r.SERIAL,
        "returned_firmware":"v0.59-plutoplus-spf-dual-rx-counter-fix","plan":{"host":r.HOST,
            "fit_sha256":"a"*64,"return_iio_layout":"tx-capable-2r2t-profile-tandem-v1"},
        "host_key_rotation":{"replacement_known_hosts_sha256":sha(hosts.read_bytes())},
        "read_only_return_attestation":{"fit_sha256":"a"*64,"qspi_sha256":"b"*64}}
    receipt.write_text(json.dumps(deployment))
    value={"schema":"org.leo.research.arm-stateless-remote-binding/v1","host":r.HOST,"serial":r.SERIAL,
        "firmware":deployment["returned_firmware"],"fit_sha256":"a"*64,"qspi_sha256":"b"*64,
        "deployment_receipt":str(receipt),"deployment_receipt_sha256":r.digest_path(receipt),
        "deployment_receipt_id":"current-v059","known_hosts":str(hosts),
        "known_hosts_sha256":sha(hosts.read_bytes()),"password_file":str(password)}
    path=tmp_path/"binding.json"; path.write_text(json.dumps(value)); return path,value,deployment


def test_binding_requires_current_receipt_host_key_and_firmware_hashes(tmp_path):
    path,value,_=binding(tmp_path)
    assert r.validate_binding(path)["firmware"].startswith("v0.59")
    value["fit_sha256"]="c"*64; path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match="firmware hashes"): r.validate_binding(path)


def test_binding_refuses_host_key_or_receipt_drift(tmp_path):
    path,value,_=binding(tmp_path)
    Path(value["known_hosts"]).write_text("rotated\n")
    with pytest.raises(ValueError,match="known-hosts"): r.validate_binding(path)


def test_binding_accepts_exactly_one_identity_file_authentication(tmp_path):
    path,value,_=binding(tmp_path)
    identity=tmp_path/"identity"; identity.write_text("private key placeholder")
    value.pop("password_file"); value["identity_file"]=str(identity); path.write_text(json.dumps(value))
    assert r.validate_binding(path)["identity_file"]==str(identity)
    value["password_file"]=str(identity); path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match="schema"): r.validate_binding(path)


def test_schedule_is_rotated_and_prefix_is_explicit():
    cases=[{"case_id":str(k)} for k in range(4)]
    rows=r.schedule(cases,3)
    assert [method for _,method,_ in rows[:3]]==list(r.METHODS)
    assert [method for _,method,_ in rows[3:6]]==[r.METHODS[1],r.METHODS[2],r.METHODS[0]]
    assert [method for _,method,_ in rows[6:9]]==[r.METHODS[2],r.METHODS[0],r.METHODS[1]]
    with pytest.raises(ValueError): r.schedule(cases,0)


def valid_result(case,method):
    receiver=lambda index:{"receiver":index,"result":{"confirmation_count":1,
        "rank":{"order":[0,1,2,3,4,5]},"confirmations":[{"candidate_count":1}]}}
    return {"schema":"org.leo.research.arm-stateless-probe-result/v1","method":method,
        "case_id":case["case_id"],"rate_hz":case["rate_hz"],"edge":case["edge"],"warmups":1,
        "repetitions":[{"index":k,"receivers":[receiver(0),receiver(1)],
                        "visit_cpu_ms":1.0,"visit_wall_ms":1.1} for k in range(3)]}


def test_result_validation_requires_complete_both_rx_measurement():
    case={"case_id":"case","rate_hz":2_500_000,"edge":"lower"}; row=valid_result(case,r.METHODS[0])
    r.validate_result(row,case,r.METHODS[0])
    row["repetitions"][1]["receivers"].pop()
    with pytest.raises(ValueError,match="accounting"): r.validate_result(row,case,r.METHODS[0])


def test_remote_scratch_cleans_exact_registered_paths_after_failure():
    commands=[]
    state={"temporary_files_removed":False}
    def run(command,data=None,timeout=0):
        commands.append(command)
        return b"/tmp/leo-arm-stateless.Ab12Z9\n" if command.startswith("mktemp") else b""
    with pytest.raises(RuntimeError,match="boom"):
        with r.remote_scratch(run,["probe","case-00.ci16"],state): raise RuntimeError("boom")
    assert commands[-2]=="rm -f -- /tmp/leo-arm-stateless.Ab12Z9/probe /tmp/leo-arm-stateless.Ab12Z9/case-00.ci16"
    assert commands[-1]=="rmdir -- /tmp/leo-arm-stateless.Ab12Z9"
    assert state["temporary_files_removed"] is True


@pytest.mark.parametrize("text",[
    "memory_available_kib=163839\ntmp_available_kib=98304\n",
    "memory_available_kib=200000\ntmp_available_kib=98303\n",
    "memory_available_kib=200000\n",
])
def test_capacity_refuses_low_or_incomplete_target(text):
    with pytest.raises(ValueError): r.parse_capacity(text)


def test_remote_deadline_is_bounded_and_preserves_argv_quoting():
    shell=r.deadline_shell(["/tmp/probe","case with space"],15)
    assert "sleep 15" in shell and "'case with space'" in shell
    with pytest.raises(ValueError): r.deadline_shell(["probe"],91)


def test_remote_deadline_does_not_hold_stdout_open_after_fast_child():
    started=time.monotonic()
    result=subprocess.run(["sh","-c",r.deadline_shell(["/bin/true"],2)],capture_output=True,timeout=1)
    assert result.returncode==0
    assert time.monotonic()-started < 1


def test_remote_deadline_terminates_slow_child_without_lingering_guard():
    started=time.monotonic()
    result=subprocess.run(["sh","-c",r.deadline_shell(["sleep","20"],1)],capture_output=True,timeout=3)
    assert result.returncode != 0
    assert 0.8 < time.monotonic()-started < 3


def test_timer_margin_uses_finite_timer_and_refuses_active(monkeypatch):
    now=time.time()
    responses=[subprocess.CompletedProcess([],3),
        subprocess.CompletedProcess([],0,stdout=json.dumps([{"unit":"leo-v052-adaptive.timer",
            "next":int((now+120)*1_000_000)}]))]
    monkeypatch.setattr(r.subprocess,"run",lambda *args,**kwargs: responses.pop(0))
    result=r.timer_margin(90)
    assert result["clock"]=="CLOCK_REALTIME" and result["remaining_seconds"] > 119

    monkeypatch.setattr(r.subprocess,"run",lambda *args,**kwargs: subprocess.CompletedProcess([],0))
    with pytest.raises(RuntimeError,match="service is active"): r.timer_margin(30)
