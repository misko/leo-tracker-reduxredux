"""Recover DS30 path migrations when the frozen sequential campaign encounters them."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parents[2]
sys.path[:0] = [str(HERE), str(WORKTREE)]

import ds30_paired_evaluation as study
from ds30_paired_inputs import ARMS, checked, digest, encode, publish, read, write
from ds30_relocated_original import CASES, PLAN_PIN, admitted_proof, measured_pair, plan_document
from ds30_relocation_ledger import attach, combine, overlay, retained_attempts

ROOT = study.OUTPUT
RECOVERY = ROOT / "relocation"
STATE = RECOVERY / "coordinator"
ORDINARY = "leo-ds30-paired-evaluation-20261124.service"
FIRST_OWNER = "leo-ds30-relocated-0452-retry-20261124.service"
FIRST = "DS30-0452"
TEMPORARY = 75
RESUME = 42
PATH_ERROR = "ValueError: The actual source is outside the enrolled original recording"
ORDINARY_DRIVER = Path("/tmp/leo-v3-ds30-paired-evaluation/reports/ALGO08/v3/ds30_paired_evaluation.py")
ORDINARY_ARGV = [str(study.PYTHON), "-BP", str(ORDINARY_DRIVER), "run", "--target", "455", "--max-pairs", "455", "--watch"]
SERVICE_KEYS = ("LoadState", "ActiveState", "SubState", "InvocationID", "MainPID", "ExecMainStatus",
                "Result", "ExecStart", "User", "CPUAffinity", "Nice", "IOSchedulingClass")


def service(unit):
    result = subprocess.check_output(["/usr/bin/systemctl", "show", unit, *["--property=" + k for k in SERVICE_KEYS]],
                                     text=True, timeout=10)
    return dict(line.split("=", 1) for line in result.splitlines())


def literal_service(observed):
    match = re.search(r"argv\[\]=([^;]+);", observed["ExecStart"])
    return (observed["LoadState"] == "loaded" and observed["User"] == "leo" and observed["CPUAffinity"] == "2"
            and int(observed["Nice"]) >= 15 and observed["IOSchedulingClass"] == "3"
            and match is not None and match.group(1).strip() == " ".join(ORDINARY_ARGV))


def absent_service(observed):
    return observed["LoadState"] == "not-found" and observed["ActiveState"] == "inactive" and not observed.get("InvocationID")


def exact_halt(observed, records):
    """Accept only the original driver's known stage guard from this invocation."""
    identity = observed["InvocationID"]
    if (observed["ActiveState"], observed["Result"], observed["ExecMainStatus"], observed["MainPID"]) != (
            "failed", "exit-code", "1", "0") or not re.fullmatch(r"[a-f0-9]{32}", identity):
        return None
    messages = [entry["MESSAGE"] for entry in records if entry.get("_SYSTEMD_UNIT") == ORDINARY
                and entry.get("_SYSTEMD_INVOCATION_ID") == identity and isinstance(entry.get("MESSAGE"), str)]
    trace = any(f'File "{ORDINARY_DRIVER}",' in line and "in_scope" in line for line in messages)
    failures = [re.fullmatch(r"ValueError: Review repeated operational failures before scaling beyond (8|30|100) cases", line)
                for line in messages]
    matches = [item for item in failures if item]
    if not trace or len(matches) != 1:
        return None
    return int(matches[0].group(1))


def snapshot():
    ordinary, owner = service(ORDINARY), service(FIRST_OWNER)
    if not literal_service(ordinary) and not absent_service(ordinary):
        raise ValueError("Ordinary service is absent or its approved command changed")
    lines = []
    if ordinary["ActiveState"] == "failed" and re.fullmatch(r"[a-f0-9]{32}", ordinary["InvocationID"]):
        lines = subprocess.check_output(
            ["/usr/bin/sudo", "-n", "/usr/bin/journalctl", "--no-pager", "-n", "64", "-o", "json",
             "_SYSTEMD_UNIT=" + ORDINARY, "_SYSTEMD_INVOCATION_ID=" + ordinary["InvocationID"]],
            text=True, timeout=15).splitlines()
    return dict(ordinary=ordinary, owner=owner,
                halted_at=exact_halt(ordinary, [json.loads(line) for line in lines]))


def rejection(path):
    return study.summary(path) == {"state": "invalid_original_input", "verified_pair": False, "reason": PATH_ERROR}


def overlay_path(case):
    return RECOVERY / case / "overlay.json"


def sidecar(case):
    return RECOVERY / case


def original(case):
    return ROOT / "cases" / case


