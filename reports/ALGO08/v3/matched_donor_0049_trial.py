"""Measure a sealed nonanchor intervention using the exact original 0049 saved route."""

import argparse
import fcntl
import gzip
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from shutil import copyfile
import subprocess
import sys
from time import perf_counter_ns, process_time_ns, time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

from sparse8_cfo_epoch_challenge import ADMISSION, CASE, CROSSOVER, PAIR, PARITY, ordinary
from sparse8_cfo_epoch_saved import BUILD, BUILD_PIN, CHARTED, deny_backing
from sparse8_cfo_epoch_trial import ARMS, CAMPAIGN, LOCK, attrs, document, identifier, write
from matched_donor_0049 import derive, owner_counts
from sparse_only_drop_0049 import exclude_sparse_only
from empty_recovery_0049 import restore_empty_lanes
import signed_cfo_time_readout as authority


STAGE = Path("/dev/shm/leo-v3-cfo-epoch-0049-saved01")
DONOR = SimpleNamespace(stem="ds30-0049-matched-donor", derive=derive,
                        ledger="donations", ledger_digest="donation_sha256", label="donated",
                        option=None, source=None, priority="best-effort: prio 7")
EXCLUSION = SimpleNamespace(stem="ds30-0049-sparse-only-drop", derive=exclude_sparse_only,
                            ledger="removed", ledger_digest="exclusion_sha256", label="removed",
                            option="--exclude-sparse-only", source="sparse_only_drop_0049.py", priority=DONOR.priority)
RESTORATION = SimpleNamespace(stem="ds30-0049-empty-recovery", derive=restore_empty_lanes,
                              ledger="inserted", ledger_digest="insertion_sha256", label="inserted",
                              option="--restore-empty-lanes", source="empty_recovery_0049.py", priority="idle")

PREVIOUS = {
    DONOR.stem: "9e129a016bdd533d7c82706b402665bea6cd2d34c0628c0bda62fe414cae1a6a",
    EXCLUSION.stem: "dcbc89c91c03b302343057f982207a90684c956e8d2d12e3d198119ebf1836bb",
}


def protocol(experiment):
    return identifier(HERE/f"{experiment.stem}-protocol.md")


def source_pins(experiment):
    names = ["matched_donor_0049.py", "signed_cfo_time_readout.py", "sparse8_cfo_epoch_trial.py"]
    if experiment.source:
        names.append(experiment.source)
    return {name: identifier(HERE/name) for name in names}


def prepare(root, experiment):
    if root.exists() or root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Use a fresh private output in local tmpfs")
    sys.addaudithook(deny_backing)
    started = perf_counter_ns(), process_time_ns()
    previous = ordinary(STAGE)
    sparse, _, offer = authority.candidate(CASE)
    pair = document(CAMPAIGN/"cases"/CASE/"pair.json", PAIR)
    group = CAMPAIGN/"cases"/CASE/"installed"/f"attempt-{pair['generation']:06d}"
    stock_result = document(group/"result.json", pair["attempt_result_sha256"]["installed"])
    stock = authority.read_native(group/"publication", stock_result["native_sha256"])
    if (authority.canonical(sparse) != previous["terminal"]["native_sha256"]
            or stock_result["raw_identity"]["region_sha256"].removeprefix("sha256:") != offer.removeprefix("sha256:")
            or stock["provenance"]["detector_sha256"] != "sha256:"+authority.FULL):
        raise ValueError("Require the exact authentic sparse/installed pair and identical original offer")
    derived, change = experiment.derive(stock, sparse)
    if experiment is EXCLUSION:
        measured = {key: (value["opportunities"], value["removed"], value["original_winners"])
                    for key, value in change["coverage"].items()}
        if measured != {"rx0/short": (811, 78, 374), "rx1/short": (811, 83, 143),
                        "rx0/anchor": (121, 0, 56), "rx1/anchor": (121, 0, 27)}:
            raise ValueError("Sparse-only enrolment differs from the freeze")
    if experiment is RESTORATION:
        measured = {key: (value["opportunities"], value["original_empty"], value["inserted"])
                    for key, value in change["coverage"].items()}
        if (measured != {"rx0/short": (811, 437, 30), "rx1/short": (811, 668, 74),
                         "rx0/anchor": (121, 65, 0), "rx1/anchor": (121, 94, 0)}
                or change["original_winners"] != 600):
            raise ValueError("Empty-lane enrolment differs from the freeze")
    root.mkdir(mode=0o700)
    payload = root/"derived-native.json"
    payload.write_bytes(json.dumps(derived, sort_keys=True, ensure_ascii=False, allow_nan=False,
                                   separators=(",", ":")).encode())
    payload.chmod(0o400)
    if "sha256:"+identifier(payload) != change["derived_native_sha256"]:
        raise ValueError("The sealed counterfactual differs from its canonical identity")
    print(write(root/"plan.json", dict(case=CASE, protocol=protocol(experiment), worker=identifier(Path(__file__)),
          sources=source_pins(experiment), archived_parity=previous["parity"],
          original_native_sha256=previous["terminal"]["native_sha256"], installed_native_sha256=stock_result["native_sha256"],
          original_archive=stock_result["raw_identity"]["archive_sha256"],
          original_saved_clock=previous["timed_saved_clock"], original_terminal=previous["witness"]["evidence"]["detail"]["terminal_sha256"],
          change=change, cpu_s=(process_time_ns()-started[1])/1e9, elapsed_s=(perf_counter_ns()-started[0])/1e9,
          score_reads=0, waveform_reads=0)))


