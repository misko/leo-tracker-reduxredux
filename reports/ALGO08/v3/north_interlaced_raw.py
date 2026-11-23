"""Measure one raw-to-web northern comparison with the frozen primary interlaced schedule."""

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import runpy
import subprocess
from time import perf_counter, process_time_ns, thread_time_ns, time_ns
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
BENCH = Path("/tmp/leo-algo08v2-2x-bench")
SOURCE = BENCH / "exact-curved-lookahead-north-inside/pair.json"
SOURCE_SHA = "9bf5dc4e3ef1e2df17f8d8184bca74f2ce9559a1e154401b9f6330f8e97feaeb"
NORTH = "0abe7b4514be674d9f5388e3"
MANIFEST_SHA = "0205ca2d10c1282f6c782c93a32d2bff1ae8a7b39ff959c93b4ca3613f0f07eb"
OFFER_SHA = "f4ff743e9f3d00bc18344143bffaaf7801276018dbd75b6ab2ec5207e887e891"
REFERENCE_SHA = "334f9795489d9a85e535eb848623637cd59ff18903b9cb8e478c6ac4c30c6db1"
TRUTH_SHA = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
RECEIVER_SHA = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
CACHE_SHA = "4f10e0a2e23121e184ee7d37767f55c29fefc158f4182a2dd99c4268ff2ce6ab"
PILOT = {"lower": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
         "upper": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c"}
GRAPH = dict(max_degree=2, points_per_coefficient=2, min_points=6)
ARMS = ("c0", "fitted_c")


def verified(path, expected):
    content = path.read_bytes()
    if sha256(content).hexdigest() != expected:
        raise ValueError(f"Unexpected input SHA-256 for {path}")
    return content


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def streams_and_slots(records, *, visits_per_stream=150, stream_count=8):
    """Assign two different visit times in each complete per-RF triple."""
    streams = defaultdict(list)
    for visit, key in enumerate(records):
        streams[key].append(visit)
    if (visits_per_stream <= 0 or visits_per_stream % 3 or len(streams) != stream_count
            or any(len(visits) != visits_per_stream for visits in streams.values())):
        raise ValueError("Expected an equal number of complete stereo triples on each RF stream")
    slots = set()
    for rank, (_, visits) in enumerate(sorted(streams.items())):
        moving = rank % 2
        for start in range(0, len(visits), 3):
            home, moved = rank % 3, (rank + 1) % 3
            slots.add((visits[start + home], 1 - moving))
            slots.add((visits[start + moved], moving))
    return streams, slots


def stream_key(acquisition, target):
    return target["channel"], float(acquisition["actual_if_center_hz"] + target["lnb_lo_hz"]), target["edge"]


def make_plan(recording):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource, FastScanStore
    from first_third_ingress import chunk_rows

    verified(recording / "manifest.json", MANIFEST_SHA)
    _, binding, inventory = FastScanStore(recording.parent).inventory(recording, verify_windows=False)
    if inventory["window_count"] != 1200 or len(inventory["segments"]) != 1:
        raise ValueError("Expected the pinned 1,200-window northern segment")
    source = FastSegmentSource(inventory["segments"][0])
    manifest = source.reader.manifest
    policy = FastScanPolicyV2()
    samples = []
    for chunk in manifest.chunks:
        for row in chunk_rows(source, chunk):
            acquisition = row.acquisition
            if (len(samples) != acquisition["global_visit"] or source.receiver_ids != (0, 1)
                    or not valid_window_support(acquisition, manifest.sample_rate_hz,
                                                (row.sample_count, row.receiver_count, 2),
                                                source.receiver_ids, policy)):
                raise ValueError("The northern schedule requires complete ordered admitted visits")
            samples.append(stream_key(acquisition, source.targets[row.target_id]))
    streams, slots = streams_and_slots(samples)
    return samples, streams, slots, binding


def strongest(candidates):
    if any(not row["passed_fractional_margin_gate"] for row in candidates):
        raise ValueError("The installed native receiver emitted an unverified factor")
    return max(candidates, key=lambda row: (row["fractional_margin"], -row["candidate_rank"]), default=None)


class PaidDetector:
    def __init__(self, records, slots):
        self.records, self.slots = records, slots
        self.seen = []
        self.paid = []

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        import ctypes as ct
        import numpy as np
        from tools.pipeline_eval.qualification.blind_compact_run import Factor, Native, _probe, factor_candidate

        if method != "cancellation":
            raise ValueError("Expected the original signed two-scan receiver")
        verified(binary, RECEIVER_SHA)
        asset = np.frombuffer(verified(pilot, PILOT[edge]), dtype="<f4")
        receiver = Native(binary, asset)
        call = receiver.lib.cancellation_factors
        call.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(Factor)]
        call.restype = ct.c_int

        def visit(window):
            visit_index = window.acquisition["global_visit"]
            key = stream_key(window.acquisition, window.target)
            if (visit_index != len(self.seen) or visit_index >= len(self.records)
                    or key != self.records[visit_index] or tuple(window.receiver_ids) != (0, 1)):
                raise ValueError("Authenticated planning rows and original raw visitor differ")
            self.seen.append(key)
            mid = window.target["rf_center_hz"] - key[1]
            rows = []
            for lane in window.receiver_ids:
                picked = None
                if (visit_index, lane) in self.slots:
                    vector = (Factor * 2)()
                    tick = thread_time_ns()
                    count = call(receiver.ctx, window.samples.ctypes.data, lane, mid - 800000, mid + 800000, vector)
                    cpu = thread_time_ns() - tick
                    if not 0 <= count <= 2:
                        raise ValueError("Unexpected signed native factor count")
                    candidates = [factor_candidate(row.rank, row.integer, status="complete", offset=row.offset,
                                                   cfo=row.hz, exact=row.exact, control=row.control,
                                                   margin=row.exact-row.control) for row in vector[:count]]
                    picked = strongest(candidates)
                    self.paid.append(dict(slot=[visit_index, lane], native_cpu_ns=cpu, factors=candidates))
                rows.append(_probe(window, lane, [] if picked is None else [picked]))
            return rows

        try:
            yield visit
        finally:
            receiver.close()


