"""Run one opt-in fixed-support weighted publication on the signed 0049 packet."""

import argparse
import fcntl
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from shutil import copyfile
import subprocess
import sys
from time import perf_counter_ns, time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
STAGE = Path("/dev/shm/leo-v3-cfo-epoch-0049-saved01")
LAW = HERE/"measurements/held-native-precision.json.gz"
LAW_PIN = "cb84ca1c57822ef603d194d10acca022e700657e30db6676c903e68545c0e80b"
PROTOCOL = HERE/"held-native-precision-0049-protocol.md"
CASE = "DS30-0049"
HOLDOUT = "DS30-0019"
ARMS = ("c0", "fitted_c")


def inputs():
    from sparse8_cfo_epoch_challenge import ADMISSION
    from sparse8_cfo_epoch_saved import BUILD, BUILD_PIN, CHARTED, deny_backing
    from signed_cfo_time_readout import document

    sys.addaudithook(deny_backing)
    sys.path[:0] = [str(CHARTED/"reports/ALGO08/v3"), str(CHARTED), str(HERE)]
    import empty_bootstrap as boot
    import integrated_original_batch as chart

    book, _, producer_cutoff = chart.load_build(BUILD, BUILD_PIN)
    _, spec, _, publication, _ = boot.load_runtime()
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from leo.operations.tle_archive import TleArchiveReader
    from legacy_first_map_acceleration import checked_artifacts
    from unified_short_bootstrap import Handoff

    if Path(algo08_position.__file__).resolve() != boot.PAYLOAD/"tools/algo08_position.py":
        raise ValueError("The installed saved scientific entry is unavailable")
    if Path(algo08_scan.__file__).resolve() != boot.PAYLOAD/"tools/algo08_scan.py" or not callable(v5_core.infer):
        raise ValueError("The installed scan boundary is unavailable")
    admission = chart.document(STAGE/"admission.json", ADMISSION)
    signed = chart.document(STAGE/"authority.json", admission["authority_pin"])
    signed_native = chart.document(STAGE/"native.json", admission["native_pin"])
    inventory_sha = signed["inventory_sha256"]
    inventory = chart.document(STAGE/"inventory.json", inventory_sha)
    recording, archive, offer = Path(signed["recording"]), STAGE/"tle", STAGE/"offer.json"
    chart.validate_case(signed, SimpleNamespace(recording=recording, region=offer))
    cutoff = signed["causal_cutoff_utc_ns"]
    if chart.archive_digest(archive, cutoff) != signed["archive_sha256"] or producer_cutoff >= cutoff:
        raise ValueError("The original pre-capture catalogue or earlier portable source changed")
    chart.match_native(signed, signed_native)
    chart.match_inventory(signed, signed["session_id"], inventory_sha, inventory)
    causal = TleArchiveReader(archive).list_snapshots("space-track")
    files = [str(ref.path) for ref in causal] + [str(STAGE/name) for name in ("native.json", "inventory.json", "offer.json")]
    cache = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *files]))["fincore"]
    if len(causal) != 48 or len(cache) != len(files) or any(row["res"] < row["size"] for row in cache):
        raise ValueError("The full signed detector and causal catalogue must be resident")
    detector = signed_native["provenance"]["detector_sha256"][7:]
    boot.bind_native(signed_native, signed["session_id"], inventory_sha, detector, expected="sha256:"+admission["native_pin"])
    rule = document(LAW, LAW_PIN)
    if (not rule["qualifies"] or min(rule["eligible_held"]) != HOLDOUT or admission["case"] != CASE
            or rule["cases"][CASE]["input"]["candidate_native_sha256"] != "sha256:"+admission["native_pin"]):
        raise ValueError("The frozen development model and exact saved input are required")
    handoff = Handoff(signed["session_id"], inventory_sha, detector, signed_native)
    library = book["native"]["--legacy-first-map-fast"]
    acceleration = checked_artifacts(Path(library["path"]), library["sha256"])
    portable = book["native"]["--portable-orbit-index"]
    options = SimpleNamespace(recording=recording, archive=archive, region=offer, archive_sha256=signed["archive_sha256"],
                              history_risk_route=True, portable_orbit_index=Path(portable["path"]),
                              portable_orbit_index_sha256=portable["sha256"],
                              portable_orbit_producer_sha256=book["portable_producer"]["sha256"].removeprefix("sha256:"),
                              cairo_six_sheets=True, cairo_residual_layout=False)
    return options, (spec, publication, signed, signed_native, inventory, admission, rule, acceleration, handoff)