def start_runtime():
    sys.addaudithook(deny_backing)
    sys.path[:0] = [str(CHARTED/"reports/ALGO08/v3"), str(CHARTED), str(HERE)]
    import empty_bootstrap as boot

    return boot


def worker(root, plan_pin, experiment, *, smoke=False):
    boot = start_runtime()
    import integrated_original_batch as chart

    book, _, earlier = chart.load_build(BUILD, BUILD_PIN)
    _, spec, _, publication, _ = boot.load_runtime()
    from tools import algo08_position, algo08_scan
    import exact_named_raw as raw
    from combined_successor_raw_entry import solver_ports
    from integrated_original_entry import positive_ports
    from legacy_first_map_acceleration import checked_artifacts
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    from prospective_0316_solver import denied
    from unified_short_bootstrap import Handoff

    if any(Path(module.__file__).resolve() != boot.PAYLOAD/"tools"/f"algo08_{label}.py"
           for label,module in (("position", algo08_position),("scan",algo08_scan))):
        raise ValueError("Saved solver must bind genuine installed scanner and position modules")
    plan = document(root/"plan.json", plan_pin)
    if (plan["case"] != CASE or plan["protocol"] != protocol(experiment) or plan["worker"] != identifier(Path(__file__))
            or plan["sources"] != source_pins(experiment)):
        raise ValueError("Changed frozen worker, plan or source recipe")
    admission = chart.document(STAGE/"admission.json", ADMISSION)
    signed = chart.document(STAGE/"authority.json", admission["authority_pin"])
    session, input_pin = signed["session_id"], signed["inventory_sha256"]
    change = plan["change"]
    native = document(root/"derived-native.json", change["derived_native_sha256"])
    detector, recipe = change["recipe_sha256"], change["recipe"]
    if (authority.canonical(recipe) != detector or plan["original_native_sha256"] != "sha256:"+admission["native_pin"]
            or recipe["sparse_native_sha256"] != plan["original_native_sha256"]
            or recipe["installed_native_sha256"] != plan["installed_native_sha256"]
            or authority.canonical(change[experiment.ledger]) != recipe[experiment.ledger_digest]):
        raise ValueError("The derived packet's original measurements or recipe are no longer bound")
    boot.bind_native(native, session, input_pin, detector[7:], expected=change["derived_native_sha256"])
    if detector in ("sha256:"+spec["detector_sha256"], "sha256:"+authority.SPARSE):
        raise ValueError("Counterfactual must carry its own detector identity")
    inventory = chart.document(STAGE/"inventory.json", input_pin)
    chart.match_native(signed, native)
    chart.match_inventory(signed, session, input_pin, inventory)
    recording, archive, offer = Path(signed["recording"]), STAGE/"tle", STAGE/"offer.json"
    chart.validate_case(signed, SimpleNamespace(recording=recording, region=offer))
    cutoff = signed["causal_cutoff_utc_ns"]
    if chart.archive_digest(archive, cutoff) != signed["archive_sha256"] or plan["original_archive"] != signed["archive_sha256"] or earlier >= cutoff:
        raise ValueError("Exact original causal catalogue and earlier portable producer required")
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    paths = [str(ref.path) for ref in refs]
    cache = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *paths]))["fincore"]
    if len(refs) != 48 or len(cache) != len(refs) or any(r["res"]<r["size"] for r in cache):
        raise ValueError("Use only the existing fully resident saved causal catalogue")
    pinned = book["native"]["--legacy-first-map-fast"]
    acceleration = checked_artifacts(Path(pinned["path"]), pinned["sha256"])
    portable = book["native"]["--portable-orbit-index"]
    args = SimpleNamespace(recording=recording, archive=archive, region=offer, output=root/"substituted",
                            archive_sha256=signed["archive_sha256"], history_risk_route=True,
                            portable_orbit_index=Path(portable["path"]), portable_orbit_index_sha256=portable["sha256"],
                            portable_orbit_producer_sha256=book["portable_producer"]["sha256"].removeprefix("sha256:"),
                            cairo_six_sheets=True, cairo_residual_layout=False)
    handoff = Handoff(session, input_pin, detector[7:], native)
    raw.request_from_handoff(args, handoff)

    def saved_inventory(_store, selected, *, verify_windows=True):
        if Path(selected) != recording or verify_windows:
            raise ValueError("Only the frozen inventory may be supplied")
        return session, input_pin, inventory

    ports = {}
    with (patch.object(FastScanStore, "inventory", saved_inventory),
          patch.object(FastSegmentSource, "windows", denied), patch.object(ShortWindowReader, "windows", denied),
          positive_ports(solver_ports, acceleration, ports)):
        if smoke:
            print(json.dumps(dict(case=CASE, changed=len(change[experiment.ledger]), refs=len(refs),
                                  acquired=handoff.calls, waveform_reads=0, solver_runs=0)))
            return
        receipt, _ = raw.publish_active(args, publication, spec, handoff)
    published, = args.output.glob("fast-scan-automatic-work/*/detections.json")
    document(published, change["derived_native_sha256"])
    document(args.output/"fast-scan-inputs"/(session+".json"), input_pin)
    if handoff.calls != 1:
        raise ValueError("Expected one non-waveform handoff through the original signed solver")
    print(write(root/"receipt.json", dict(case=CASE, input=change["derived_native_sha256"], receipt=receipt,
        witness=identifier(args.output/"exact-named-raw-witness.json"), plan_sha256=plan_pin, handoffs=handoff.calls,
        waveform_reads=0, graph_replayed=True, receiver_rerun=False, selector_rerun=False)))


