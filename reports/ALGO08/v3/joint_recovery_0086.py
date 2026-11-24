"""Run the frozen 0049 edit classes on one already qualified saved recording."""

import argparse
import json
import sys
from pathlib import Path
from time import monotonic, perf_counter_ns, process_time_ns, time_ns
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import joint_recovery_0049_wait as waiter  # noqa: E402
import matched_donor_0049_trial as trial  # noqa: E402
import signed_cfo_time_readout as signed  # noqa: E402
from field_receiver_solver_cross import exact_charted_policy  # noqa: E402
from sparse8_cfo_epoch_trial import geography  # noqa: E402

CASE = "DS30-0086"
ROOT = Path("/dev/shm/leo-v3-joint-recovery-0086-01")
STAGE = Path("/dev/shm/leo-v3-cfo-epoch-0086-saved01")
ORIGINAL = trial.CAMPAIGN/"cases"/CASE
CHARTED_FULL = Path("/tmp/leo-v3-field-stock-saved-0086-01/candidate")
INSTALLED = (CHARTED_FULL/"fast-scan-automatic-work"
             /"algo08-v2-da6c4cee9d6c1b7868bbe0a677555e0b/detections.json")
PAIR_PIN = "407765fa47754cc99556143888b286e88f4674ab21836d3f437ac8af4c2ca439"
ADMISSION_PIN = "0edbc20d3e2c5ef90a1a324a4f92da72cfe9105c89dc68cba74235815f4aec2b"
RAW_WITNESS_PIN = "5d775bbb9ff01ca9943c8001ed316cd2d65925da8348368452ddd8c0855ae084"
CHART_WITNESS_PIN = "915ddc6e1c49e4725bef885ca418e7aff3e4a938464a4c2a9a1e58e14e3d06a9"
CHART_WORKER_PIN = "36c964fe7e2cf12ed2d322bf85dc52f82f3f67877fbeb929ce35873f63b2bcf5"
EXPERIMENT = SimpleNamespace(
    **(vars(trial.JOINT) | dict(stem="ds30-0086-joint-recovery", transfer_sources=(
        Path(__file__).name, "joint_recovery_0049_wait.py", "field_receiver_solver_cross.py",
    ))),
)


def originals():
    pair = trial.document(ORIGINAL/"pair.json", PAIR_PIN)
    admission = trial.document(STAGE/"admission.json", ADMISSION_PIN)
    authority = trial.document(STAGE/"authority.json", admission["authority_pin"])
    archived, pubs = {}, {}
    if not pair["verified_pair"] or not pair["chronological"] or pair["generation"] != 1:
        raise ValueError("Require the enrolled original pair")
    for role in ("installed", "successor"):
        path = ORIGINAL/role/"attempt-000001"
        pubs[role] = path/"publication"
        raw = trial.document(path/"result.json", pair["attempt_result_sha256"][role])
        if raw["raw_identity"] != authority or raw["process"]["exit_code"] or (
            raw["outcome"] != "complete" or raw["algorithm"] != role
        ):
            raise ValueError("The two originals have different identity or outcome")
        archived[role] = raw
    if archived["successor"]["native_sha256"] != "sha256:"+admission["native_pin"]:
        raise ValueError("Staged sparse source differs from the signed original pair")
    return authority, archived, pubs


def cache(*, detector_packets=False):
    archive = STAGE/"tle"
    files = [path.resolve(strict=True) for path in archive.glob("archive/space-track/*.tle")]
    build = trial.document(trial.BUILD, trial.BUILD_PIN)
    portable = Path(build["native"]["--portable-orbit-index"]["path"]).resolve(strict=True)
    if (len(files) != 50 or not portable.is_relative_to("/dev/shm")
            or any(not body.is_relative_to(archive) for body in files)):
        raise ValueError("Require the staged local 50-body causal view and portable operand")
    trial.require_resident([portable, *files])
    if detector_packets:
        trial.require_resident([INSTALLED, STAGE/"native.json"])
    return dict(tle_files=len(files), portable_sha256=build["native"]["--portable-orbit-index"]["sha256"])