def worker(root, *, smoke=False):
    args, (spec, publication, signed, native, inventory, admission, rule, acceleration, handoff) = inputs()
    from combined_successor_raw_entry import solver_ports
    from exact_named_raw import request_from_handoff
    import exact_named_raw as raw
    from held_precision_finish import FixedPrecision, target_scales
    from integrated_original_entry import positive_ports
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    from prospective_0316_solver import denied
    from sparse8_cfo_epoch_trial import document, identifier, write

    def saved_inventory(_self, recording, *, verify_windows=True):
        if Path(recording) != args.recording or verify_windows:
            raise ValueError("The saved likelihood cannot request the original waveform")
        return signed["session_id"], signed["inventory_sha256"], inventory

    targets = target_scales(native, rule["model"]["scale_hz2"])
    rows, _ = winning_observations(native)
    if targets.keys() != {row["observation_id"] for row in rows} or len(rows) != 600:
        raise ValueError("Matched precision identities differ from Graph-winning signed rows")
    request_from_handoff(args, handoff)
    treatment = FixedPrecision(targets)
    ports = {}
    if smoke:
        with treatment.install(), positive_ports(solver_ports, acceleration, ports):
            if handoff.calls or treatment.audit["status"] != "unavailable":
                raise ValueError("Preflight changed measurements or found an unsupported precision port")
        print(json.dumps(dict(case=CASE, candidates=len(targets), anchors=sum(v is None for v in targets.values()),
                              waveform_reads=0, solves=0)))
        return
    args.output = root/"weighted"
    with (patch.object(FastScanStore, "inventory", saved_inventory),
          patch.object(FastSegmentSource, "windows", denied), patch.object(ShortWindowReader, "windows", denied),
          treatment.install(), positive_ports(solver_ports, acceleration, ports)):
        receipt, _ = raw.publish_active(args, publication, spec, handoff)
    published, = args.output.glob("fast-scan-automatic-work/*/detections.json")
    document(published, admission["native_pin"])
    document(args.output/"fast-scan-inputs"/(signed["session_id"]+".json"), signed["inventory_sha256"])
    if handoff.calls != 1:
        raise ValueError("The saved weighted build must consume the original handoff once")
    return write(root/"weighted-receipt.json", dict(case=CASE, protocol=identifier(PROTOCOL),
        worker=identifier(Path(__file__)), precision_source=identifier(HERE/"held_precision_finish.py"), law=LAW_PIN,
        native_sha256=identifier(published), inventory_sha256=signed["inventory_sha256"], waveform_reads=0,
        handoffs=handoff.calls, ordinary_graph_input=canonical_digest(rows), precision=treatment.summary(),
        receipt=receipt, witness_sha256=identifier(args.output/"exact-named-raw-witness.json")))