def candidate(args):
    from joint_publication import run

    planned = []

    def prepare():
        start = process_time_ns()
        records, streams, slots, binding = make_plan(args.recording)
        detector = PaidDetector(records, slots)
        planned.append((records, streams, slots, binding, process_time_ns() - start, detector))
        return detector.detector

    args.saved = args.saved_digest = None
    args.signed_finish, args.verify_images = True, False
    run(args, prepare_detector=prepare, detector_description="verified raw with measured interlaced lanes",
        track_config=lambda cfg: replace(cfg, **GRAPH))
    from leo.contracts.digests import canonical_digest

    (records, streams, slots, binding, plan_cpu, detector), = planned
    if detector.seen != records or {tuple(row["slot"]) for row in detector.paid} != slots or len(detector.paid) != 800:
        raise ValueError("Unexpected native call count, assay scope or paid lane duplicates")
    write(args.output / "interlaced-schedule.json", dict(plan_cpu_ns=plan_cpu, inventory_sha256=binding,
          stream_sizes=[[key, len(visits)] for key, visits in sorted(streams.items())],
          mask_sha256=canonical_digest(sorted(slots)), paid=detector.paid,
          paid_stereo_visits=len({visit for visit, _ in slots}), graph=GRAPH))


def arm_evidence(root, receipt, started, audit):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification import paired_publication as pairs
    from joint_publication import artifacts

    native_file, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    terminal_file, = (root / "fast-scan-automatic-work").glob("*/terminal.json")
    if terminal_file.parent.name != receipt["run_id"]:
        raise ValueError("Published workspace does not agree with the receipt")
    # The pinned storage API predates the create=False keyword. Verify the
    # terminal path exists before dispatching the stock evidence helper.
    report = pairs.evidence(root, receipt, started_ns=started)
    raw = native_file.read_bytes()
    native = json.loads(raw)
    terminal = json.loads(terminal_file.read_bytes())
    if canonical_digest(native) != terminal["native_sha256"]:
        raise ValueError("The published terminal is not bound to the measured detector record")
    standard_report = root/"fast-scan-reports"/f"{receipt['run_id']}.json"
    stamps = dict(acquisition_lock_ns=(native_file.parent/"owner.lock").stat().st_mtime_ns,
                  detections_ns=native_file.stat().st_mtime_ns,
                  terminal_ns=terminal_file.stat().st_mtime_ns,
                  report_ns=standard_report.stat().st_mtime_ns)
    metrics = dict(native_sha256=canonical_digest(native), native_file_sha256=sha256(raw).hexdigest(),
                   detection_file_s=(native_file.stat().st_mtime_ns-started)/1e9,
                   selected=sum(len(row["candidates"]) for row in native["source"]["probes"]),
                   workspace_file_mtimes_ns=stamps, evidence=artifacts(root, receipt), **report, **audit)
    if not started:
        metrics.pop("detection_file_s")
        metrics.pop("terminal_file_s")
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(root)
        grid = store.position_grid(receipt["run_id"])
        if set(metrics["arms"]) != set(ARMS) or not grid["complete"]:
            raise ValueError("Both calibration arms and a complete evidence grid are required")
        metrics["verified_grid_points"] = grid["evaluated_points"]
    metrics["selected_by_rank"] = dict(Counter(
        candidate["candidate_rank"] for row in native["source"]["probes"] for candidate in row["candidates"]))
    return metrics, native


