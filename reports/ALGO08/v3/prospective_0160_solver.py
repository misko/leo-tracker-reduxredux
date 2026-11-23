"""Run one prospectively assigned solver-only pair on the saved named DS30-0160 input."""

import argparse
import csv
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
import stat
import subprocess
import sys
from time import perf_counter, process_time

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from prospective_0316_solver import ARMS, DETECTOR, INPUT_DESCRIPTION, LIBRARIES, ORDER, SOURCE_PINS
from prospective_0316_solver import elapsed, inspect, owner_delta, verify_sources, worker
from prospective_small_physical import CACHE_LIB, CACHE_PIN, ROSTER, ROSTER_PINS, checked, ranked_cases
from prospective_solver_budget import DATA, MODEL, MODEL_SHA, predictions


HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "prospective-0160-solver-protocol.md"
BASE = "c7dfb2bfc5c52384cf635ac0f73b662af581181e"
CASE, ISSUED, ADMITTED = "DS30-0160", 3691, 2354
EXCLUSIONS = ("DS30-0008", "DS30-0016", "DS30-0057", "DS30-0227", "DS30-0316")
PAIR_SHA = "975052db3a21dc7439ef53830c5c46336cc62e2c5111f003a790221f148aaf03"
NATIVE_SHA = "1c56c47f871933cdc1887e41d79d2b28da0624b3104d2e5b05d0957c488bd4b5"
BINDING_SHA = "5afc021402c5501318e1f17224ddc3a11c80af468f46ee94c647eba6c04b6cfd"
OFFER_SHA = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
STAGES_SHA = "fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a"
STOCK_SPEC = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
BINDING = Path("/srv/bulk/leo-dev/ds30-full-20261121/bindings") / f"{CASE}.json"
LOCAL_PANEL = Path("/tmp/ds30-v2-stage-all-6cdbac")
LOCAL_SAVED = Path("/dev/shm/leo-v3-saved-0316-pair-01")
TLE_CAP = 96 * 1024**2
MAX_SOME_PCT = 60.0
SETTINGS = dict(native_sha=NATIVE_SHA, windows=ISSUED, admitted=ADMITTED, audit_name="saved-0160-worker.json")
PINS = dict(SOURCE_PINS, **{
    "unified_short_bootstrap.py": "025b727d423c0b7b33f5d7036dc0e9bc97ba30fcc07d454599679958e140adca",
    "short_graph_guard.py": "ef145279a8e9930ab4ff0268b0f47256ad89800e91cfb3440babfc485d30ab08",
})
FIX_PINS = PINS | {"joint_publication.py": "2f9c5636d710edb35b038d63b37b46f375c4a2ab390efa90124fd3cc35982d71"}


def assignment():
    panel, decision, rows = (checked(ROSTER / name, pin) for name, pin in ROSTER_PINS.items())
    ids = [row["case"] for row in json.loads(panel)["cases"]]
    pins = json.loads(decision)["pair_sha256"]
    named = {row["case"]: row["decision"] for row in csv.DictReader(StringIO(rows.decode()))
             if row["build"] == "candidate"}
    if len(ids) != 100 or len(set(ids)) != 100 or not set(pins) == set(ids) == set(named):
        raise ValueError("The signed roster and named outcome census differ")
    complete = {}
    for case in ids:
        if named[case] != "complete":
            continue
        pair = json.loads(checked(LOCAL_PANEL / case / "pair.json", pins[case]))
        receipt = pair["runs"]["candidate"]["receipt"]
        if pair["candidate_specification_digest"] != STOCK_SPEC or receipt["decision"] != "complete" or type(receipt["window_count"]) is not int:
            raise ValueError(f"Signed named completion changed for {case}")
        complete[case] = receipt["window_count"]
    eligible = ranked_cases(complete, EXCLUSIONS, 3043, max(complete.values()))
    if len(complete) != 92 or not eligible or eligible[0] != (ISSUED, CASE) or pins[CASE] != PAIR_SHA:
        raise ValueError("The signed roster no longer assigns the frozen case")
    census = sorted((n, case, pins[case]) for case, n in complete.items())
    return dict(assigned=len(ids), complete=len(census), exclusions=EXCLUSIONS, first_three=eligible,
                census_sha256=sha256(json.dumps(census).encode()).hexdigest(), roster_pins=ROSTER_PINS)


