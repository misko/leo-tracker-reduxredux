"""Run one optional exact paired repair on the verified saved 0220 detector input."""

import argparse
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from time import perf_counter, time_ns
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from curved_overcap_repair import ARM_NAMES, CONTROL, HERE, PINS, SOURCE, WorkBudget, audit, checked


CASE = "DS30-0220"
FIELD = Path("/srv/postgres-nvme/leo-ds30-research-worktrees/field-installed-packet-saved/reports/ALGO08/v3")
FIELD_PIN = "2192ba12399da1bb4193a7d8887e84345e920eec93281ed73f60ea403a065441"
HELPER_PIN = "748efc75ca9381129580c106779caddfc3d97f694f0b6c73ed68ba22ccf60c69"
PROTOCOL = HERE / "curved-overcap-repair-0220-protocol.md"
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
THREADS = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS",
           "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    path.chmod(0o400)
    return pin(path)


def pin(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path, digest=None):
    return json.loads(path.read_bytes() if digest is None else checked(path, digest))


def field_worker_import():
    checked(FIELD / "field_installed_packet_saved.py", FIELD_PIN)
    checked(FIELD / "ds30_0049_saved_crossover.py", HELPER_PIN)
    sys.path[:0] = [str(SOURCE), str(SOURCE.parents[2]), str(FIELD), str(FIELD.parents[2])]
    import field_installed_packet_saved as field
    import ds30_0049_saved_crossover as crossover
    if Path(crossover.__file__) != FIELD / "ds30_0049_saved_crossover.py":
        raise ValueError("The saved worker did not bind its archived crossover")
    return field, crossover


def candidate(stage):
    scope = {}
    field, crossover = field_worker_import()
    original = crossover.charted

    def charted(*args, **kwargs):
        import blind_joint_repair as repair

        path = Path(repair.__file__)
        if path != SOURCE / "blind_joint_repair.py":
            raise ValueError("Expected the authenticated, unchanged repair source")
        checked(path, PINS[path])
        budget = WorkBudget(repair.small_rejection)
        with patch.object(repair, "small_rejection", budget.admit):
            result = original(*args, **kwargs)
        scope["additional_attempt"] = budget.over_cap_counts
        return result

    with patch.object(crossover, "charted", charted):
        field.worker(CASE, stage)
    write(stage / "repair-policy.json", scope | dict(raw_timing_credit=0, protocol_sha256=pin(PROTOCOL),
                                                    source_sha256=pin(Path(__file__))))


def run(stage):
    if (os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15
            or any(os.environ.get(k) != "1" for k in THREADS)
            or subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip() != "best-effort: prio 7"):
        raise ValueError("Require the single low-priority shared Gauss benchmark")
    proof = audit()
    with LOCK.open("rb") as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stage.mkdir(mode=0o700)
        audit_pin = write(stage / "prefit-audit.json", proof)
        for name in ("tmp", "fonts"):
            (stage / name).mkdir()
        env = os.environ | dict(TMPDIR=str(stage / "tmp"), MPLCONFIGDIR=str(stage / "fonts"))
        command = [sys.executable, "-IB", str(Path(__file__)), "candidate", str(stage)]
        with (stage / "stdout.log").open("x") as stdout, (stage / "stderr.log").open("x") as stderr:
            before, start, utc = getrusage(RUSAGE_CHILDREN), perf_counter(), time_ns()
            try:
                result = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=100, check=False)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = 124
            wall, finished, after = perf_counter()-start, time_ns(), getrusage(RUSAGE_CHILDREN)
        clock = dict(cpu_s=(after.ru_utime-before.ru_utime)+(after.ru_stime-before.ru_stime),
                     elapsed_s=wall, started_unix_ns=utc, finished_unix_ns=finished, command=command, exit_code=code)
        clock_pin = write(stage / "process.json", clock)
    if code:
        raise ValueError(f"Saved child exited {code}, see {stage / 'stderr.log'}")
    products = ("admission.json", "repair-policy.json", "candidate/crossover-worker.json",
                "candidate/exact-named-raw-witness.json")
    return write(stage / "prediction-seal.json", dict(prefit_sha256=audit_pin, process_sha256=clock_pin,
        protocol_sha256=pin(PROTOCOL), receipt_sha256={name: pin(stage / name) for name in products},
        surveys_in_worker=0))