def validate_schedule(baseline, candidate_raw, schedule, reference_source):
    from leo.contracts.digests import canonical_digest

    base, new = baseline["source"]["probes"], candidate_raw["source"]["probes"]
    if (len(base) != len(new) or len(new) != 2400
            or any(dict(r, candidates=[]) != dict(p, candidates=[]) for r, p in zip(base, new, strict=True))):
        raise ValueError("The schedules changed admitted probe opportunities")
    verified(reference_source, REFERENCE_SHA)
    reference_slots = runpy.run_path(str(reference_source))["slots"]
    allowed = {(new[index]["visit_index"], new[index]["receiver_id"]) for index in reference_slots(new, False)}
    actual = {tuple(row["slot"]): row["factors"] for row in schedule["paid"]}
    if (len(actual) != len(schedule["paid"]) or set(actual) != allowed or len(allowed) != 800
            or canonical_digest(sorted(allowed)) != schedule["mask_sha256"]
            or candidate_raw["source"]["input_manifest_sha256"] != schedule["inventory_sha256"]):
        raise ValueError("Measured mask differs from the frozen reference on original accepted metadata")
    for row in new:
        option = strongest(actual.get((row["visit_index"], row["receiver_id"]), []))
        if row["candidates"] != ([] if option is None else [option]):
            raise ValueError("A masked row or native maximum margin differs")


def score(runs):
    from tools.pipeline_eval.scoring import distance_km

    positions = json.loads(verified(HERE.parent / "regional-release/scoring-key.json", TRUTH_SHA))
    truth, = {tuple(row["truth"]) for row in positions["answers"].values() if row["recording"] == NORTH}
    result = {}
    for key, row in runs.items():
        if row["receipt"]["decision"] != "complete":
            result[key] = {}
            continue
        result[key] = {arm: dict(error_km=distance_km(row["arms"][arm]["latlon"], truth),
                                 rf_rms_hz=row["arms"][arm]["rf_rms_hz"]) for arm in ARMS}
    complete = bool(result["baseline"] and result["candidate"])
    delta = {arm: result["candidate"][arm]["error_km"]-result["baseline"][arm]["error_km"]
             for arm in ARMS} if complete else {}
    return dict(public_truth=list(truth), scores=result, position_delta_km=delta,
                passed_250m_screen=complete and all(value <= .25 for value in delta.values()))