def pending_arm(root, active_rows):
    for row in active_rows:
        folder = root / "cases" / row["case"]
        if not study.summary(folder) and any(
                any((folder / arm).glob("attempt-*/launch.json")) for arm in ARMS):
            return row["case"]
    return None


def eligible(rows):
    """The resume gate uses only the planned encounter and exact old rejection."""
    result = []
    for row in rows:
        case = row["case"]
        if case in CASES and case != FIRST and rejection(original(case)) and not overlay_path(case).is_file():
            result.append(case)
    return result


def resume_intent(number, invocation, ordered):
    """Capture the pre-import cause for the exact failed ordinary invocation."""
    path = STATE / ("resume-" + invocation + ".json")
    group = [row["case"] for row in ordered[:number]]
    if path.is_file():
        retained = read(path)
        if (retained["stage"] != number or retained["cases"] != group or retained["invocation"] != invocation
                or retained["plan_sha256"] != PLAN_PIN):
            raise ValueError("The recorded stop no longer corresponds to the held ordinary invocation")
        return retained
    proofs = {}
    for case in group:
        directory = original(case)
        disposition = study.summary(directory)
        if disposition.get("verified_pair"):
            continue
        if case not in CASES or not rejection(directory) or any((directory / arm).exists() for arm in ARMS):
            raise ValueError(f"Stage contains an unresolved non-migration or paid failure: {case}")
        proofs[case] = digest((directory / "pair.json").read_bytes())
    if len(proofs) < 2:
        raise ValueError("The stopped stage cannot be attributed to two exact migration rejections")
    intent = dict(stage=number, invocation=invocation, cases=group, rejections=proofs, plan_sha256=PLAN_PIN)
    write(path, intent)
    return intent


def check_resume(intent):
    for case in intent["cases"]:
        if not study.summary(original(case)).get("verified_pair"):
            raise ValueError(f"An ordinary input is still unresolved after the relocation import: {case}")
        if case in intent["rejections"]:
            checked(original(case) / "original-preflight.json", intent["rejections"][case])
            bundle = read(original(case) / "relocation-overlay.json")
            if bundle != read(overlay_path(case)) or bundle["original_preflight_sha256"] != intent["rejections"][case]:
                raise ValueError("The import does not preserve the rejection that caused the actual stop")


def status(state, **values):
    document = dict(state=state, plan_sha256=PLAN_PIN, **values)
    publish(STATE / "status.json", encode(document) + b"\n", replace=True)
    return document


def on_hold(reason, **values):
    return TEMPORARY, status(reason, **values)


def recover_one(case):
    proof = RECOVERY / f"{case}-approved-proof.json"
    if not proof.exists():
        if admitted_proof(case, proof) == TEMPORARY:
            return on_hold("metadata_waiting_for_quiet_storage", case=case)
    pin = digest(proof.read_bytes())
    body = read(proof)
    if body["case"] != case or body["plan_sha256"] != PLAN_PIN:
        raise ValueError("Stored metadata proof has the wrong original authority")
    output = sidecar(case)
    retained_attempts(output)
    if not study.summary(output):
        quiet, _ = study.quiet_window()
        if not quiet:
            return on_hold("raw_waiting_for_quiet_storage", case=case, proof_sha256=pin)
        status("recovering", case=case, proof_sha256=pin)
        try:
            result = measured_pair(proof, pin, output)
        except BlockingIOError:
            return on_hold("raw_waiting_for_gauss_lease", case=case, proof_sha256=pin)
        if result == TEMPORARY:
            return on_hold("raw_waiting_for_quiet_storage", case=case, proof_sha256=pin)
    seal = overlay(proof, pin)
    combine()
    return on_hold("overlay_verified", case=case, proof_sha256=seal["proof_sha256"])


def verify_first_owner():
    path = overlay_path(FIRST)
    if not path.is_file():
        raise ValueError("The independent 0452 owner stopped without a verified overlay")
    witness = STATE / "first-owner-handoff.json"
    sha = digest(path.read_bytes())
    if witness.is_file():
        if read(witness)["overlay_sha256"] != sha:
            raise ValueError("The independent owner's verified overlay changed")
        return
    report = read(path)
    if report != overlay(ROOT / report["proof_path"], report["proof_sha256"]):
        raise ValueError("The independent owner had no valid measured handoff")
    write(witness, {"overlay_sha256": sha, "proof_sha256": report["proof_sha256"]})


