#!/usr/bin/env python3
"""Strict host-side saved-IQ ARM runner. It never starts or configures RF."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import math
import os
import re
import shlex
import subprocess
import tarfile
import time
from pathlib import Path
from typing import Callable, Iterator

HERE = Path(__file__).resolve().parent
HOST = "192.168.1.20"
SERIAL = "1040005e0b100007100010000bf33a5d4d"
METHODS = ("packed_builtin_fp64", "packed_fftw_fp64", "aligned_v5_fftw_fp32")
PIPELINE_LOCK = Path("/run/leo-adaptive-pipeline.lock")
MIN_MEMORY_KIB = 160 * 1024
MIN_TMPFS_KIB = 96 * 1024
MAX_SECONDS_LIMIT = 90
MIN_SECONDS_LIMIT = 30
TIMER_MARGIN_SECONDS = 15
FFTW3 = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot/usr/lib/libfftw3.so.3.6.10")


def digest_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def require_absolute_file(path: Path) -> None:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError(f"required absolute regular file: {path}")


def validate_binding(path: Path) -> dict:
    require_absolute_file(path)
    binding = json.loads(path.read_text())
    required = {
        "schema", "host", "serial", "firmware", "fit_sha256", "qspi_sha256",
        "deployment_receipt", "deployment_receipt_sha256", "deployment_receipt_id",
        "known_hosts", "known_hosts_sha256",
    }
    auth=set(binding)-required
    if set(binding)&required != required or auth not in ({"password_file"},{"identity_file"}) or binding["schema"] != "org.leo.research.arm-stateless-remote-binding/v1":
        raise ValueError("unexpected remote binding schema or fields")
    if binding["host"] != HOST or binding["serial"] != SERIAL:
        raise ValueError("remote binding targets the wrong host or serial")
    for key in ("fit_sha256", "qspi_sha256", "deployment_receipt_sha256", "known_hosts_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", binding[key]): raise ValueError(f"invalid {key}")
    known_hosts, receipt = map(Path, (binding["known_hosts"], binding["deployment_receipt"]))
    credential=Path(binding[next(iter(auth))])
    for item in (known_hosts, receipt, credential): require_absolute_file(item)
    if digest_path(known_hosts) != binding["known_hosts_sha256"]: raise ValueError("known-hosts identity changed")
    if digest_path(receipt) != binding["deployment_receipt_sha256"]: raise ValueError("deployment receipt changed")
    deployment = json.loads(receipt.read_text())
    if deployment.get("receipt_id") != binding["deployment_receipt_id"] or deployment.get("outcome") != "success":
        raise ValueError("deployment receipt identity/outcome differs")
    if deployment.get("returned_serial") != SERIAL or deployment.get("returned_firmware") != binding["firmware"]:
        raise ValueError("deployment receipt device identity differs")
    plan = deployment.get("plan", {})
    if plan.get("host") != HOST: raise ValueError("deployment receipt host differs")
    rotation = deployment.get("host_key_rotation", {})
    if rotation.get("replacement_known_hosts_sha256") != binding["known_hosts_sha256"]:
        raise ValueError("deployment receipt does not bind the selected host key")
    attestation = deployment.get("read_only_return_attestation", {})
    if attestation.get("fit_sha256") != binding["fit_sha256"] or attestation.get("qspi_sha256") != binding["qspi_sha256"]:
        raise ValueError("deployment receipt firmware hashes differ")
    if deployment.get("plan",{}).get("fit_sha256") != binding["fit_sha256"] or deployment.get("plan",{}).get("return_iio_layout") != "tx-capable-2r2t-profile-tandem-v1":
        raise ValueError("deployment plan does not bind the current FIT/layout")
    return binding


def load_payload(bundle: Path) -> tuple[dict, dict[Path, str]]:
    bundle = bundle.resolve(); manifest_path = bundle / "manifest.json"
    require_absolute_file(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "org.leo.research.arm-stateless-probe-bundle/v1": raise ValueError("wrong bundle schema")
    plan_path=HERE/"plan.json"; plan=json.loads(plan_path.read_text())
    if manifest.get("plan_sha256") != digest_path(plan_path): raise ValueError("bundle does not bind the frozen probe plan")
    public=lambda c:{k:c[k] for k in ("case_id","origin","split","rate_hz","edge","raw_npy")}
    if [public(c) for c in manifest["cases"]] != [public(c) for c in plan["cases"]]:
        raise ValueError("bundle case metadata differs from the frozen plan")
    if any(c["split"] not in ("dev","control") for c in manifest["cases"]): raise ValueError("non-development case in ARM bundle")
    build_path = HERE / "build.receipt.json"; build = json.loads(build_path.read_text())
    expected = {row["method"]: row["binary_sha256"] for row in build["builds"]}
    files = {manifest_path: digest_path(manifest_path), build_path: digest_path(build_path),
             plan_path:digest_path(plan_path),Path(__file__).resolve():digest_path(Path(__file__).resolve())}
    for item in build["builds"]:
        for name,expected_sha in item["sources_sha256"].items():
            source=Path(name); require_absolute_file(source)
            if digest_path(source)!=expected_sha: raise ValueError(f"scientific build source drift: {source}")
            files[source]=expected_sha
    for method in METHODS:
        path = HERE / method
        if digest_path(path) != expected[method]: raise ValueError(f"binary drift: {method}")
        files[path] = expected[method]
    if digest_path(FFTW3) != build["fp64_fftw_runtime_sha256"]: raise ValueError("FP64 FFTW runtime drift")
    files[FFTW3] = build["fp64_fftw_runtime_sha256"]
    for case in manifest["cases"]:
        if Path(case["raw_file"]).name != case["raw_file"] or not re.fullmatch(r"case-[0-9]{2}\.ci16",case["raw_file"]):
            raise ValueError("unsafe IQ bundle filename")
        raw = bundle / case["raw_file"]
        if digest_path(raw) != case["raw_file_sha256"]: raise ValueError(f"bundle IQ drift: {case['case_id']}")
        files[raw] = case["raw_file_sha256"]
    for template in manifest["templates"].values():
        for kind in ("exact", "control"):
            if Path(template[kind]).name != template[kind] or not re.fullmatch(r"template-[a-z0-9-]+\.c128",template[kind]):
                raise ValueError("unsafe template filename")
            path = bundle / template[kind]; expected_sha = template[kind + "_sha256"]
            if digest_path(path) != expected_sha: raise ValueError(f"template drift: {path}")
            files[path] = expected_sha
    return manifest, files


def schedule(cases: list[dict], case_limit: int) -> list[tuple[dict, str, int]]:
    if not 1 <= case_limit <= len(cases): raise ValueError("case-limit outside frozen plan")
    rows=[]
    for index, case in enumerate(cases[:case_limit]):
        order = METHODS[index % 3:] + METHODS[:index % 3]
        rows.extend((case, method, position) for position, method in enumerate(order))
    return rows


def parse_capacity(text: str) -> dict:
    fields={}
    for line in text.splitlines():
        key,sep,value=line.partition("=")
        if not sep or key in fields or not value.isdigit(): raise ValueError("malformed capacity response")
        fields[key]=int(value)
    if set(fields)!={"memory_available_kib","tmp_available_kib"}: raise ValueError("incomplete capacity response")
    if fields["memory_available_kib"] < MIN_MEMORY_KIB: raise ValueError("insufficient available ARM memory")
    if fields["tmp_available_kib"] < MIN_TMPFS_KIB: raise ValueError("insufficient ARM tmpfs")
    return fields


def payload_archive(stage: dict[Path,str], remote_names: dict[Path,str]) -> tuple[bytes,str]:
    checks="".join(f"{stage[path]}  {remote_names[path]}\n" for path in sorted(stage,key=lambda p:remote_names[p]))
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode="w") as archive:
        for path in sorted(stage,key=lambda p:remote_names[p]):
            data=path.read_bytes(); info=tarfile.TarInfo(remote_names[path]); info.size=len(data)
            info.mode=0o700 if remote_names[path] in METHODS else 0o600
            archive.addfile(info,io.BytesIO(data))
        data=checks.encode(); info=tarfile.TarInfo("SHA256SUMS"); info.size=len(data); info.mode=0o600
        archive.addfile(info,io.BytesIO(data))
    return out.getvalue(),checks


def timer_margin(max_seconds: int) -> dict:
    active=subprocess.run(["systemctl","is-active","--quiet","leo-v052-adaptive.service"],timeout=5)
    if active.returncode==0: raise RuntimeError("scheduled adaptive capture service is active")
    if active.returncode not in (3,): raise RuntimeError("cannot establish adaptive service inactivity")
    result=subprocess.run(["systemctl","list-timers","leo-v052-adaptive.timer","--all",
        "--output=json","--no-pager"],
        check=True,text=True,capture_output=True,timeout=5)
    rows=json.loads(result.stdout)
    if len(rows)!=1 or rows[0].get("unit")!="leo-v052-adaptive.timer" or type(rows[0].get("next")) is not int:
        raise RuntimeError("adaptive timer has no finite next-slot binding")
    next_usec=rows[0]["next"]
    remaining=next_usec/1_000_000-time.time()
    if remaining < max_seconds+TIMER_MARGIN_SECONDS: raise RuntimeError("insufficient margin before scheduled capture")
    return {"clock":"CLOCK_REALTIME","next_elapse_usec":next_usec,
            "remaining_seconds":remaining,"required_seconds":max_seconds+TIMER_MARGIN_SECONDS}


def parse_system_profile(text: str) -> dict:
    fields={}
    for line in text.splitlines():
        key,sep,value=line.partition("=")
        if not sep or key in fields: raise ValueError("malformed ARM system profile")
        fields[key]=value
    required={"uname","cpu_hardware","cpu_model","cpu_count","scaling_cur_freq_khz","scaling_governor"}
    if set(fields)!=required or not fields["cpu_count"].isdigit(): raise ValueError("incomplete ARM system profile")
    return fields


def validate_result(row: dict, case: dict, method: str) -> None:
    if row.get("schema") != "org.leo.research.arm-stateless-probe-result/v1" or row.get("method") != method:
        raise ValueError("wrong probe result schema/method")
    if row.get("case_id") != case["case_id"] or row.get("rate_hz") != case["rate_hz"] or row.get("edge") != case["edge"]:
        raise ValueError("probe returned the wrong case")
    if row.get("warmups") != 1 or not isinstance(row.get("repetitions"),list) or len(row["repetitions"]) != 3:
        raise ValueError("probe did not complete one warmup and three repetitions")
    for index, rep in enumerate(row["repetitions"]):
        if rep.get("index") != index or [x.get("receiver") for x in rep.get("receivers",[])] != [0,1]:
            raise ValueError("receiver/repetition accounting differs")
        for key in ("visit_cpu_ms","visit_wall_ms"):
            if type(rep.get(key)) not in (int,float) or not math.isfinite(rep[key]) or rep[key] <= 0: raise ValueError("invalid visit timing")
        for rx in rep["receivers"]:
            result=rx.get("result",{})
            if result.get("confirmation_count") != 1 or len(result.get("rank",{}).get("order",[])) != 6:
                raise ValueError("incomplete six-screen/one-confirmation result")
            confirmation=result.get("confirmations",[{}])[0]
            if confirmation.get("candidate_count") not in (0,1): raise ValueError("invalid candidate accounting")


def deadline_shell(argv: list[str], seconds: int) -> str:
    if not 1 <= seconds <= MAX_SECONDS_LIMIT: raise ValueError("invalid process deadline")
    command=shlex.join(argv)
    return ("set -eu; " + command + " & child=$!; "
            f"( sleep {seconds}; kill -TERM \"$child\" 2>/dev/null || :; sleep 1; kill -KILL \"$child\" 2>/dev/null || : ) </dev/null >/dev/null 2>&1 & guard=$!; "
            "set +e; wait \"$child\"; status=$?; set -e; kill \"$guard\" 2>/dev/null || :; wait \"$guard\" 2>/dev/null || :; exit \"$status\"")


@contextlib.contextmanager
def remote_scratch(run: Callable, intended_names: list[str], cleanup_state: dict | None = None) -> Iterator[str]:
    remote = run("mktemp -d /tmp/leo-arm-stateless.XXXXXX", timeout=5).decode().strip()
    if not re.fullmatch(r"/tmp/leo-arm-stateless\.[A-Za-z0-9]{6}",remote): raise ValueError("unexpected remote scratch path")
    try:
        yield remote
    finally:
        paths=[remote+"/"+name for name in intended_names]
        run("rm -f -- " + " ".join(map(shlex.quote,paths)), timeout=10)
        run("rmdir -- " + shlex.quote(remote), timeout=5)
        if cleanup_state is not None: cleanup_state["temporary_files_removed"]=True


@contextlib.contextmanager
def pipeline_lock() -> Iterator[None]:
    if not PIPELINE_LOCK.is_file(): raise RuntimeError("adaptive pipeline lock is missing")
    fd=os.open(PIPELINE_LOCK,os.O_RDWR)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error: raise RuntimeError("adaptive capture pipeline is active") from error
        yield
    finally:
        os.close(fd)


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding",required=True,type=Path)
    parser.add_argument("--bundle",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--case-limit",type=int,default=4)
    parser.add_argument("--max-seconds",type=int,default=90)
    args=parser.parse_args()
    if not MIN_SECONDS_LIMIT <= args.max_seconds <= MAX_SECONDS_LIMIT: raise ValueError("max-seconds must be in [30,90]")
    binding=validate_binding(args.binding.resolve()); manifest,all_files=load_payload(args.bundle)
    work=schedule(manifest["cases"],args.case_limit)
    selected_cases={c["case_id"] for c,_,_ in work}
    selected=[c for c in manifest["cases"] if c["case_id"] in selected_cases]
    templates={c["template_key"] for c in selected}
    stage={HERE/m:digest_path(HERE/m) for m in METHODS}; stage[FFTW3]=digest_path(FFTW3)
    for c in selected: stage[args.bundle.resolve()/c["raw_file"]]=c["raw_file_sha256"]
    for key in templates:
        t=manifest["templates"][key]
        for kind in ("exact","control"): stage[args.bundle.resolve()/t[kind]]=t[kind+"_sha256"]
    remote_names={p:("libfftw3.so.3" if p==FFTW3 else p.name) for p in stage}
    if len(set(remote_names.values()))!=len(remote_names): raise ValueError("remote payload name collision")
    args.output.mkdir(parents=True,exist_ok=False)
    archive,checks=payload_archive(stage,remote_names)
    report={"schema":"org.leo.research.arm-stateless-remote-result/v1","status":"started",
            "execution_environment":"physical_arm_saved_iq","qemu":False,
            "host":HOST,"serial":SERIAL,"firmware":binding["firmware"],"fit_sha256":binding["fit_sha256"],
            "binding_sha256":digest_path(args.binding.resolve()),"bundle_manifest_sha256":digest_path(args.bundle.resolve()/"manifest.json"),
            "build_receipt_sha256":digest_path(HERE/"build.receipt.json"),"probe_plan_sha256":digest_path(HERE/"plan.json"),
            "runner_sha256":digest_path(Path(__file__).resolve()),
            "case_limit":args.case_limit,"plan_complete":args.case_limit==len(manifest["cases"]),"max_seconds":args.max_seconds,
            "rf_collection":False,"firmware_written":False,"rows":[],"temporary_files_removed":False}
    protected_local=dict(all_files)
    protected_local[args.binding.resolve()]=report["binding_sha256"]
    protected_local[Path(binding["deployment_receipt"])]=binding["deployment_receipt_sha256"]
    protected_local[Path(binding["known_hosts"])]=binding["known_hosts_sha256"]
    report["local_hashes_before"]={str(path):expected for path,expected in protected_local.items()}
    def save(): (args.output/"receipt.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    started=time.monotonic(); deadline=started+args.max_seconds; work_deadline=deadline-15
    ssh_options=["-o","StrictHostKeyChecking=yes","-o","UserKnownHostsFile="+binding["known_hosts"],
                 "-o","GlobalKnownHostsFile=/dev/null","-o","ForwardAgent=no","-o","ConnectTimeout=5"]
    if "identity_file" in binding:
        ssh=["ssh","-o","BatchMode=yes","-o","IdentitiesOnly=yes","-o","IdentityAgent=none",
             "-i",binding["identity_file"],*ssh_options,"root@"+HOST]
    else:
        ssh=["sshpass","-f",binding["password_file"],"ssh","-o","BatchMode=no",
             "-o","PreferredAuthentications=password,keyboard-interactive","-o","PubkeyAuthentication=no",
             *ssh_options,"root@"+HOST]
    def run(command,data=None,timeout=15):
        remaining=deadline-time.monotonic()
        if remaining<=0: raise TimeoutError("overall ARM slot deadline expired")
        result=subprocess.run(ssh+[command],input=data,capture_output=True,timeout=min(timeout,max(1,remaining)))
        if result.returncode: raise RuntimeError(f"remote command failed {result.returncode}: {result.stderr.decode(errors='replace')}")
        return result.stdout
    # Existing deployment stack supplies receipt-aware attestation and the normal locks.
    from leo.acquisition.authority import CaptureTaskKind,LocalCaptureAuthority,RadioResource
    from pluto_plus import bootstrap_firmware
    from pluto_plus.radio_lock import acquire_radio_lock
    deployment_path=Path(binding["deployment_receipt"])
    deployment=json.loads(deployment_path.read_text()); fit_size=deployment["plan"]["fit_size"]
    authority=LocalCaptureAuthority(Path("/srv/bulk/leo/control"),(RadioResource("radio_pluto_5d4d",SERIAL,"ip:"+HOST),))
    def attest():
        output=run(f"sh -s -- {shlex.quote(SERIAL)} {fit_size}",data=bootstrap_firmware._REMOTE_RECONCILE_SCRIPT,timeout=15).decode()
        fields=bootstrap_firmware._parse_reconciliation_report(output)
        bootstrap_firmware._require_remote_tx_safe(fields,bootstrap_firmware.PAIRED_RX_TX_CAPABLE_LAYOUT)
        expected=deployment["read_only_return_attestation"]
        for key in ("serial","firmware","qspi_bytes","qspi_sha256","fit_sha256"):
            if fields[key] != expected[key]: raise ValueError(f"current ARM {key} differs from deployment receipt")
        return fields
    try:
        with pipeline_lock(),authority.claim(("radio_pluto_5d4d",),task_id="arm-stateless-saved-iq",task_kind=CaptureTaskKind.QUALIFICATION),acquire_radio_lock(SERIAL):
            report["timer_margin"]=timer_margin(args.max_seconds)
            primary=None
            try:
                report["before"]=attest()
                profile_command="uname=$(uname -a); hardware=$(awk -F: '/^Hardware/ {sub(/^ +/,\"\",$2); print $2; exit}' /proc/cpuinfo); model=$(awk -F: '/^model name/ {sub(/^ +/,\"\",$2); print $2; exit}' /proc/cpuinfo); count=$(grep -c '^processor' /proc/cpuinfo); base=/sys/devices/system/cpu/cpufreq/policy0; printf 'uname=%s\\ncpu_hardware=%s\\ncpu_model=%s\\ncpu_count=%s\\nscaling_cur_freq_khz=%s\\nscaling_governor=%s\\n' \"$uname\" \"${hardware:-missing}\" \"${model:-missing}\" \"$count\" \"$(cat $base/scaling_cur_freq 2>/dev/null || printf missing)\" \"$(cat $base/scaling_governor 2>/dev/null || printf missing)\""
                report["system_profile"]=parse_system_profile(run(profile_command,timeout=5).decode())
                remote_names_list=[*remote_names.values(),"SHA256SUMS"]
                with remote_scratch(run,remote_names_list,report) as remote:
                    report["remote_directory"]=remote
                    report["capacity"]=parse_capacity(run("awk '/MemAvailable:/ {print \"memory_available_kib=\" $2}' /proc/meminfo; df -Pk /tmp | awk 'NR==2 {print \"tmp_available_kib=\" $4}'",timeout=5).decode())
                    run("tar -C "+shlex.quote(remote)+" -xf -",archive,timeout=25)
                    checked=run("cd "+shlex.quote(remote)+" && sha256sum -c SHA256SUMS",timeout=10).decode()
                    if checked.count(": OK")!=len(stage): raise ValueError("remote payload verification incomplete")
                    report["remote_hashes_before"]={remote_names[p]:h for p,h in stage.items()}
                    for work_index,(case,method,position) in enumerate(work):
                        remaining=int(work_deadline-time.monotonic())
                        if remaining<2: raise TimeoutError("insufficient slot budget for next process")
                        process_seconds=max(1,min(15,remaining//(len(work)-work_index)))
                        t=manifest["templates"][case["template_key"]]
                        argv=["env","LD_LIBRARY_PATH="+remote,remote+"/"+method,remote+"/"+case["raw_file"],remote+"/"+t["exact"],remote+"/"+t["control"],str(case["rate_hz"]),case["edge"],case["case_id"]]
                        output=run(deadline_shell(argv,process_seconds),timeout=min(process_seconds+2,remaining+2))
                        row=json.loads(output); validate_result(row,case,method)
                        report["rows"].append({"schedule_position":position,
                            "case":{"case_id":case["case_id"],"origin":case["origin"],"split":case["split"],
                                    "rate_hz":case["rate_hz"],"edge":case["edge"]},"result":row})
                        save()
                    checked=run("cd "+shlex.quote(remote)+" && sha256sum -c SHA256SUMS",timeout=10).decode()
                    if checked.count(": OK")!=len(stage): raise ValueError("remote payload changed during execution")
                    report["remote_hashes_after"]={remote_names[p]:h for p,h in stage.items()}
            except BaseException as error:
                primary=error; raise
            finally:
                if "before" in report:
                    try:
                        report["after"]=attest()
                        if report["before"]!=report["after"]: raise ValueError("radio state changed during saved-IQ execution")
                    except BaseException as attestation_error:
                        report["after_attestation_error"]=f"{type(attestation_error).__name__}: {attestation_error}"
                        if primary is None: raise
            for path,expected in protected_local.items():
                if digest_path(path)!=expected: raise ValueError("local source changed during execution")
            report["status"]="complete" if report["plan_complete"] else "bounded_prefix_complete"
    except BaseException as error:
        report.update(status="failed",error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report["local_hashes_after"]={}
        for path in protected_local:
            try: report["local_hashes_after"][str(path)]=digest_path(path)
            except OSError as error: report["local_hashes_after"][str(path)]=f"ERROR:{type(error).__name__}"
        report["local_hashes_unchanged"]=report["local_hashes_after"]==report["local_hashes_before"]
        report["elapsed_seconds"]=time.monotonic()-started; save()
    return 0


if __name__=="__main__": raise SystemExit(main())