def score(stage, seal_pin):
    seal = read(stage / "prediction-seal.json", seal_pin)
    if seal["protocol_sha256"] != pin(PROTOCOL) or seal["surveys_in_worker"]:
        raise ValueError("The sealed numerical prediction changed")
    proof = read(stage / "prefit-audit.json", seal["prefit_sha256"])
    clock = read(stage / "process.json", seal["process_sha256"])
    products = {name: read(stage / name, p) for name, p in seal["receipt_sha256"].items()}
    field, _ = field_worker_import()
    import empty_bootstrap as boot

    boot.load_runtime()
    from named_hybrid_baseline import media_and_grid
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km

    _, _, named, authority, _, _ = field.enroll(CASE)
    admission = products["admission.json"]
    worker = products["candidate/crossover-worker.json"]
    witness = products["candidate/exact-named-raw-witness.json"]
    route = witness["ports"]["history_risk"]
    attempt, = route["lean_attempts"]
    policy = products["repair-policy.json"]
    receipt = worker["receipt"]
    if (clock["exit_code"] or worker["waveform_reads"] or worker["verified_handoffs"] != 1
            or admission["raw_authority"] != authority or admission["native_sha256"] != named["native_sha256"]
            or receipt["region"] != named["evidence"]["receipt"]["region"]
            or any(tuple(policy["additional_attempt"][k]) != tuple(v)
                   for k, v in proof["predicate_proof"]["repair_counts"].items())):
        raise ValueError("Saved scientific result differs from the enrolled comparison or over-cap attempt")
    output = stage / "candidate"
    terminal = read(output / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json",
                    receipt["terminal_sha256"])
    figures = media_and_grid(output, receipt, named["native_sha256"], [worker["ordered_owners"]], expected_grid=None)
    result = dict(case=CASE, prediction_seal=seal_pin, decision=receipt["decision"], branch=attempt["decision"],
                  repair=attempt["repair"], fallback=attempt.get("fallback_clocks"),
                  other_veto=attempt.get("reason"), clock=clock, optics=figures["images"], grid=figures["grid"],
                  raw_timing_credit=0, missing_region_qualified=False, advancement=False)
    if receipt["decision"] == "complete":
        ref, = [r["reference"] for r in read(FIELD.parents[2] / "reports/2026_11_21_ds30_full/reference-audit.json",
                                             field.REFERENCE_PIN)["cases"] if r["dataset_label"] == CASE
                and r["authority_eligible"] and r["sealed_metadata_digests_verified"]]
        site = [ref["latitude_deg"], ref["longitude_deg"]]
        old = read(CONTROL / "candidate/crossover-worker.json", PINS[CONTROL / "candidate/crossover-worker.json"])
        arms = {}
        for arm in ARM_NAMES:
            stock, test = named["evidence"]["arms"][arm], terminal["arms"][arm]
            a, b = (1000.*distance_km(row["latlon"], site) for row in (stock, test))
            arms[arm] = dict(ordinary_error_m=a, candidate_error_m=b, change_m=b-a,
                             ordinary_rf_hz=stock["rf_rms_hz"], candidate_rf_hz=test["rf_rms_hz"],
                             owners=owner_delta(old["ordered_owners"][arm], worker["ordered_owners"][arm]))
        satisfies = (result["branch"] == "complete" and result["fallback"] is None
                     and max(row["change_m"] for row in arms.values()) <= 250.
                     and all(clock[k] < proof["current"][k] for k in ("elapsed_s", "cpu_s")))
        result.update(arms=arms, containing_pass=satisfies)
    return write(stage / "score.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("audit", "run", "candidate", "score"))
    parser.add_argument("stage", type=Path)
    parser.add_argument("--seal")
    args = parser.parse_args()
    if args.mode == "audit":
        print(write(args.stage, audit()))
    elif args.mode == "run":
        print(run(args.stage))
    elif args.mode == "candidate":
        candidate(args.stage)
    else:
        print(score(args.stage, args.seal))
