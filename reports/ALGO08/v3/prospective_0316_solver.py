"""Compare current and named v3 solvers on one authenticated full-aperture packet."""

import argparse
from contextlib import nullcontext
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
BASE = "06ece133e"
CASE = "DS30-0316"
ORDER = ("stock", "cumulative")
ARMS = ("c0", "fitted_c")
NATIVE_SHA = "6bbbb2575df6a203dd0d183a3ad8390110fbac778504803e275b7493b8422bed"
DETECTOR = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
PAIR_SHA = "334790daefa5a26511aa72328ecd2dc3124a92c826257df9019f8afa793415ed"
SIGNED_SHA = "548e80975fe5a991bb58dd020fb936681200c6a6f3418cf9c22e941f8ccc6636"
TRANSFER_SHA = "9ada781c4cd94272c134c9ea9794cfd59ff7bf79efdaba48bf1b3ecfa6cfe52c"
PAIR_ROOT = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications") / CASE
NATIVE_PATH = PAIR_ROOT / "candidate/fast-scan-automatic-work/algo08-v2-f3811e529be84ffd1a4e0a25474cf58d/detections.json"
INPUT_DESCRIPTION = "authenticated saved full-20 ms named ALGO08v3 detections"
SOURCE_PINS = {
    "unified_short_bootstrap.py": "abf3a08289e795a0a4fbe6c539038f4af7c070f45ca4a9ae60c68e484952ff9a",
    "empty_bootstrap.py": "2d789b4fb28447a623f6118bb53a2b734645a9bbedb7a263007f52f4acc429a0",
    "joint_publication.py": "faf50abb5fc444e4f4479ec627a21d5291a407ef2dd5bdb1a6215e80b136f729",
    "exact_graph_execution.py": "cee1c8e095f139d4e1b839dc84a3c25b96794a96031df05a16f7f876a67391fe",
    "one_pass_web_png.py": "0be5c8a2f90d36691d1bb20a1e3dee0fe17eae7a70b66b732a560cf0257c88aa",
    "prepared_exterior.py": "f964e5ee81b97f58efc7afe06119c1606f402b2ecbf8b61b12fe6d9af1b95064",
    "grid_phase_state_reuse.py": "00cb3d9135835301f47afb455dad2669f543cdfa83a3579864e2903e18260170",
    "cold_finalist_race.py": "eeb7d1041f34fb7dbb805cb12eb93f66eba87e729e9cf695ff77811b51842fe7",
}
REGIONALS = Path("/srv/bulk/leo-dev/regional-probe-block-20261123")
LIBRARIES = {
    "geographic_library": (Path("/var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so"), "b8c8e0bb22e62fc69585909f193c76ab22ab4f2892d7fcbedd2cc31c78c573ee"),
    "regional_track_library": (REGIONALS / "scores.so", "5e96851c0f9c479dbb176eeb3f2ba143c461d590a9b35b00fb5c1d7ce984d098"),
    "frontier_block_library": (REGIONALS / "block.so", "adfbfca33caee3c6b337ddf401db1112e525867e451ad010eb30cb65965ce042"),
}


def denied(*args, **kwargs):
    raise RuntimeError("This saved-only publication cannot open a waveform reader or run a detector")


def owner_delta(stock, candidate):
    before = {identifier: (norad, role) for identifier, norad, role in stock}
    after = {identifier: (norad, role) for identifier, norad, role in candidate}
    if len(before) != len(stock) or len(after) != len(candidate):
        raise ValueError("Published ownership has duplicate observation IDs")
    shared = before.keys() & after.keys()
    changes = [[key, *before[key], *after[key]] for key in sorted(shared) if before[key] != after[key]]
    return dict(stock=len(before), candidate=len(after), shared=len(shared), identical_ordered_rows=stock == candidate,
                reassigned_norad=sum(old != new for _, old, _, new, _ in changes),
                changed_roles=sum(old != new for _, _, old, _, new in changes),
                dropped=sorted(before.keys()-after.keys()), added=sorted(after.keys()-before.keys()), changed=changes)