def pair(output, reference_source):
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification import cache_residency as cache
    from tools.pipeline_eval.qualification import paired_publication as pairs
    from aperture_trial import PAYLOAD, RELEASE, archive_identity, machine

    verified(reference_source, REFERENCE_SHA)
    identity = json.loads(verified(SOURCE, SOURCE_SHA))
    recording, archive, offer = Path(identity["recording"]), Path(identity["archive"]["root"]), Path(identity["region"])
    verified(offer, OFFER_SHA)
    verified(recording / "manifest.json", MANIFEST_SHA)
    if (recording.name != NORTH or archive_identity(archive) != identity["archive"]
            or subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", recording], text=True).strip() != "tmpfs"):
        raise ValueError("Expected the pinned tmpfs recording and original causal archive")
    settings = machine()
    if (settings["cpu"] != [2] or settings["nice"] < 15 or "prio 7" not in settings["ionice"]
            or any(value != "1" for value in settings["threads"].values())):
        raise ValueError("Expected Gauss CPU 2 at the chosen priorities")
    pairs.verified_v3(pairs.NAMED_V3)
    output.mkdir(exist_ok=False)
    store = FastScanStore(output)
    _, _, inventory = store.inventory(recording, verify_windows=False)
    pins = tuple((Path(row["path"])/"manifest.json", row["manifest_digest"]) for row in inventory["segments"])
    query_file = BENCH / "ds30-cache-residency.so"
    verified(query_file, CACHE_SHA)
    query = cache.load_query(query_file)
    shared_args = ["--recording", str(recording), "--region", str(offer), "--archive", str(archive)]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (HERE, PAYLOAD, RELEASE/"src", RELEASE))))
    for name in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                 "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(name, None)
    launches = {}
    for arm in ("candidate", "baseline"):
        root = output / arm
        if arm == "baseline":
            root.mkdir()
            command = [str(pairs.NAMED_V3), *shared_args, "--bulk-root", str(root)]
        else:
            command = [str(RELEASE/"venv/bin/python"), "-BPs", __file__, "candidate", *shared_args, "--output", str(root)]
        snapshot = cache.bound_snapshot(store, recording, pins, os.sysconf("SC_PAGE_SIZE"), query)
        usage, started, wall = pairs.child_usage(), time_ns(), perf_counter()
        child = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60)
        time = perf_counter()-wall
        counters = {name: value-usage[name] for name, value in pairs.child_usage().items()}
        raw_launch = dict(elapsed_s=time, started_ns=started, cache=snapshot, command=command,
                          returncode=child.returncode, **counters)
        write(output/f"{arm}-launch-clock.json", raw_launch)
        if child.returncode:
            raise RuntimeError(f"{arm} failed after {time:.3f} seconds: {child.stderr[-4000:]}")
        launches[arm] = raw_launch
        if arm == "baseline":
            receipt = json.loads(child.stdout.splitlines()[-1])
            pairs.verify_v3_publication(root, receipt)
            launches[arm]["receipt"] = receipt
        else:
            study = json.loads((root/"joint-research-receipt.json").read_bytes())
            launches[arm]["receipt"] = study["receipt"]
            launches[arm]["research"] = study
    finish_pair(output, reference_source, identity, settings, launches)


def audit_existing(output, reference_source, receipt_root):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification import paired_publication as pairs

    verified(reference_source, REFERENCE_SHA)
    identity = json.loads(verified(SOURCE, SOURCE_SHA))
    baseline = output/"baseline"
    marker = json.loads((baseline/"algo08v3-release.json").read_bytes())
    terminal_file, = (baseline/"fast-scan-automatic-work").glob("*/terminal.json")
    terminal = json.loads(terminal_file.read_bytes())
    run_id = terminal_file.parent.name
    scan = json.loads((baseline/"fast-scan-reports"/f"{run_id}.json").read_bytes())
    receipt = dict(run_id=run_id, session_id=marker["session_id"], decision=marker["decision"],
                   terminal_sha256=canonical_digest(terminal), region=terminal["region"],
                   counts=scan["counts"], window_count=scan["window_count"])
    pairs.verify_v3_publication(baseline, receipt)
    study = json.loads((output/"candidate/joint-research-receipt.json").read_bytes())
    launches = {}
    for arm, returned in (("candidate", study["receipt"]), ("baseline", receipt)):
        clock = output / f"{arm}-launch-clock.json"
        launches[arm] = json.loads(clock.read_bytes()) if clock.is_file() else dict(started_ns=0)
        launches[arm]["receipt"] = returned
    launches["candidate"]["research"] = study
    receipt_root.mkdir(exist_ok=False)
    finish_pair(output, reference_source, identity, study["machine"], launches, receipt_root=receipt_root)