def launch(root):
    from sparse8_cfo_epoch_challenge import ordinary
    from sparse8_cfo_epoch_trial import LOCK, attrs, identifier, write

    machine = attrs()
    archived = ordinary(STAGE)
    if root.parent.resolve() != Path("/dev/shm") or root.exists():
        raise ValueError("Use a fresh tmpfs publication root")
    with LOCK.open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root.mkdir(mode=0o700)
        scratch = root/"scratch"
        scratch.mkdir()
        font = STAGE/"centroid-scratch"/"fontlist-v3.11.0.json"
        if font.is_file():
            copyfile(font, scratch/font.name)
        env = os.environ | dict(TMPDIR=str(scratch), MPLCONFIGDIR=str(scratch), XDG_CACHE_HOME=str(scratch))
        command = [sys.executable, "-IB", str(Path(__file__)), "worker", str(root)]
        with (root/"weighted.stdout").open("x") as out, (root/"weighted.stderr").open("x") as err:
            before, unix, start = getrusage(RUSAGE_CHILDREN), time_ns(), perf_counter_ns()
            try:
                status = subprocess.run(command, stdout=out, stderr=err, env=env, check=False, timeout=28).returncode
            except subprocess.TimeoutExpired:
                status = 124
            after, end = getrusage(RUSAGE_CHILDREN), perf_counter_ns()
        clock = dict(started_unix_ns=unix, finished_unix_ns=time_ns(), elapsed_s=(end-start)/1e9,
                     cpu_s=(after.ru_utime-before.ru_utime)+(after.ru_stime-before.ru_stime),
                     input_blocks=after.ru_inblock-before.ru_inblock, major_faults=after.ru_majflt-before.ru_majflt,
                     exit_code=status, command=command)
        pin = write(root/"weighted-clock.json", clock)
        prediction = dict(case=CASE, next_case=HOLDOUT, machine=machine, clock_sha256=pin,
                          ordinary_parity=archived["parity"], ordinary_clock=archived["timed_saved_clock"],
                          ordinary_terminal_sha256=archived["witness"]["evidence"]["detail"]["terminal_sha256"],
                          protocol=identifier(PROTOCOL), waveform_reads=0,
                          weighted_receipt_sha256=identifier(root/"weighted-receipt.json") if not status else None)
        print(write(root/"prediction-seal.json", prediction))
        if status:
            raise ValueError(f"The single saved child exited {status}; inspect its sealed clock and stderr")