def step(observed, *, dry=False):
    plan = plan_document()
    ordered = study.stage_cases(plan)
    if not literal_service(observed["ordinary"]) and not absent_service(observed["ordinary"]):
        raise ValueError("The ordinary invocation no longer matches the approved command")
    state, stage = observed["ordinary"]["ActiveState"], observed["halted_at"]
    if dry:
        return 0, dict(plan_sha256=PLAN_PIN, ordinary=state, halted_at=stage,
                       existing_0452_owner=observed["owner"]["ActiveState"], pending_ordinary_arm=pending_arm(ROOT, ordered),
                       eligible=eligible(ordered), overlays=[case for case in CASES if overlay_path(case).is_file()])
    intent = None
    if state == "failed":
        if not stage:
            raise ValueError("Unknown ordinary stop; no automatic restart or new relocated acquisition")
        intent = resume_intent(stage, observed["ordinary"]["InvocationID"], ordered)
    elif state == "inactive":
        if ((not absent_service(observed["ordinary"]) and observed["ordinary"]["Result"] != "success")
                or not all(study.summary(original(r["case"])) for r in ordered)):
            raise ValueError("Ordinary service stopped outside a completed campaign")
    elif state != "active":
        return on_hold("ordinary_service_transition")
    if observed["owner"]["ActiveState"] in ("active", "activating", "deactivating", "reloading"):
        return on_hold("existing_0452_owner", case=FIRST)
    verify_first_owner()
    partial = pending_arm(ROOT, ordered)
    if partial:
        return on_hold("ordinary_pair_in_progress", case=partial)
    if state != "active":
        for case in CASES:
            if overlay_path(case).is_file() and rejection(original(case)):
                try:
                    attach(case)
                except BlockingIOError:
                    return on_hold("ordinary_driver_lock_busy")
    unresolved = eligible(ordered)
    if intent is not None:
        repairs = set(intent["rejections"])
        unresolved = [case for case in unresolved if case in repairs]
        if not unresolved:
            check_resume(intent)
            combine()
            return RESUME, status("restart_proven_stage", stage=stage, invocation=intent["invocation"],
                                  attached=sorted(repairs))
    if unresolved:
        return recover_one(unresolved[0])
    if state == "inactive":
        if any(not overlay_path(case).is_file() for case in CASES):
            raise ValueError("A frozen migrated original has no verified overlay")
        combine()
        return 0, status("all_migrations_attached")
    return on_hold("waiting_for_frozen_encounter")


def run_as_leo(observed, mode):
    threads = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
    command = ["/usr/bin/sudo", "-n", "-u", "leo", "/usr/bin/env", "PYTHONDONTWRITEBYTECODE=1",
               f"PYTHONPATH={WORKTREE / 'src'}:{WORKTREE}", *(v + "=1" for v in threads),
               str(study.PYTHON), "-BP", str(Path(__file__).resolve()), mode]
    return subprocess.run(command, input=encode(observed), stdout=subprocess.PIPE, check=False)


def supervise(dry=False):
    observed = snapshot()
    worker = run_as_leo(observed, "inspect" if dry else "step")
    if worker.stdout:
        sys.stdout.buffer.write(worker.stdout)
        sys.stdout.buffer.flush()
    if worker.returncode != RESUME:
        return worker.returncode
    request = json.loads(worker.stdout)
    latest = snapshot()
    if (dry or request["state"] != "restart_proven_stage" or request["plan_sha256"] != PLAN_PIN
            or request["stage"] != observed["halted_at"] or request["stage"] != latest["halted_at"]
            or request["invocation"] != observed["ordinary"]["InvocationID"]
            or request["invocation"] != latest["ordinary"]["InvocationID"]
            or len(request["attached"]) < 2 or not set(request["attached"]) <= set(CASES)):
        raise ValueError("Restart request no longer corresponds to the exact failed invocation")
    # A concurrent human start can succeed first. 'start' never stops a running arm.
    subprocess.run(["/usr/bin/sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", ORDINARY], check=True)
    return TEMPORARY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("supervise", "dry", "step", "inspect"))
    args = parser.parse_args()
    if args.action in ("supervise", "dry"):
        return supervise(dry=args.action == "dry")
    observed = json.load(sys.stdin)
    if args.action == "inspect":
        code, result = step(observed, dry=True)
    else:
        if set(os.sched_getaffinity(0)) != {2} or os.getpriority(os.PRIO_PROCESS, 0) < 15:
            raise ValueError("Expected the low-priority one-CPU coordinator")
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            with study.exclusive(STATE / "coordinator.lock", "a+b"):
                try:
                    code, result = step(observed)
                except (KeyError, OSError, TypeError, ValueError) as error:
                    code, result = 1, status("manual_review", reason=f"{type(error).__name__}: {error}")
        except BlockingIOError:
            code, result = TEMPORARY, {"state": "coordinator_lock_busy"}
    print(json.dumps(result, sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
