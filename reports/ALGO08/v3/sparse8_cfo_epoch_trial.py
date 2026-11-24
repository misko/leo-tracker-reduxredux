"""Time and seal the saved CFO epoch comparison, then score its sealed outputs."""

import argparse
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from time import perf_counter_ns, time_ns

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sparse8_cfo_epoch_saved import CASE, HERE, MODES, NATIVE, PROTOCOL


LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
PAIR = "5a5307be75290e5bed14cb42380e47cd9679030a327fdcce2fa1fd2f3c910719"
REFERENCES = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
ARMS = ("c0", "fitted_c")
THREADS = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS",
           "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def identifier(path):
    return sha256(path.read_bytes()).hexdigest()


def document(path, pin=None):
    body = path.read_bytes()
    if pin is not None and sha256(body).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Digest changed for {path.name}")
    return json.loads(body)


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")
    path.chmod(0o400)
    return identifier(path)


def attrs():
    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15:
        raise ValueError("Expected CPU2 and nice 15 on the shared host")
    priority = subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip()
    if priority != "best-effort: prio 7" or any(os.environ.get(key) != "1" for key in THREADS):
        raise ValueError(f"Expected low IO priority and single numerical thread, got {priority}")
    return dict(cpu=2, nice=15, ionice=priority, threads={key: 1 for key in THREADS})


def launch(stage, mode, admission=None):
    config = attrs()
    worker = HERE / "sparse8_cfo_epoch_saved.py"
    with LOCK.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        scratch = stage / f"{mode}-scratch"
        scratch.mkdir()
        environment = os.environ | dict(
            TMPDIR=str(scratch), MPLCONFIGDIR=str(scratch), XDG_CACHE_HOME=str(scratch))
        result = stage / f"{mode}-receipt.json"
        command = [sys.executable, "-IB", str(worker), mode, str(stage)]
        if admission is not None:
            command.extend(("--admission", admission))
        with (stage / f"{mode}.stdout").open("x") as out, (stage / f"{mode}.stderr").open("x") as err:
            usage0 = getrusage(RUSAGE_CHILDREN)
            unix, start = time_ns(), perf_counter_ns()
            try:
                completed = subprocess.run(command, stdout=out, stderr=err, check=False, timeout=120,
                                           env=environment, stdin=subprocess.DEVNULL)
                exit_code = completed.returncode
            except subprocess.TimeoutExpired:
                exit_code = 124
            elapsed = (perf_counter_ns()-start)*1e-9
            finished = time_ns()
            usage1 = getrusage(RUSAGE_CHILDREN)
        clock = dict(started_unix_ns=unix, finished_unix_ns=finished, elapsed_s=elapsed, exit_code=exit_code,
                     cpu_s=usage1.ru_utime-usage0.ru_utime+usage1.ru_stime-usage0.ru_stime,
                     major_faults=usage1.ru_majflt-usage0.ru_majflt, command=command,
                     input_blocks=usage1.ru_inblock-usage0.ru_inblock)
        clock_pin = write(stage / f"{mode}-clock.json", clock)
        if exit_code:
            raise RuntimeError(f"{mode} exited {exit_code}. See {stage / (mode+'.stderr')}")
        result.chmod(0o400)
        products = dict(clock_sha256=clock_pin, receipt_sha256=identifier(result))
    return products, config


def run(stage, requested_mode, *, admission=None, case=CASE, protocol=PROTOCOL):
    if requested_mode == "centroid":
        control = ordinary_receipt(stage)
        if document(stage / "ordinary-clock.json")["exit_code"] and not document(control).get("recovered"):
            raise ValueError("The ordinary saved publication must complete first")
    products, config = launch(stage, requested_mode, admission)
    stages = {requested_mode: products}
    if requested_mode == "ordinary":
        print(stages[requested_mode]["receipt_sha256"], flush=True)
        return
    control = ordinary_receipt(stage)
    stages["ordinary"] = dict(clock_sha256=identifier(stage / "ordinary-clock.json"), receipt_file=control.name,
                              receipt_sha256=identifier(control))
    seal = write(stage / "prediction-seal.json", dict(
        case=case, protocol_sha256=identifier(protocol), driver_sha256=identifier(Path(__file__)),
        stage_order=MODES, score_reads=0, acquisition="verified saved packet", host=config, products=stages,
        admission_sha256=admission))
    print(seal, flush=True)