def score(root, pin):
    from sparse8_cfo_epoch_challenge import CROSSOVER, ordinary
    from sparse8_cfo_epoch_saved import CHARTED, deny_backing
    from sparse8_cfo_epoch_trial import document, geography, identifier, write

    sys.addaudithook(deny_backing)
    sys.path[:0] = [str(CHARTED/"reports/ALGO08/v3"), str(CHARTED), str(HERE)]
    from empty_bootstrap import load_runtime

    sealed = document(root/"prediction-seal.json", pin)
    if sealed["case"] != CASE or sealed["protocol"] != identifier(PROTOCOL) or sealed["next_case"] != HOLDOUT:
        raise ValueError("The development prediction seal differs from its fixed protocol")
    clock = document(root/"weighted-clock.json", sealed["clock_sha256"])
    run = document(root/"weighted-receipt.json", sealed["weighted_receipt_sha256"])
    out = root/"weighted"
    witness = document(out/"exact-named-raw-witness.json", run["witness_sha256"])
    receipt = run["receipt"]
    terminal_path = out/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json"
    terminal = document(terminal_path, receipt["terminal_sha256"])
    old = ordinary(STAGE)
    if (clock["exit_code"] or run["handoffs"] != 1 or terminal["native_sha256"] != old["terminal"]["native_sha256"]
            or terminal["region"] != old["terminal"]["region"]):
        raise ValueError("The candidate differs from its original signed input, offer or execution")
    load_runtime()
    from joint_publication import artifacts
    from publication_media_checks import image_comparison_fields
    from raw_0016_best_score import position_sides
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.scoring import distance_km

    route = witness["ports"]["history_risk"]
    repair = [arm.get("local_future_repair") for arm in route["lean_attempts"]]
    output = dict(case=CASE, clocks=dict(weighted=clock, archived_ordinary=sealed["ordinary_clock"]),
                  precision=run["precision"], evidence=witness["evidence"], route=route, prediction_sha256=pin,
                  decision=receipt["decision"], qualification=False)
    if receipt["decision"] == "complete":
        if terminal["decision"] != "ok":
            raise ValueError("The standard complete receipt must bind an actual position terminal")
        media = artifacts(out, receipt)
        store = FastStandardAnalysisStore(out)
        sides = position_sides(store, receipt, media)
        before, after = old["witness"]["evidence"], witness["evidence"]
        same = before["owner_rows"] == after["owner_rows"]
        for arm, roster in after["owner_rows"].items():
            if canonical_digest({oid: norad for oid, norad, _role in roster}) != after["detail"]["arms"][arm]["owner_sha256"]:
                raise ValueError("The owner rows do not bind the authoritative owner map")
        if (len(sides["figures"]) != 8 or sides["grid_points"] != 179
                or before["detail"]["session_id"] != after["detail"]["session_id"]
                or json.dumps(image_comparison_fields(media["images"]), sort_keys=True)
                != json.dumps(image_comparison_fields(after["images"]), sort_keys=True)):
            raise ValueError("Missing or unbound standard products")
        old_grid = FastStandardAnalysisStore(CROSSOVER/"successor-successor").position_grid(receipt["run_id"])
        grid = store.position_grid(receipt["run_id"])
        path = store.position_path(receipt["run_id"])
        keys = ("region_center", "box_width_km", "matched_c_grid", "coarse_size", "local_size", "local_half_width_km")
        if (any(old_grid[k] != grid[k] for k in keys) or set(grid["endpoint_objective_replay"]) != set(ARMS)
                or any(abs(v) > 1e-5 for v in grid["endpoint_objective_replay"].values())
                or any(path["stages"][-1]["arms"][arm]["endpoint"] != grid["endpoints"][arm] for arm in ARMS)):
            raise ValueError("The original numerical evidence coverage or endpoint replay changed")
        points = [{(p["east_km"], p["north_km"]) for p in product["points"]} for product in (old_grid, grid)]
        numerical = dict(common_locations=len(points[0] & points[1]), planned=grid["planned_points"],
                         replay=grid["endpoint_objective_replay"],
                         path_rounds={arm: len(path["stages"][-1]["arms"][arm]["rounds"]) for arm in ARMS},
                         png_changes=sum(item["sha256"] != before["images"][name]["sha256"]
                                         for name,item in after["images"].items()))
        reference = geography(CASE)
        results = {}
        for arm in ARMS:
            a, b = old["terminal"]["arms"][arm], terminal["arms"][arm]
            earlier, current = (1000*distance_km(v["latlon"], reference) for v in (a,b))
            if not all(isfinite(v) for v in (*b["latlon"], b["rf_rms_hz"], current)):
                raise ValueError("The calibration arm is incomplete")
            results[arm] = dict(before_error_m=earlier, current_error_m=current, change_m=current-earlier,
                before_rf_hz=a["rf_rms_hz"], current_rf_hz=b["rf_rms_hz"],
                before_all_owned_hz=before["detail"]["arms"][arm]["residual_rms_hz"],
                current_all_owned_hz=after["detail"]["arms"][arm]["residual_rms_hz"],
                ordinary_owner_count=len(before["owner_rows"][arm]), weighted_owner_count=len(after["owner_rows"][arm]))
        deltas = [r["change_m"] for r in results.values()]
        actual = any(item and item["decision"] == "accepted" for item in repair) and run["precision"].get("weighted_evidence")
        output.update(arms=results, same_ordered_owners=same, actual_weighted=bool(actual), products=sides,
                      numerical=numerical,
                      qualification=bool(actual and same and max(deltas) <= 250 and min(deltas) <= -250))
    print(write(root/"score.json", output))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "smoke", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--seal")
    args = parser.parse_args()
    if args.action == "score":
        score(args.root, args.seal)
    elif args.action == "launch":
        launch(args.root)
    else:
        worker(args.root, smoke=args.action == "smoke")