def launch(root, plan_pin, experiment):
    config = attrs(expected_priority=experiment.priority)
    if document(root/"plan.json", plan_pin)["protocol"] != protocol(experiment):
        raise ValueError("Launch flag differs from frozen protocol")
    with LOCK.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        scratch = root/"scratch"
        scratch.mkdir()
        font = STAGE/"centroid-scratch"/"fontlist-v3.11.0.json"
        if font.is_file():
            copyfile(font, scratch/font.name)
        environment = os.environ | dict(TMPDIR=str(scratch), MPLCONFIGDIR=str(scratch), XDG_CACHE_HOME=str(scratch))
        command = [sys.executable, "-IB", str(Path(__file__)), "worker", str(root), "--pin", plan_pin]
        if experiment.option:
            command.append(experiment.option)
        with (root/"worker.stdout").open("x") as out, (root/"worker.stderr").open("x") as err:
            cpu, began, unix = getrusage(RUSAGE_CHILDREN), perf_counter_ns(), time_ns()
            try:
                status = subprocess.run(command, env=environment, stdout=out, stderr=err, timeout=28, check=False).returncode
            except subprocess.TimeoutExpired:
                status = 124
            final, ended = getrusage(RUSAGE_CHILDREN), perf_counter_ns()
        clock = write(root/"clock.json", dict(
            command=command, cpu_s=(final.ru_stime+final.ru_utime)-(cpu.ru_stime+cpu.ru_utime), elapsed_s=(ended-began)/1e9,
            started_unix_ns=unix, finished_unix_ns=time_ns(), io_blocks=final.ru_inblock-cpu.ru_inblock,
            major_faults=final.ru_majflt-cpu.ru_majflt, exit_code=status))
        print(write(root/"prediction-seal.json", dict(
            clock=clock, receipt=identifier(root/"receipt.json") if status==0 else None,
            machine=config, plan_sha256=plan_pin, protocol=protocol(experiment), source=identifier(Path(__file__)),
            survey_reads=0, waveform_reads=0)))
        if status:
            raise ValueError(f"Single candidate exit {status}; measured stderr and clock retained")