def forecast():
    model = json.loads(checked(DATA / MODEL, MODEL_SHA))
    row, = (r for r in json.loads(checked(DATA / "acquisition-throughput.json", STAGES_SHA))["rows"] if r["case"] == CASE)
    proxy = row["stages"][1]
    expected = predictions(model, proxy)
    if (CASE in model["stock_candidate_solve_cpu_s"] or proxy != 12.512649675
            or expected != dict(dense_only_s=4.670439584135788, three_sizes_s=8.106107909431483)):
        raise ValueError("The pre-outcome forecast changed")
    return dict(historical_stock_s=proxy, predicted_solve_cpu_s=expected, model_sha256=MODEL_SHA,
                stages_sha256=STAGES_SHA, inventory=row["inventory_sha256"], historical_stage_elapsed_s=row["stages"])


def pressure():
    return Path("/proc/pressure/io").read_text()


def cold_gate(cache, pressures):
    missing = any(row["resident_pages"] != row["file_pages"] for row in cache)
    some = [dict(part.split("=", 1) for part in sample.splitlines()[0].split()[1:]) for sample in pressures]
    return "blocked" if missing and any(float(value[key]) >= MAX_SOME_PCT for value in some for key in ("avg10", "avg60")) else "admitted"


def observed(files, query, page_size):
    # Original signed snapshot files are deliberate hardlinks. A root-only read
    # prevents Linux from returning fictitious all-resident results for read-only
    # other-owner mappings. The later per-file SHA check still precedes staging.
    result = []
    for path in files:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or not info.st_size:
                raise ValueError(f"Expected a nonempty regular saved file: {path}")
            result.append(dict(path=str(path), bytes=info.st_size, device=info.st_dev, inode=info.st_ino,
                               file_pages=(info.st_size+page_size-1)//page_size,
                               resident_pages=query(descriptor, info.st_size)))
        finally:
            os.close(descriptor)
    return result


def saved_inputs():
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.qualification import paired_publication as pp

    panel = LOCAL_PANEL / CASE
    pair = json.loads(checked(panel / "pair.json", PAIR_SHA))
    before = pair["runs"]["candidate"]
    rec = before["receipt"]
    binding = json.loads(checked(BINDING, BINDING_SHA))
    case = binding["case"]
    manifests = [(Path("/srv/bulk")/row["path"], "sha256:"+row["sha256"]) for row in case["recording"]["segments"]]
    terminal_file = panel / "candidate/fast-scan-automatic-work" / rec["run_id"] / "terminal.json"
    terminal = json.loads(checked(terminal_file, rec["terminal_sha256"]))
    native, = terminal_file.parent.parent.glob("*/detections.json")
    if (terminal["native_sha256"] != "sha256:"+NATIVE_SHA or rec["window_count"] != ISSUED
            or rec["counts"]["processed"] != ADMITTED or pair["candidate_specification"]["detector_sha256"] != DETECTOR
            or case["id"] != CASE or case["raw_authority"] != before["raw_authority"] or case["session_id"] != rec["session_id"]
            or [(str(p), pin) for p, pin in manifests] != [(m["path"], m["sha256"]) for m in pair["cache_observation"]["manifests"]]
            or pair["candidate_specification_digest"] != pp.V3_IDENTITY["frozen_specification"]):
        raise ValueError("Saved original identity differs from the signed named panel")
    archive = Path(pair["archive"]["root"])
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != 52 or sum(ref.byte_size for ref in refs) > TLE_CAP
            or canonical_digest({ref.path.name: ref.sha256 for ref in refs}) != pair["archive"]["snapshots_sha256"]):
        raise ValueError("Causal source metadata is outside its signed snapshot census")
    source_files = {}
    for ref in refs:
        relative = ref.path.relative_to(archive)
        existing = LOCAL_SAVED / "tle" / relative
        source_files[str(relative)] = str(existing if existing.is_file() and existing.stat().st_size == ref.byte_size else ref.path)
    return dict(case=CASE, native=str(native), named_terminal=str(terminal_file), offer=pair["region"],
                original_archive=pair["archive"], archive_sources=source_files, causal_cutoff_utc_ns=binding["orbit_cutoff_ns"],
                recording=pair["recording"], raw_authority=before["raw_authority"], session=rec["session_id"],
                manifests=[[str(p), h] for p, h in manifests], original_pair_sha256=PAIR_SHA,
                detector_sha256=DETECTOR, native_sha256=NATIVE_SHA, offer_sha256=OFFER_SHA), before