def bound_packets(archived, pubs):
    stock = signed.read_native(pubs["installed"], archived["installed"]["native_sha256"],
                               path=INSTALLED)
    if stock["provenance"]["detector_sha256"] != "sha256:"+signed.FULL:
        raise ValueError("The installed donor recipe differs")
    trial.document(pubs["successor"]/"exact-named-raw-witness.json", RAW_WITNESS_PIN)
    raw = archived["successor"]
    sparse, _, _ = signed.qualified_candidate(
        pubs["successor"], trial.document(pubs["successor"]/"unified-short-bootstrap.json"),
        raw["native_sha256"], raw["raw_identity"]["region_sha256"],
        native_path=STAGE/"native.json",
    )
    return stock, sparse


def prepare(root):
    sys.addaudithook(trial.deny_backing)
    begin, cpu = perf_counter_ns(), process_time_ns()
    authority, archived, pubs = originals()
    residency = cache(detector_packets=True)
    stock, sparse = bound_packets(archived, pubs)
    packet, edits = trial.restore_coverage_and_winner(stock, sparse)
    root.mkdir(mode=0o700)
    filepath = root/"derived-native.json"
    filepath.write_bytes(json.dumps(packet, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                    separators=(",", ":")).encode())
    filepath.chmod(0o400)
    trial.document(filepath, edits["derived_native_sha256"])
    return trial.write(root/"plan.json", dict(
        case=CASE, protocol=trial.protocol(EXPERIMENT), pair_pin=PAIR_PIN, residency=residency,
        worker=trial.identifier(HERE/"matched_donor_0049_trial.py"),
        sources=trial.source_pins(EXPERIMENT), original_archive=authority["archive_sha256"],
        original_offer=authority["region_sha256"], original_native_sha256=signed.canonical(sparse),
        installed_native_sha256=signed.canonical(stock), change=edits, score_reads=0, waveform_reads=0,
        cpu_s=(process_time_ns()-cpu)*1e-9, elapsed_s=(perf_counter_ns()-begin)*1e-9,
    ))


def launch(root, pid, duration, pin):
    plan = trial.document(root/"plan.json", pin)
    if (plan["case"] != CASE or plan["protocol"] != trial.protocol(EXPERIMENT)
            or (root/"child-intent.json").exists() or (root/"wait-receipt.json").exists()):
        raise ValueError("Require the unchanged and unused transfer plan")
    machine = trial.attrs(expected_priority="idle")
    limits = waiter.slot_inputs(pid, duration)
    begin, deadline = time_ns(), monotonic()+duration
    binding = dict(driver=Path(__file__).resolve(), budget=27, flags=[], plan_pin=pin,
                   protocol=plan["protocol"])

    def child(fd, admission):
        return waiter.run_child(root, fd, dict(admission, driver_pid=pid), machine, binding=binding)

    print(f"Waiting at most {duration:g}s for the sole DS30-0086 worker", flush=True)
    outcome, rejected, last = waiter.wait_for_slot(
        deadline=deadline, cached=cache, launch=child, **limits,
    )
    print(trial.write(root/"wait-receipt.json", dict(
        worker=outcome, rejected=dict(rejected), last_sample=last, plan_sha256=pin,
        duration_s=duration, started_unix_ns=begin, finished_unix_ns=time_ns(), driver_pid=pid,
    )), flush=True)