def ordinary_receipt(stage):
    recovered = stage / "ordinary-recovered.json"
    return recovered if recovered.is_file() else stage / "ordinary-receipt.json"


def recover_ordinary(stage):
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.contracts.digests import canonical_digest

    clock = document(stage / "ordinary-clock.json")
    stderr = (stage / "ordinary.stderr").read_text()
    if clock["exit_code"] != 1 or not stderr.rstrip().endswith("Object of type ndarray is not JSON serializable"):
        raise ValueError("Unexpected ordinary worker failure")
    witness_path = stage / "ordinary" / "exact-named-raw-witness.json"
    witness = document(witness_path)
    evidence = witness["evidence"]
    detail = evidence["detail"]
    terminal = dict(run_id=detail["run_id"], terminal_sha256=detail["terminal_sha256"], decision=detail["state"])
    published = document(stage / "ordinary/fast-scan-automatic-work" / terminal["run_id"] / "terminal.json",
                         terminal["terminal_sha256"])
    (published_native,) = (stage / "ordinary").glob("fast-scan-automatic-work/*/detections.json")
    native = document(published_native, NATIVE)
    if (terminal["decision"] != "complete" or len(evidence["images"]) != 8 or
            detail["input_sha256"] != "sha256:"+NATIVE or published["native_sha256"] != detail["input_sha256"]):
        raise ValueError("The ordinary signed products did not complete before provenance serialization")
    rows, _ = winning_observations(native)
    partial = stage / "ordinary-receipt.json"
    if not partial.read_text().startswith('{"acquisition_handoffs":1,'):
        raise ValueError("The emitted boundary evidence is missing")
    result = dict(case=CASE, mode="ordinary", terminal=terminal, waveform_reads=0, acquisition_handoffs=1,
                  graph_time=dict(graph_input_digests=[canonical_digest(rows)], recomputed_from_signed_native=True),
                  evidence=dict(evidence=evidence), recovered=True, witness_sha256=identifier(witness_path),
                  partial_receipt_sha256=identifier(partial), failure_sha256=identifier(stage / "ordinary.stderr"))
    print(write(stage / "ordinary-recovered.json", result))