def preflight():
    from tools.pipeline_eval.qualification.cache_residency import load_query

    if os.geteuid() != 0:
        raise ValueError("Run the passive observation as a privileged read-only cache observer")
    initial = pressure()
    enrollment = assignment()
    work, _ = saved_inputs()
    checked(CACHE_LIB, CACHE_PIN)
    query, size = load_query(CACHE_LIB), os.sysconf("SC_PAGE_SIZE")
    groups = dict(archive=[Path(path) for path in work["archive_sources"].values()],
                  manifests=[Path(path) for path, _ in work["manifests"]], native=[Path(work["native"])])
    snapshots = {name: observed(files, query, size) for name, files in groups.items()}
    finish = pressure()
    bulk = [r for rows in snapshots.values() for r in rows if Path(r["path"]).is_relative_to("/srv/bulk")]
    return dict(case=CASE, no_waveform=True, admission=cold_gate(bulk, (initial, finish)), forecast=forecast(),
                assignment=enrollment, input_paths=work, page_size=size, cache=snapshots, cache_library_sha256=CACHE_PIN,
                pressures=[initial, finish], protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest())


def stage(root, admission):
    from aperture_trial import write
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore

    request, historical = saved_inputs()
    if request != admission["input_paths"]:
        raise ValueError("The staging set changed after the passive preflight")
    inventory = admission["forecast"]["inventory"]
    session, digest, raw = FastScanStore(root).inventory(Path(request["recording"]), verify_windows=False)
    native_bytes = checked(Path(request["native"]), NATIVE_SHA)
    native = json.loads(native_bytes)
    manifests = [[str(Path(m["path"])/"manifest.json"), m["manifest_digest"]] for m in raw["segments"]]
    if (raw["window_count"] != ISSUED or session != request["session"] or inventory != digest
            or manifests != request["manifests"] or native["source"]["input_manifest_sha256"] != digest
            or native["source"]["raw_recording_authority_digest"] != request["raw_authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["causal_cutoff_utc_ns"]):
        raise ValueError("Saved detector, original manifest order or causal cutoff changed")
    packet, offer, archive = root / "named-detections.json", root / "operator-offer.json", root / "tle"
    packet.write_bytes(native_bytes)
    offer.write_bytes(checked(Path(request["offer"]), OFFER_SHA))
    total = 0
    for name, path in request["archive_sources"].items():
        dest, path = archive / name, Path(path)
        data = checked(path, path.stem.rsplit("-", 1)[1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        total += len(data)
    names = {r.path.name: r.sha256 for r in TleArchiveReader(archive).list_snapshots("space-track")}
    if canonical_digest(names) != request["original_archive"]["snapshots_sha256"] or total > TLE_CAP:
        raise ValueError("Verified tmpfs snapshot roster differs from the original")
    prepared = {}
    for name, (_, pin) in LIBRARIES.items():
        path = root / f"{name}.so"
        path.write_bytes(checked(LOCAL_SAVED / path.name, pin))
        prepared[name] = str(path)
    request.update(inventory=inventory, native_file=str(packet), offer_file=str(offer), local_libraries=prepared,
                   local_archive=dict(root=str(archive), bytes=total, snapshots=len(names)))
    write(root / "request.json", request)
    return request, historical


def evaluation(runs, historical, model):
    from aperture_trial import read
    from dense_full_short_raw import checked as pinned_path
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    stock = runs["stock"]["science"]
    if any(stock[k] != historical[k] for k in ("arms", "owners", "raw_authority", "scientific_digests", "artifacts")):
        raise ValueError("Fresh named publication differs from the signed historical science")
    references = read(pinned_path(REFERENCE, REFERENCE_SHA256))
    ref, = (row["reference"] for row in references["cases"] if row["dataset_label"] == CASE
            and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [ref[key] for key in ("latitude_deg", "longitude_deg")]
    accuracy, rf = {}, {}
    for mode, run in runs.items():
        arms = run["science"]["arms"]
        accuracy[mode] = {a: distance_km(truth, arms[a]["latlon"]) if arms[a]["latlon"] else None for a in ARMS}
        rf[mode] = {a: arms[a].get("rf_rms_hz") for a in ARMS}
    stock, candidate = (runs[mode]["worker"]["solve"]["cpu_s"] for mode in ORDER)
    predicted = model["predicted_solve_cpu_s"]
    fresh_control = predictions(json.loads(checked(DATA / MODEL, MODEL_SHA)), stock)
    figures = runs["stock"]["figures"]
    return dict(horizontal_error_km=accuracy, rf_rms_hz=rf, reference_sha256=REFERENCE_SHA256,
                delta_horizontal_error_km={a: accuracy["cumulative"][a]-accuracy["stock"][a]
                                          if accuracy["cumulative"][a] is not None else None for a in ARMS},
                owners={a: owner_delta(*(runs[mode]["selected_rows"].get(a, []) for mode in ORDER)) for a in ARMS},
                figure_equality={name: {key: figures[name][key] == runs["cumulative"]["figures"].get(name, {}).get(key)
                                        for key in ("sha256", "rgba_sha256", "size")} for name in figures},
                historical_forecast_residual_s={name: candidate-seconds for name, seconds in predicted.items()},
                fresh_stock_solve_cpu_s=stock, candidate_solve_cpu_s=candidate, fresh_stock_predictions_s=fresh_control,
                fresh_stock_prediction_residual_s={name: candidate-seconds for name, seconds in fresh_control.items()})


def run(root, admission_file):
    from aperture_trial import read, RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(checked, PINS)
    admission = read(admission_file)
    if (admission["case"] != CASE or admission["protocol_sha256"] != sha256(PROTOCOL.read_bytes()).hexdigest()
            or admission["forecast"] != forecast()):
        raise ValueError("Passive admission must follow the frozen case protocol")
    now = pressure()
    bulk = [r for rows in admission["cache"].values() for r in rows if Path(r["path"]).is_relative_to("/srv/bulk")]
    if admission["admission"] != "admitted" or cold_gate(bulk, (now,)) == "blocked":
        print("Saved metadata staging blocked by I/O pressure")
        return
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("The paired outputs require fresh tmpfs roots")
    root.mkdir()
    (root / "tmp").mkdir()
    before_blocks = getrusage(RUSAGE_SELF).ru_inblock
    start = process_time(), perf_counter()
    request, historical = stage(root, admission)
    stage_clock = dict(elapsed(start), input_blocks=getrusage(RUSAGE_SELF).ru_inblock-before_blocks,
                       pressure_before=now, pressure_after=pressure())
    write(root / "stage-clock.json", stage_clock)
    env, executable = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([executable, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    clocks = {}
    for mode in ORDER:
        output = root / mode
        command = [executable, "-IB", __file__, "worker", root / "request.json", mode, output]
        clocks[mode] = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=clocks[mode], command=list(map(str, command))))
        if clocks[mode]["exit_code"]:
            raise RuntimeError(f"Saved {mode} worker failed; retain the process receipt")
    runs = {mode: inspect(root / mode, mode, read(root / mode / SETTINGS["audit_name"])["receipt"],
                          clocks[mode], request, **SETTINGS) for mode in ORDER}
    result = dict(case=CASE, no_waveform=True, waveform_calls=0, input=INPUT_DESCRIPTION, research_base=BASE,
                  order=ORDER, machine=machine, protocol_sha256=admission["protocol_sha256"], inputs=request,
                  source_sha256=PINS | {path.name: sha256(path.read_bytes()).hexdigest() for path in
                                        (Path(__file__), HERE/"prospective_0316_solver.py")},
                  preflight_sha256=sha256(admission_file.read_bytes()).hexdigest(), admission=admission,
                  stage=stage_clock, scores=evaluation(runs, historical, admission["forecast"]), runs=runs)
    write(root / "result.json", result)


def audit_published(root, admission_file, output):
    """Verify immutable files from the original process exits without invoking a solver."""
    from aperture_trial import read, write
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification import paired_publication as pp
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    admission, req = read(admission_file), read(root / "request.json")
    clocks = {mode: read(root / f"{mode}-clock.json")["timing"] for mode in ORDER}
    historical = json.loads(checked(LOCAL_PANEL / CASE / "pair.json", PAIR_SHA))["runs"]["candidate"]
    if clocks["stock"]["exit_code"] != 0 or clocks["cumulative"]["exit_code"] != 1:
        raise ValueError("The archived process exits do not match the incomplete comparison")
    ref, = (row["reference"] for row in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
            if row["dataset_label"] == CASE and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    truth = [ref[key] for key in ("latitude_deg", "longitude_deg")]
    score = {}
    for mode in ORDER:
        destination = root / mode
        receipt = historical["receipt"].copy()
        run_id = receipt["run_id"]
        store = FastStandardAnalysisStore(destination)
        detail = store.detail(run_id)
        workspace = FastScanStore(destination).automatic_workspace(run_id, create=False)
        terminal_path = workspace / "terminal.json"
        terminal = read(terminal_path)
        native_path, = workspace.parent.glob("*/detections.json")
        if (sha256(native_path.read_bytes()).hexdigest() != NATIVE_SHA or terminal["native_sha256"] != "sha256:"+NATIVE_SHA
                or detail["raw_authority"] != req["raw_authority"] or detail["session_id"] != req["session"]
                or detail["region"] != receipt["region"] or terminal["orbit_policy"] != "history_support"):
            raise ValueError("Published files do not bind the signed recording or documented orbit support")
        receipt.update(terminal_sha256=detail["terminal_sha256"], decision=detail["state"])
        if receipt["decision"] != "complete":
            raise ValueError("The reported science must match the published complete fix")
        event = clocks[mode]["started_unix_ns"]
        science = pp.evidence(destination, receipt, event, read_only=True)
        if mode == "stock" and any(science[k] != historical[k]
                                   for k in ("arms", "owners", "raw_authority", "scientific_digests", "artifacts")):
            raise ValueError("Named replay does not reproduce the historical signed evidence")
        figures = artifacts(destination, receipt)["images"]
        grid, path = store.position_grid(run_id), store.position_path(run_id)
        if (grid["evaluated_points"] != 179 or not grid["complete"] or len(figures) != 8
                or any(doc["binding"]["position_png_sha256"] != figures["position"]["sha256"] for doc in (grid, path))):
            raise ValueError("Published grid, path or figure binding is incomplete")
        audit_file = destination / SETTINGS["audit_name"]
        authenticated = read(audit_file) if audit_file.is_file() else None
        score[mode] = dict(process=clocks[mode], worker=authenticated, terminal=terminal, science=science, pngs=figures,
                           candidate_route_available=(destination / "joint-research-receipt.json").is_file(),
                           associated={arm: detail["arms"][arm]["associated_points"] for arm in ARMS},
                           scopes=dict(launch_to_native_mtime_s=(native_path.stat().st_mtime_ns-event)/1e9,
                                       native_to_terminal_mtime_s=(terminal_path.stat().st_mtime_ns-native_path.stat().st_mtime_ns)/1e9),
                           horizontal_error_km={a: distance_km(truth, terminal["arms"][a]["latlon"]) for a in ARMS},
                           rf_rms_hz={a: terminal["arms"][a]["rf_rms_hz"] for a in ARMS},
                           sidecars=dict(grid=canonical_digest(grid), path=canonical_digest(path),
                                         position_png_sha256=figures["position"]["sha256"]))
    stock, candidate = (score[mode] for mode in ORDER)
    if candidate["candidate_route_available"] or candidate["worker"] is not None:
        raise ValueError("The candidate exit must retain the missing route/solve receipt limitation")
    png_equality = {name: {key: item[key] == candidate["pngs"][name][key] for key in ("sha256", "rgba_sha256", "size")}
                    for name, item in stock["pngs"].items()}
    write(output, dict(case=CASE, status="candidate_verifier_failed_after_publication", no_waveform=True, waveform_calls=0,
                       original_inputs=req, admission=admission, stage=read(root / "stage-clock.json"),
                       reference_sha256=REFERENCE_SHA256, runs=score, identical_png_fields=png_equality,
                       candidate_owner_rows_available=False, candidate_numerical_solve_cpu_available=False))


def confirm(first_root, audit_file, destination):
    from aperture_trial import read, RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(checked, FIX_PINS)
    request_file = first_root / "request.json"
    request, audit = read(request_file), read(audit_file)
    if (audit["case"] != CASE or request != audit["original_inputs"]
            or audit["runs"]["cumulative"]["process"]["exit_code"] != 1):
        raise ValueError("Verification requires the preserved original candidate exit and scientific audit")
    inventory = first_root / "stock/fast-scan-inputs" / f"{request['session']}.json"
    paths = [inventory, Path(request["native_file"]), Path(request["offer_file"]), Path(request["local_archive"]["root"]),
             *(Path(path) for path in request["local_libraries"].values())]
    if any(not path.resolve(strict=True).is_relative_to(first_root) for path in paths):
        raise ValueError("Verification may use only the previously staged saved inputs")
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", destination.parent], text=True).strip() != "tmpfs":
        raise ValueError("Verification output must use a fresh tmpfs root")
    destination.mkdir()
    (destination / "tmp").mkdir()
    env = environment(first_root)
    env["TMPDIR"] = str(destination / "tmp")
    output = destination / "cumulative"
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "worker", request_file, "cumulative", output,
               "--staged-inventory", inventory]
    clock = measure(command, env, output)
    write(destination / "cumulative-clock.json", dict(timing=clock, command=list(map(str, command))))
    if clock["exit_code"]:
        raise RuntimeError("Corrected candidate worker failed; its process exit is sealed")
    own = read(output / SETTINGS["audit_name"])
    checked_run = inspect(output, "cumulative", own["receipt"], clock, request, **SETTINGS)
    research = read(output / "joint-research-receipt.json")
    original = audit["runs"]["cumulative"]
    numerical = ("arms", "owners", "raw_authority", "scientific_digests", "artifacts")
    if (not research.get("recovered_inference") or research["recovered_inference"]["orbit_policy"] != "history_support"
            or any(checked_run["science"][key] != original["science"][key] for key in numerical)
            or checked_run["figures"] != original["pngs"] or checked_run["terminal"] != original["terminal"]):
        raise ValueError("Corrected candidate must audit the history retry and reproduce the first published science")
    stock_rows = read(first_root / "stock/joint-research-receipt.json")["selected_rows"]
    stock_cpu = audit["runs"]["stock"]["worker"]["solve"]["cpu_s"]
    solve_cpu = own["solve"]["cpu_s"]
    prior = audit["admission"]["forecast"]["predicted_solve_cpu_s"]
    write(destination / "result.json", dict(case=CASE, first_audit_sha256=sha256(audit_file.read_bytes()).hexdigest(),
          corrected_source=FIX_PINS, machine=machine, waveform_calls=0, input_staged=True, original_clock=original["process"],
          candidate=checked_run, recovered_inference=research["recovered_inference"], reproduced_first_publication=True,
          original_stock_solve_cpu_s=stock_cpu, candidate_solve_cpu_s=solve_cpu,
          candidate_minus_frozen_forecast_s={name: solve_cpu-seconds for name, seconds in prior.items()},
          owners={arm: owner_delta(stock_rows[arm], checked_run["selected_rows"][arm]) for arm in ARMS}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_subparsers(dest="operation", required=True)
    modes.add_parser("preflight")
    pair = modes.add_parser("pair")
    pair.add_argument("root", type=Path)
    pair.add_argument("preflight", type=Path)
    job = modes.add_parser("worker")
    job.add_argument("request", type=Path)
    job.add_argument("mode", choices=ORDER)
    job.add_argument("output", type=Path)
    job.add_argument("--staged-inventory", type=Path)
    audit = modes.add_parser("audit")
    audit.add_argument("root", type=Path)
    audit.add_argument("preflight", type=Path)
    audit.add_argument("output", type=Path)
    corrected = modes.add_parser("confirm")
    corrected.add_argument("root", type=Path)
    corrected.add_argument("audit", type=Path)
    corrected.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.operation == "preflight":
        print(json.dumps(preflight(), indent=2, allow_nan=False))
    elif args.operation == "pair":
        run(args.root, args.preflight)
    elif args.operation == "audit":
        audit_published(args.root, args.preflight, args.output)
    elif args.operation == "confirm":
        confirm(args.root, args.audit, args.output)
    else:
        pins = FIX_PINS if args.staged_inventory else PINS
        worker(args.request, args.mode, args.output, source_pins=pins, inventory_file=args.staged_inventory, **SETTINGS)