def score(root, pin):
    seal = trial.document(root/"prediction-seal.json", pin)
    plan = trial.document(root/"plan.json", seal["plan_sha256"])
    clock = trial.document(root/"clock.json", seal["clock"])
    run = trial.document(root/"receipt.json", seal["receipt"])
    authority, baseline, pubs = originals()
    output = root/"substituted"
    witness = trial.document(output/"exact-named-raw-witness.json", run["witness"])
    receipt, earned = run["receipt"], witness["evidence"]
    native = plan["change"]["derived_native_sha256"]
    if (clock["exit_code"] or run["handoffs"] != 1 or run["waveform_reads"] or
            receipt["window_count"] != authority["window_count"] or
            receipt["counts"] != baseline["successor"]["evidence"]["receipt"]["counts"] or
            receipt["region"] != baseline["successor"]["evidence"]["receipt"]["region"] or
            seal["protocol"] != trial.protocol(EXPERIMENT) or run["input"] != native):
        raise ValueError("The transfer lost its original scan, offer, or pinned handoff")

    trial.start_runtime().load_runtime()
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import owner_delta
    from raw_0016_best_score import position_sides
    from tools.pipeline_eval.scoring import distance_km

    terminal = trial.document(
        output/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json",
        receipt["terminal_sha256"],
    )
    full = trial.document(CHARTED_FULL/"exact-named-raw-witness.json", CHART_WITNESS_PIN)
    mixed = trial.document(pubs["successor"]/"exact-named-raw-witness.json", RAW_WITNESS_PIN)
    full_worker = trial.document(CHARTED_FULL/"crossover-worker.json", CHART_WORKER_PIN)
    exact_charted_policy(full, mixed)
    exact_charted_policy(mixed, witness)
    if (terminal["native_sha256"] != native or set(terminal["arms"]) != set(trial.ARMS)
            or full["evidence"]["detail"]["input_sha256"] != plan["installed_native_sha256"]
            or full_worker["verified_handoffs"] != 1 or full_worker["waveform_reads"]):
        raise ValueError("Wrong native staging or charted control")
    result = dict(case=CASE, decision=receipt["decision"], clock=clock, prediction_sha256=pin,
                  control_status={key: value["outcome"] for key,value in baseline.items()})
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(output)
        media = artifacts(output, receipt)
        grid = store.position_grid(receipt["run_id"])
        position = position_sides(store, receipt, media)
        if (terminal["decision"] != "ok" or len(media["images"]) != 8
                or grid["evaluated_points"] != 179
                or any(abs(v)>1e-5 for v in grid["endpoint_objective_replay"].values())
                or json.dumps(media["images"], sort_keys=True) !=
                    json.dumps(earned["images"], sort_keys=True)):
            raise ValueError("Missing verified scientific artifacts")
        fixed_full = trial.document(
            CHARTED_FULL/"fast-scan-automatic-work"/full_worker["receipt"]["run_id"]/"terminal.json",
            full_worker["receipt"]["terminal_sha256"],
        )
        site = geography(CASE)
        arms = {}
        for arm in trial.ARMS:
            rows = earned["owner_rows"][arm]
            if canonical_digest({oid:j for oid,j,_ in rows}) != earned["detail"]["arms"][arm]["owner_sha256"]:
                raise ValueError("Owner readout differs from the published arms")
            comparators = {key: item["evidence"]["arms"][arm] for key,item in baseline.items()}
            targets = dict(comparators, charted_full=fixed_full["arms"][arm], joint=terminal["arms"][arm])
            errors = {key: 1e3*distance_km(site, value["latlon"]) for key,value in targets.items()}
            arms[arm] = dict(
                endpoints=targets, error_m=errors,
                joint_minus_mixed_m=errors["joint"]-errors["successor"],
                joint_minus_installed_m=errors["joint"]-errors["installed"],
                joint_minus_charted_full_m=errors["joint"]-errors["charted_full"],
                owner_delta_sparse=owner_delta(mixed["evidence"]["owner_rows"][arm], rows),
                owner_delta_charted_full=owner_delta(full["evidence"]["owner_rows"][arm], rows),
                all_owned_rf_hz={key: page["evidence"]["detail"]["arms"][arm]["residual_rms_hz"]
                                 for key,page in (("joint",witness),("successor",mixed),
                                                  ("charted_full",full))},
            )
        result.update(arms=arms, position=position, images=media["images"],
                      grid_replay=grid["endpoint_objective_replay"], native_sha256=native)
    elif (receipt["decision"] != "withheld" or any(arm["latlon"] is not None
            for arm in terminal["arms"].values()) or earned["images"] or list(output.rglob("*.png"))):
        raise ValueError("Invalid saved disposition")
    print(trial.write(root/"score.json",result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare","smoke","wait","worker","score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin")
    parser.add_argument("--lease-fd", type=int)
    parser.add_argument("--driver-pid", type=int, default=2213879)
    parser.add_argument("--wait-s", type=float, default=720)
    args = parser.parse_args()
    if args.root != ROOT or (args.action != "prepare" and not args.pin):
        parser.error("Require the registered transfer root and action's seal")
    if args.action=="prepare":
        print(prepare(args.root))
    elif args.action in ("smoke","worker"):
        trial.worker(args.root, args.pin, EXPERIMENT, smoke=args.action=="smoke",
                     lease_fd=args.lease_fd, enrollment=(CASE,STAGE,ADMISSION_PIN,50))
    elif args.action=="wait":
        launch(args.root, args.driver_pid, args.wait_s, args.pin)
    else:
        score(args.root,args.pin)