def elapsed(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def verify_sources(checked, source_pins=SOURCE_PINS):
    for name, pin in source_pins.items():
        checked(HERE / name, pin)


def saved_inventory(request, path):
    from leo.contracts.digests import canonical_digest

    inventory = json.loads(path.read_bytes())
    digest = canonical_digest(inventory)
    session = "fast-" + digest.removeprefix("sha256:")[:32]
    recording = Path(request["recording"])
    manifests = [[str(Path(row["path"]) / "manifest.json"), row["manifest_digest"]] for row in inventory["segments"]]
    if (digest != request["inventory"] or session != request["session"] or inventory["recording_name"] != recording.name
            or manifests != request["manifests"]):
        raise ValueError("The saved inventory must bind to the original path and manifest order")

    def inventory_only(_store, path, *, verify_windows=True):
        if verify_windows or Path(path) != recording:
            raise ValueError("Saved inventory cannot authorize waveform access or another recording")
        return session, digest, inventory

    return inventory_only


def worker(job, mode, output, *, source_pins=SOURCE_PINS, native_sha=NATIVE_SHA,
           windows=3042, admitted=2702, audit_name="saved-0316-worker.json", inventory_file=None,
           detector=DETECTOR, input_description=INPUT_DESCRIPTION):
    begin = process_time(), perf_counter()
    import empty_bootstrap as staged
    import unified_short_bootstrap as cumulative

    verify_sources(staged.checked, source_pins)
    _, specification, _, publication, checks = staged.load_runtime()
    from aperture_trial import read, write
    import joint_publication as joint
    from leo.storage.fast_scan import FastSegmentSource, FastScanStore
    from leo.storage.short_window import ShortWindowReader
    from short_graph_guard import prove

    req = read(job)
    packet = Path(req["native_file"])
    offer = Path(req["offer_file"])
    native = json.loads(staged.checked(packet, native_sha))
    source = native["source"]
    recording = Path(req["recording"])
    inventory_scope = (nullcontext() if inventory_file is None else
                       patch.object(FastScanStore, "inventory", saved_inventory(req, inventory_file)))
    with inventory_scope:
        session, inventory, original = FastScanStore(output).inventory(recording, verify_windows=False)
    if (specification["detector_sha256"] != DETECTOR or req["inventory"] != inventory or req["session"] != session
            or original["window_count"] != windows or native["provenance"]["processed_windows"] != admitted
            or source["raw_recording_authority_digest"] != req["raw_authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != req["causal_cutoff_utc_ns"]):
        raise ValueError("The original named detector, authority or causal epoch changed")
    staged.checked(offer, req["offer_sha256"])
    staged.bind_native(native, session, inventory, detector, expected="sha256:"+native_sha)
    layout, graph, proof = {}, {}, None
    opts = SimpleNamespace(recording=recording, archive=Path(req["local_archive"]["root"]), region=offer,
                           output=output, one_pass_web_png=True, exact_graph_reuse=True,
                           **{name: Path(path) for name, path in req["local_libraries"].items()})
    handoff = cumulative.Handoff(session, inventory, detector, native)
    # The sentinel ensures the saved input label in the normal research receipt
    # describes the actual boundary; invoking it would also abort this worker.
    run_saved = partial(joint.run, detector_override=denied, detector_description=input_description)
    with (inventory_scope, patch.object(FastSegmentSource, "windows", denied), patch.object(ShortWindowReader, "windows", denied),
          patch.object(joint, "configuration", return_value=(publication, dict(specification, startup="stock")))):
        if mode == "stock":
            options = SimpleNamespace(**vars(opts), stock_control=True, saved=None, saved_digest=None, verify_images=True)
            result = run_saved(options, raw_context=handoff.install, keep_selected_rows=True)
        else:
            proof = prove(native, staged.RELEASE / "assets")
            if proof.get("proven") or not proof.get("winning_rows"):
                raise ValueError("The authenticated complete named packet should reach the active solver")
            with patch.object(joint, "run", run_saved):
                _, result = cumulative.publish_active(opts, publication, specification, handoff, layout, graph_audit=graph)
    if handoff.calls != 1 or result["input"] != input_description:
        raise ValueError("The normal acquisition boundary did not consume its authenticated saved packet once")
    write(output / audit_name, dict(mode=mode, complete_saved=elapsed(begin), no_waveform=True,
          handoffs=handoff.calls, detector=detector, native_sha256=native_sha, graph=graph, layout=layout,
          startup_source_checks=checks, graph_proof=proof, solve=result["solve"], receipt=result["receipt"]))
    print(json.dumps(result["receipt"], allow_nan=False))


def stage_archive(origin, target, expected):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from empty_bootstrap import checked

    refs = TleArchiveReader(origin).list_snapshots("space-track")
    names = {ref.path.name: ref.sha256 for ref in refs}
    if (canonical_digest(names) != expected or len(refs) != 46 or sum(ref.path.stat().st_size for ref in refs) > 96*1024**2):
        raise ValueError("The original pre-RF TLE archive differs from its bounded signed census")
    copied = 0
    for ref in refs:
        data = checked(ref.path, ref.sha256.removeprefix("sha256:"))
        path = target / ref.path.relative_to(origin)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        copied += len(data)
    staged = TleArchiveReader(target).list_snapshots("space-track")
    if {ref.path.name: ref.sha256 for ref in staged} != names:
        raise ValueError("Verified TLE copy altered the lookup archive")
    return dict(root=str(target), snapshots_sha256=expected, snapshots=len(names), bytes=copied)


def stage(root):
    from aperture_trial import write
    from empty_bootstrap import checked
    from leo.storage.fast_scan import FastScanStore
    from prospective_small_physical import BINDING_PIN, CASE_BINDING, OFFER_PIN

    pair = json.loads(checked(PAIR_ROOT / "pair.json", PAIR_SHA))
    before = pair["runs"]["candidate"]
    previous = json.loads(checked(CASE_BINDING, BINDING_PIN))
    native_data = checked(NATIVE_PATH, NATIVE_SHA)
    native = json.loads(native_data)
    offer = checked(Path(pair["region"]), OFFER_PIN)
    actual_source = native["source"]
    session, inventory, metadata = FastScanStore(root).inventory(Path(pair["recording"]), verify_windows=False)
    bound = previous["case"]
    cutoff = native["clock_anchor"]["before"]["realtime_ns"]
    if (metadata["window_count"] != 3042 or session != before["receipt"]["session_id"] or session != bound["session_id"]
            or actual_source["raw_recording_authority_digest"] != before["raw_authority"]
            or actual_source["raw_recording_authority_digest"] != bound["raw_authority"]
            or actual_source["input_manifest_sha256"] != inventory or previous["orbit_cutoff_ns"] != cutoff
            or before["receipt"]["decision"] != "complete" or native["provenance"]["processed_windows"] != 2702):
        raise ValueError("The named input, its original authorized archive or 25 km offer changed")
    observed = [(m["path"], m["manifest_digest"]) for m in metadata["segments"]]
    if observed != [(str((Path("/srv/bulk")/m["path"]).parent), "sha256:"+m["sha256"])
                    for m in bound["recording"]["segments"]]:
        raise ValueError("The signed published manifest ordering changed")
    packet_file, offer_file = root / "named-detections.json", root / "operator-offer.json"
    packet_file.write_bytes(native_data)
    offer_file.write_bytes(offer)
    archive = stage_archive(Path(pair["archive"]["root"]), root / "tle", pair["archive"]["snapshots_sha256"])
    library_paths = {}
    for name, (file, pin) in LIBRARIES.items():
        out = root / f"{name}.so"
        out.write_bytes(checked(file, pin))
        library_paths[name] = str(out)
    req = dict(case=CASE, session=session, inventory=inventory, raw_authority=before["raw_authority"],
               original_archive=pair["archive"], local_archive=archive, causal_cutoff_utc_ns=cutoff,
               recording=pair["recording"], native_file=str(packet_file), offer_file=str(offer_file),
               offer_sha256=OFFER_PIN, local_libraries=library_paths, original_pair_sha256=PAIR_SHA,
               detector_sha256=DETECTOR, native_sha256=NATIVE_SHA, manifests=observed)
    write(root / "request.json", req)
    return req, before


def inspect(root, mode, receipt, clock, req, *, native_sha=NATIVE_SHA, windows=3042,
            admitted=2702, audit_name="saved-0316-worker.json", detector=DETECTOR,
            input_description=INPUT_DESCRIPTION):
    from aperture_trial import read
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification import paired_publication as pp

    science = pp.evidence(root, receipt, clock["started_unix_ns"], read_only=True)
    research = read(root / "joint-research-receipt.json")
    own = read(root / audit_name)
    work = FastScanStore(root).automatic_workspace(receipt["run_id"], create=False)
    terminal = read(work / "terminal.json")
    native, = work.parent.glob("*/detections.json")
    figures = artifacts(root, receipt)["images"]
    if (sha256(native.read_bytes()).hexdigest() != native_sha or own["detector"] != detector
            or terminal["native_sha256"] != "sha256:"+native_sha or science["raw_authority"] != req["raw_authority"]
            or receipt["window_count"] != windows or receipt["counts"]["processed"] != admitted
            or receipt["session_id"] != req["session"] or not own["no_waveform"] or own["handoffs"] != 1
            or research["input"] != input_description):
        raise ValueError(f"{mode} publication changed the native packet or its original authority")
    documents = {}
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(root)
        grid = store.position_grid(receipt["run_id"])
        if not grid["complete"] or grid["evaluated_points"] != 179 or len(figures) != 8:
            raise ValueError("Complete publication must contain its original numerical grid and eight images")
        for name, body in (("grid", grid), ("path", store.position_path(receipt["run_id"]))):
            position = body["binding"]["position_png_sha256"]
            if position != figures["position"]["sha256"]:
                raise ValueError(f"The {mode} {name} sidecar does not bind its verified position PNG")
            documents[name] = dict(position_png_sha256=position, scientific_sha256=canonical_digest(
                {k: v for k, v in body.items() if k not in ("binding", "elapsed_seconds")}))
    elif figures or not terminal["reason"] or any(terminal["arms"][arm]["latlon"] is not None for arm in ARMS):
        raise ValueError("Withholding requires its reason and no figures or position")
    return dict(process=clock, worker=own, science=science, figures=figures, sidecars=documents,
                terminal=terminal, selected_rows=research["selected_rows"], route=research["route"],
                route_details=research.get("route_details"), regional=research.get("early_regional"))


def score(result, historical):
    from aperture_trial import read
    from dense_full_short_raw import checked
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    refs = read(checked(REFERENCE, REFERENCE_SHA256))
    ref, = (r for r in refs["cases"] if r["dataset_label"] == CASE and r["authority_eligible"]
            and r["sealed_metadata_digests_verified"])
    truth = [ref["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    named = result["stock"]["science"]
    if any(named[k] != historical[k] for k in ("arms", "owners", "raw_authority", "scientific_digests")):
        raise ValueError("The new installed numerical replay differs from its original named science")
    signed = read(checked(HERE / "measurements/signed-short-DS30-0316.json", SIGNED_SHA))
    if signed["original_pair_sha256"] != PAIR_SHA or signed["saved_native_sha256"] != "sha256:"+NATIVE_SHA:
        raise ValueError("The earlier signed solver uses a different receiver input")
    reference = read(checked(HERE / "measurements/solver-transfer-budget.json", TRANSFER_SHA))
    dense_stock, dense_original = reference["stock_candidate_solve_cpu_s"]["DS30-0008"]
    dense_exact = reference["dense_reused_cpu_s"]
    errors, rms = {}, {}
    for mode in ORDER:
        arms = result[mode]["science"]["arms"]
        errors[mode] = {arm: distance_km(truth, arms[arm]["latlon"]) if arms[arm]["latlon"] else None for arm in ARMS}
        rms[mode] = {arm: arms[arm].get("rf_rms_hz") for arm in ARMS}
    stock, candidate = (result[m]["worker"]["solve"]["cpu_s"] for m in ORDER)
    predictions = {tag: dict(dense_ratio=n/dense_stock, predicted_cpu_s=stock*n/dense_stock,
                             measured_minus_prediction_s=candidate-stock*n/dense_stock)
                   for tag, n in (("dense_original_graph", dense_original), ("dense_exact_graph", dense_exact))}
    return dict(reference_sha256=REFERENCE_SHA256, horizontal_error_km=errors, rf_rms_hz=rms,
                delta_horizontal_error_km={a: None if errors["cumulative"][a] is None else errors["cumulative"][a]-errors["stock"][a] for a in ARMS},
                measured_numerical_cpu_ratio=candidate/stock, dense_proportional=predictions,
                signed_previous={k: signed[k] for k in ("horizontal_error_km", "rf_rms_hz", "owner_changes", "runs")},
                owners={a: owner_delta(*(result[m]["selected_rows"].get(a, []) for m in ORDER)) for a in ARMS})


def run(root):
    from aperture_trial import read, RELEASE, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    verify_sources(checked)
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("The pair needs fresh tmpfs roots")
    root.mkdir()
    (root / "tmp").mkdir()
    stage_start = process_time(), perf_counter()
    req, historical = stage(root)
    stage_clock = elapsed(stage_start)
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    clocks = {}
    for mode in ORDER:
        output = root / mode
        command = [python, "-IB", __file__, "worker", root / "request.json", mode, output]
        clocks[mode] = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=clocks[mode], command=list(map(str, command))))
    if any(row["exit_code"] for row in clocks.values()):
        raise RuntimeError("A saved worker failed; the immediate process receipts remain available")
    result = {mode: inspect(root / mode, mode, read(root / mode / "saved-0316-worker.json")["receipt"], clocks[mode], req)
              for mode in ORDER}
    evaluation = score(result, historical)
    figures_equal = {name: {key: all(r["figures"].get(name, {}).get(key) == result["stock"]["figures"][name][key]
                                    for r in result.values()) for key in ("sha256", "rgba_sha256", "size")}
                     for name in result["stock"]["figures"]}
    write(root / "result.json", dict(case=CASE, waveform_calls=0, raw_admission="closed", input=INPUT_DESCRIPTION,
          machine=machine, sources=SOURCE_PINS, protocol_sha256=sha256((HERE / "prospective-0316-solver-protocol.md").read_bytes()).hexdigest(),
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), research_base=BASE, inputs=req,
          staged=stage_clock, order=ORDER, scores=evaluation, runs=result, paired_figure_equality=figures_equal))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cli = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        cli.add_argument("job", type=Path)
        cli.add_argument("mode", choices=ORDER)
        cli.add_argument("output", type=Path)
        worker(**vars(cli.parse_args(sys.argv[2:])))
    else:
        cli.add_argument("root", type=Path)
        run(cli.parse_args().root)