def finish_pair(output, reference_source, identity, settings, launches, *, receipt_root=None):
    receipt_root = output if receipt_root is None else receipt_root
    runs, natives = {}, {}
    for arm, launch in launches.items():
        receipt = launch.pop("receipt")
        runs[arm], natives[arm] = arm_evidence(output / arm, receipt, launch.pop("started_ns"), launch)
        if (runs[arm]["raw_authority"] != identity["runs"]["candidate"]["raw_authority"]
                or receipt["region"] != identity["runs"]["candidate"]["receipt"]["region"]
                or receipt["counts"] != dict(invalid_capture=0, processed=1200, skipped_fast_score=0)
                or natives[arm]["provenance"]["detector_sha256"] != "sha256:" + RECEIVER_SHA):
            raise ValueError("A timed arm did not consume the exact pinned native waveform authority")
    if runs["baseline"]["arms"] != identity["runs"]["candidate"]["arms"]:
        raise ValueError("The freshly installed v3 baseline differs from the earlier sealed control")
    schedule = json.loads((output/"candidate/interlaced-schedule.json").read_bytes())
    validate_schedule(natives["baseline"], natives["candidate"], schedule, reference_source)
    data = dict(order=list(runs), runs=runs, schedule=schedule, machine=settings,
                source_pair_sha256=SOURCE_SHA, manifest_sha256=MANIFEST_SHA, archive=identity["archive"],
                region_sha256=OFFER_SHA, reference_schedule_sha256=REFERENCE_SHA,
                clock_scope="launch through exit" if "elapsed_s" in runs["baseline"]
                else "recovered publication file timestamps and candidate internal clocks")
    sealed = receipt_root / "sealed-before-scoring.json"
    write(sealed, data)
    result = score(runs)
    if "elapsed_s" in runs["baseline"]:
        result["wall_speedup"] = runs["baseline"]["elapsed_s"] / runs["candidate"]["elapsed_s"]
        result["cpu_speedup"] = runs["baseline"]["cpu_s"] / runs["candidate"]["cpu_s"]
    for arm in runs.values():
        timestamps = arm["workspace_file_mtimes_ns"]
        arm["file_stamp_intervals_s"] = {
            "acquisition_lock_to_detections": (timestamps["detections_ns"]-timestamps["acquisition_lock_ns"])/1e9,
            "detections_to_terminal": (timestamps["terminal_ns"]-timestamps["detections_ns"])/1e9,
            "terminal_to_report": (timestamps["report_ns"]-timestamps["terminal_ns"])/1e9,
            "acquisition_lock_to_report": (timestamps["report_ns"]-timestamps["acquisition_lock_ns"])/1e9,
        }
    write(receipt_root/"pair.json", dict(data, transfer=result, pre_score_sha256=sha256(sealed.read_bytes()).hexdigest()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    parsers = cli.add_subparsers(dest="mode", required=True)
    parent = parsers.add_parser("pair")
    parent.add_argument("output", type=Path)
    parent.add_argument("reference_source", type=Path)
    offline = parsers.add_parser("audit-existing")
    offline.add_argument("output", type=Path)
    offline.add_argument("reference_source", type=Path)
    offline.add_argument("receipt_root", type=Path)
    child = parsers.add_parser("candidate")
    for key in ("recording", "archive", "region", "output"):
        child.add_argument("--"+key, type=Path, required=True)
    args = cli.parse_args()
    if args.mode == "candidate":
        candidate(args)
    elif args.mode == "pair":
        pair(args.output.resolve(), args.reference_source.resolve())
    else:
        audit_existing(args.output.resolve(), args.reference_source.resolve(), args.receipt_root.resolve())