def compare_previous(plan, arms):
    results = {}
    for stem, pin in PREVIOUS.items():
        path = HERE/"measurements"/(stem+".json.gz")
        previous = authority.document(path, pin)["score"]
        if (previous["decision"] != "complete"
                or previous["crossover_inputs"]["sparse_native_sha256"] != plan["original_native_sha256"]
                or previous["crossover_inputs"]["installed_native_sha256"] != plan["installed_native_sha256"]):
            raise ValueError("Previous intervention must use the exact same two native originals")
        cells = previous["arms"]
        if any(cells[arm]["sparse_m"] != arms[arm]["sparse_m"] or cells[arm]["installed_m"] != arms[arm]["installed_m"]
               for arm in ARMS):
            raise ValueError("Previous results must share the exact geographic reference and baseline predictions")
        results[stem] = dict(arms={arm: {k: cells[arm][k] for k in (
            "counterfactual_m", "change_m", "conditional_rf_hz", "all_owned_rf_hz")} for arm in ARMS},
            clock=previous["clock"], support=previous["support"], receipt_sha256=pin)
    return results


def score(root, seal_pin, experiment):
    from sparse8_cfo_epoch_trial import geography

    seal = document(root/"prediction-seal.json", seal_pin)
    plan = document(root/"plan.json", seal["plan_sha256"])
    clock = document(root/"clock.json", seal["clock"])
    run = document(root/"receipt.json", seal["receipt"])
    directory = root/"substituted"
    witness = document(directory/"exact-named-raw-witness.json", run["witness"])
    receipt = run["receipt"]
    terminal = document(directory/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json", receipt["terminal_sha256"])
    old = ordinary(STAGE)
    if (clock["exit_code"] or run["handoffs"] != 1 or terminal["native_sha256"] != plan["change"]["derived_native_sha256"]
            or terminal["region"] != old["terminal"]["region"] or seal["protocol"] != protocol(experiment)
            or receipt["window_count"] != 986 or receipt["counts"]["processed"] != 932 or receipt["counts"]["invalid_capture"] != 54):
        raise ValueError("The sealed candidate does not bind its original receiver mechanism and offer")
    start_runtime().load_runtime()
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import owner_delta
    from raw_0016_best_score import position_sides
    from tools.pipeline_eval.scoring import distance_km

    crossover = document(CROSSOVER/"final-evidence.json", PARITY)
    stock_worker = document(CROSSOVER/"installed-installed"/"crossover-worker.json",
                            crossover["owner_row_source_sha256"]["installed-installed"])
    named_receipt = stock_worker["receipt"]
    stock = document(CROSSOVER/"installed-installed"/"fast-scan-automatic-work"/named_receipt["run_id"]/"terminal.json",
                     named_receipt["terminal_sha256"])
    old_owners, new_owners = (w["evidence"]["owner_rows"] for w in (old["witness"], witness))
    support = {label: owner_counts(roster, plan["change"][experiment.ledger], label=experiment.label) for label,roster in (
        ("installed",stock_worker["ordered_owners"]), ("sparse",old_owners), ("counterfactual",new_owners))}
    if experiment is EXCLUSION and any(arm["removed"] for arm in support["counterfactual"].values()):
        raise ValueError("An excluded observation was still submitted in final ownership")
    if experiment is RESTORATION and any(arm["inserted"] for arm in support["sparse"].values()):
        raise ValueError("Restoration touched an original sparse owner")
    result = dict(decision=receipt["decision"], clock=clock, old_saved_clock=plan["original_saved_clock"], scope=receipt,
                  crossover_inputs=plan["change"]["recipe"], support=support, seals=dict(prediction=seal_pin),
                  geographic=witness["ports"]["history_risk"].get("boundary_checks", []), advance=False, useful=False)
    if receipt["decision"] == "complete":
        media = artifacts(directory, receipt)
        store = FastStandardAnalysisStore(directory)
        position = position_sides(store, receipt, media)
        grid = store.position_grid(receipt["run_id"])
        earned = witness["evidence"]
        if (terminal["decision"] != "ok" or len(media["images"]) != 8 or grid["evaluated_points"] != 179
                or any(abs(v)>1e-5 for v in grid["endpoint_objective_replay"].values())
                or json.dumps(media["images"], sort_keys=True) != json.dumps(earned["images"], sort_keys=True)):
            raise ValueError("The normal verified standard evidence is incomplete")
        georef = geography(CASE)
        arms = {}
        for arm in ARMS:
            if canonical_digest({oid:j for oid,j,_ in new_owners[arm]}) != earned["detail"]["arms"][arm]["owner_sha256"]:
                raise ValueError("Counterfactual ordered owner rows do not match their official digest")
            a,b,c = (x["arms"][arm] for x in (stock,old["terminal"],terminal))
            errors = [1e3*distance_km(row["latlon"], georef) for row in (a,b,c)]
            arms[arm] = dict(installed_m=errors[0], sparse_m=errors[1], counterfactual_m=errors[2],
                change_m=errors[2]-errors[1], remaining_gap_m=errors[2]-errors[0],
                conditional_rf_hz=[row["rf_rms_hz"] for row in (a,b,c)],
                all_owned_rf_hz=[old["witness"]["evidence"]["detail"]["arms"][arm]["residual_rms_hz"],
                                 earned["detail"]["arms"][arm]["residual_rms_hz"]],
                owner_delta=owner_delta(old_owners[arm],new_owners[arm]),
                installed_owner_delta=owner_delta(stock_worker["ordered_owners"][arm],new_owners[arm]))
        fixed, fitted = (arms[a]["change_m"] for a in ARMS)
        gap = arms["fitted_c"]["sparse_m"]-arms["fitted_c"]["installed_m"]
        useful = fitted <= -250 and fixed <= 250
        advance = -fitted >= gap/2 and fixed <= 250
        if experiment is RESTORATION:
            useful = advance = fitted <= -250 and fixed <= -250
            stock_detail = FastStandardAnalysisStore(CROSSOVER/"installed-installed").detail(named_receipt["run_id"])
            result.update(prior_separate_interventions=compare_previous(plan, arms),
                          installed_all_owned_rf_hz={a:stock_detail["arms"][a]["residual_rms_hz"] for a in ARMS},
                          installed_saved_clock=crossover["cells"]["installed-installed"]["clocks"])
        result.update(arms=arms, position=position, media=media["images"], grid_replay=grid["endpoint_objective_replay"],
                      useful=useful, advance=advance, fitted_gap_recovered=-fitted/gap)
    elif receipt["decision"] != "withheld" or witness["evidence"]["images"] or list(directory.rglob("*.png")):
        raise ValueError("Unexpected incomplete saved scientific disposition")
    print(write(root/"score.json",result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare","smoke","launch","worker","score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--pin")
    options = parser.add_mutually_exclusive_group()
    for choice in (EXCLUSION, RESTORATION):
        options.add_argument(choice.option, dest="experiment", action="store_const", const=choice)
    parser.set_defaults(experiment=DONOR)
    args = parser.parse_args()
    experiment = args.experiment
    if args.action=="prepare":
        prepare(args.root, experiment)
    elif not args.pin:
        parser.error("Supply the frozen input or prediction SHA-256")
    elif args.action in ("smoke","worker"):
        worker(args.root, args.pin, experiment, smoke=args.action=="smoke")
    else:
        {"launch":launch, "score":score}[args.action](args.root, args.pin, experiment)