def geography(case=CASE):
    root = HERE.parents[2]
    body = subprocess.check_output([
        "git", "-c", f"safe.directory={root}", "-C", str(root), "show",
        "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    if sha256(body).hexdigest() != REFERENCES:
        raise ValueError("The reviewed survey audit differs")
    row, = (row for row in json.loads(body)["cases"] if row["dataset_label"] == case
            and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    return [row["reference"][name] for name in ("latitude_deg", "longitude_deg")]


def score(stage, seal_sha, *, case=CASE, protocol=PROTOCOL, native_pin=NATIVE, pair_pin=PAIR, require_grid_parity=False):
    from tools.pipeline_eval.scoring import distance_km
    from prospective_0316_solver import owner_delta

    seal = document(stage / "prediction-seal.json", seal_sha)
    if (seal["case"] != case or seal["score_reads"] != 0 or seal["protocol_sha256"] != identifier(protocol)
            or seal["stage_order"] != list(MODES) or set(seal["products"]) != set(MODES)):
        raise ValueError("Expected both frozen predictions before survey scoring")
    stages = {}
    for mode in MODES:
        hashes = seal["products"][mode]
        receipt_path = stage / hashes.get("receipt_file", f"{mode}-receipt.json")
        receipt = document(receipt_path, hashes["receipt_sha256"])
        clock = document(stage / f"{mode}-clock.json", hashes["clock_sha256"])
        result = receipt["terminal"]
        terminal = document(stage / mode / "fast-scan-automatic-work" / result["run_id"] / "terminal.json",
                            result["terminal_sha256"])
        if (terminal["native_sha256"] != "sha256:"+native_pin or receipt["acquisition_handoffs"] != 1
                or receipt["waveform_reads"] or (clock["exit_code"] and not receipt.get("recovered"))
                or set(terminal["arms"]) != set(ARMS)):
            raise ValueError("Prediction does not bind to the saved-graph comparison")
        evidence = receipt["evidence"]["evidence"]
        witness = document(stage / mode / "exact-named-raw-witness.json", receipt["witness_sha256"])
        stages[mode] = dict(terminal=terminal, saved_receipt=receipt, evidence=evidence, clock=clock,
                            route=witness["solver_recipe"]["history_risk"])
    home = CAMPAIGN / "cases" / case
    pair = document(home / "pair.json", pair_pin)
    archive = home / "successor" / f"attempt-{pair['generation']:06d}"
    published = document(archive / "result.json", pair["attempt_result_sha256"]["successor"])
    result = published["evidence"]["receipt"]
    archived_terminal = document(archive / "publication/fast-scan-automatic-work" / result["run_id"] / "terminal.json",
                                 result["terminal_sha256"])
    ordinary, corrected = (stages[tag] for tag in MODES)
    reproduction = dict(
        terminal=ordinary["terminal"] == archived_terminal,
        owners=ordinary["evidence"]["owner_maps"] == published["evidence"]["owners"],
        arms=ordinary["terminal"]["arms"] == archived_terminal["arms"],
        graph_digest_changed=ordinary["saved_receipt"]["graph_time"]["graph_input_digests"]
        != corrected["saved_receipt"]["graph_time"]["graph_input_digests"])
    if require_grid_parity:
        archived_witness = document(archive / "publication/exact-named-raw-witness.json")
        a, b = archived_witness["evidence"], ordinary["evidence"]
        reproduction.update(images=a["images"] == b["images"], ordered_owners=a["owner_rows"] == b["owner_rows"],
                            path=a["sidecars"]["path"] == b["sidecars"]["path"],
                            scientific_grid=scientific_grid(stage / "ordinary") == scientific_grid(archive / "publication"))
    if not all(reproduction.values()):
        raise ValueError(f"Archived ordinary scientific evidence differs: {reproduction}")
    stop = corrected["saved_receipt"]["terminal"]["decision"] != "complete"
    result = dict(case=case, seal_sha256=seal_sha, archived_reproduction=reproduction, stop=stop)
    if not stop:
        reference = geography(case)
        deltas, outcomes = {}, {}
        for mode, state in stages.items():
            evidence = state["evidence"]
            if len(evidence["images"]) != 8 or not evidence["grid"]:
                raise ValueError("Expected complete figures and position grid")
            outcomes[mode] = dict(clock=state["clock"], figures=evidence["images"], grid=evidence["grid"], route=state["route"],
                                  owner_maps=evidence["owner_maps"], arms={
                                      arm: dict(position=arm_state["latlon"], rf_rms_hz=arm_state["rf_rms_hz"],
                                                error_m=1e3*distance_km(arm_state["latlon"], reference))
                                      for arm, arm_state in state["terminal"]["arms"].items()})
        a, b = (outcomes[mode]["arms"] for mode in MODES)
        for arm in ARMS:
            deltas[arm] = dict(error_m=b[arm]["error_m"]-a[arm]["error_m"],
                               rf_rms_hz=b[arm]["rf_rms_hz"]-a[arm]["rf_rms_hz"],
                               endpoint_shift_m=1e3*distance_km(a[arm]["position"], b[arm]["position"]),
                               owners=owner_delta(ordinary["evidence"]["owner_rows"][arm],
                                                  corrected["evidence"]["owner_rows"][arm]))
        result.update(outcomes=outcomes, change=deltas, reference_sha256=REFERENCES,
                      stop=any(row["error_m"] > 250. for row in deltas.values()),
                      correction=corrected["saved_receipt"]["graph_time"])
    print(write(stage / "score.json", result))


def scientific_grid(root):
    (path,) = root.glob("fast-scan-standard-v2/*/*/position-grid.json")
    return {key: value for key, value in document(path)["document"].items() if key != "elapsed_seconds"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--score", metavar="PREDICTION_SEAL_SHA256")
    action.add_argument("--run", choices=MODES)
    action.add_argument("--recover-ordinary", action="store_true")
    args = parser.parse_args()
    if args.score:
        score(args.stage, args.score)
    elif args.recover_ordinary:
        recover_ordinary(args.stage)
    else:
        run(args.stage, args.run)
