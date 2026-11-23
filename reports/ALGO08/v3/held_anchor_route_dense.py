"""Run the prospective single dense saved held-anchor publication."""

import argparse
from functools import partial
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
RAW = Path("/var/tmp/leo-full-short-dense-DS30-0008")
RAW_PIN = "1425cca32530cf5ecf22ba9cfb99c79a8aac39dc9a0232202270552968c49ac7"
NATIVE_PIN = "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
RECIPE_PIN = "a86307c85d8405fd9c4a14b4bd09066f924016c82922b02b65d05557a6dc89bb"
ARCHIVED_PUBLICATION_PIN = "f335120b34ddc8775a55fee321a28826c7bbecfadf6fb16f2efcf335473e387d"
ANCHOR_OUTCOMES_PIN = "b7585cb260661e4424d8be3d4eea0263f52f01ef2ad48e2f1719a037462419f3"
MEDIUM_SHA = "c886afae2bc5ef5e5a63b01ac2577fa56127878c408cb698be4c1e6e1fd58ab5"
CONTROLS_PIN = "c36abe2ba57fc140e2c75fb331192afbc31cc31dc9820d2c64add8304bed6e3f"
INPUT_LABEL = "authenticated saved 20/12 ms packet chosen by frozen held anchors"


def denied(*args, **kwargs):
    raise RuntimeError("The sealed saved-only branch never reads waveform bytes or runs a detector")


def stage_archive(root, target, expected):
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    refs = TleArchiveReader(root).list_snapshots("space-track")
    pins = {row.path.name: row.sha256 for row in refs}
    if (canonical_digest(pins) != expected or len(refs) != 47
            or sum(row.path.stat().st_size for row in refs) > 96*1024**2):
        raise ValueError("The dense causal archive differs from the original assignment")
    size = 0
    for row in refs:
        data = checked(row.path, row.sha256.removeprefix("sha256:"))
        out = target / row.path.relative_to(root)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        size += len(data)
    return dict(root=str(target), snapshots_sha256=expected, records=len(refs), bytes=size)


def stage(root, medium):
    from aperture_trial import write
    from empty_bootstrap import checked
    from held_anchor_route_controls import verified_original
    from held_anchor_route_publication import prepare
    from leo.storage.fast_scan import FastScanStore, immutable_json
    from prospective_0316_solver import LIBRARIES

    controls = json.loads(checked(HERE / "measurements/held-anchor-route-controls.json", CONTROLS_PIN))["controls"]
    released = json.loads(checked(medium, MEDIUM_SHA))
    intermediate = released["cases"]["DS30-0057"]
    if (intermediate["route"] != "unfiltered" or not all(row["previous_chosen_verified"] for row in controls.values())):
        raise ValueError("The prospective dense fit needs the independent frozen medium and packet controls")
    binding = json.loads(checked(RAW / "binding.json", RAW_PIN))
    original_file, original, recipe = verified_original(RAW / "publication", NATIVE_PIN, RECIPE_PIN)
    launch = binding["command"]
    recording = Path(launch[launch.index("--recording")+1])
    session, inventory, index = FastScanStore(root).inventory(recording, verify_windows=False)
    source = original["source"]
    if (source["session_id"] != session or source["input_manifest_sha256"] != inventory
            or binding["inventory"] != inventory or binding["authority"] != source["raw_recording_authority_digest"]
            or index["window_count"] != 6772):
        raise ValueError("Expected the original signed dense recording")
    decision_file = root / "route-decision.json"
    selected, _, detector, decision = prepare(original, recipe, session, inventory, decision_file)
    original_path, selected_path = root / "original-detections.json", root / "selected-detections.json"
    original_path.write_bytes(checked(original_file, NATIVE_PIN))
    immutable_json(selected_path, selected)
    checked(selected_path, decision["selected_native_sha256"].removeprefix("sha256:"))
    region = root / "operator-offer.json"
    region.write_bytes(checked(Path(binding["region"]), binding["region_sha256"]))
    archive = stage_archive(Path(binding["archive"]["root"]), root / "tle", binding["archive"]["snapshots_sha256"])
    libraries = {}
    for name, (path, digest) in LIBRARIES.items():
        target = root / f"{name}.so"
        target.write_bytes(checked(path, digest))
        libraries[name] = str(target)
    request = dict(recording=str(recording), session=session, inventory=inventory, authority=binding["authority"],
                   offer=str(region), offer_sha256=binding["region_sha256"], archive=archive, libraries=libraries,
                   cutoff_utc_ns=original["clock_anchor"]["before"]["realtime_ns"],
                   original=dict(file=str(original_path), native_sha256="sha256:"+NATIVE_PIN,
                                 detector=original["provenance"]["detector_sha256"][7:]),
                   selected=dict(file=str(selected_path), native_sha256=decision["selected_native_sha256"], detector=detector),
                   medium_sha256=MEDIUM_SHA, controls_sha256=CONTROLS_PIN,
                   selection_sha256=sha256(decision_file.read_bytes()).hexdigest())
    write(root / "request.json", request)
    return request, decision


def worker(request, arm, output):
    import empty_bootstrap as staged
    import unified_short_bootstrap as unified

    from aperture_trial import read, write

    _, specification, _, publication, _ = staged.load_runtime()
    import joint_publication as joint
    from leo.storage.fast_scan import FastSegmentSource, FastScanStore
    from leo.storage.short_window import ShortWindowReader

    req = read(request)
    chosen = req[arm]
    native = json.loads(staged.checked(Path(chosen["file"]), chosen["native_sha256"][7:]))
    session, inventory, original = FastScanStore(output).inventory(Path(req["recording"]), verify_windows=False)
    if (session, inventory, original["window_count"]) != (req["session"], req["inventory"], 6772):
        raise ValueError("The publication must consume the original sealed inventory")
    if (native["source"]["raw_recording_authority_digest"] != req["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != req["cutoff_utc_ns"]):
        raise ValueError("The chosen signed detector differs from the original causal capture")
    staged.bind_native(native, session, inventory, chosen["detector"], expected=chosen["native_sha256"])
    staged.checked(Path(req["offer"]), req["offer_sha256"])
    handoff = unified.Handoff(session, inventory, chosen["detector"], native)
    graph, layout = {}, {}
    args = SimpleNamespace(recording=Path(req["recording"]), archive=Path(req["archive"]["root"]),
                           region=Path(req["offer"]), output=output, one_pass_web_png=True,
                           exact_graph_reuse=False, **{k: Path(v) for k, v in req["libraries"].items()})
    label = INPUT_LABEL if arm == "selected" else "authenticated saved original unfiltered 20/12 ms control"
    selected = partial(joint.run, detector_override=denied, detector_description=label)
    with (patch.object(joint, "run", selected), patch.object(FastSegmentSource, "windows", denied),
          patch.object(ShortWindowReader, "windows", denied)):
        receipt, research = unified.publish_active(args, publication, specification, handoff, layout, graph_audit=graph)
    if handoff.calls != 1 or research["input"] != label:
        raise ValueError("There must be exactly one authenticated selected handoff")
    write(output / "held-anchor-worker.json", dict(receipt=receipt, graph=graph, layout=layout, input=label,
          solve=research["solve"], detector=chosen["detector"], native_sha256=chosen["native_sha256"],
          handoffs=handoff.calls, waveform_calls=0))


def evidence(output, arm, timings, request):
    from aperture_trial import read
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from tools.pipeline_eval.qualification.paired_publication import evidence as verify

    trial = read(output / "joint-research-receipt.json")
    worker_row = read(output / "held-anchor-worker.json")
    receipt = trial["receipt"]
    observed = verify(output, receipt, timings["started_unix_ns"], read_only=True)
    images = artifacts(output, receipt)["images"]
    if ("sha256:"+sha256(native_packet(output).read_bytes()).hexdigest() != request[arm]["native_sha256"]
            or observed["raw_authority"] != request["authority"] or worker_row["waveform_calls"]
            or worker_row["handoffs"] != 1 or worker_row["graph"]["enabled"]):
        raise ValueError("The published receiver, raw authority and ordinary graph must match the assigned route")
    sidecars = {}
    if receipt["decision"] == "complete":
        store, run = FastStandardAnalysisStore(output), receipt["run_id"]
        grid, path = store.position_grid(run), store.position_path(run)
        if len(images) != 8 or not grid["complete"] or grid["evaluated_points"] != 179:
            raise ValueError("The selected fix must publish the complete 179-point grid and eight verified PNGs")
        for name, item in (("grid", grid), ("path", path)):
            image = item["binding"]["position_png_sha256"]
            if image != images["position"]["sha256"]:
                raise ValueError(f"The selected {name} does not bind its own verified PNG")
            sidecars[name] = image
    elif images or not observed["reason"] or any(a["latlon"] is not None for a in observed["arms"].values()):
        raise ValueError("An actual withheld decision must have no figures or positions")
    return dict(process=timings, science=observed, images=images, sidecars=sidecars, worker=worker_row,
                sources=trial["source_sha256"], owner_rows=trial.get("selected_rows", {}), regional=trial.get("early_regional"))


def evaluate(results, decision):
    from empty_bootstrap import checked
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    earlier = gzip.decompress((HERE / "measurements/cumulative-dense-graph-DS30-0008.json.gz").read_bytes())
    if sha256(earlier).hexdigest() != ARCHIVED_PUBLICATION_PIN:
        raise ValueError("The archived ordinary-Graph unfiltered publication changed")
    archived = json.loads(earlier)["runs"]["installed"]
    original = results.get("original", results["selected"])
    selected = results["selected"]
    same_science = {key: original["science"][key] == archived["science"][key]
                    for key in ("arms", "owners", "scientific_digests")}
    same_images = json.loads(json.dumps(original["images"])) == archived["images"]
    differing = sorted(name for name, pin in original["sources"].items()
                       if archived["worker"]["sources"].get(name) != pin)
    refs = json.loads(checked(REFERENCE, REFERENCE_SHA256))
    ref, = (r for r in refs["cases"] if r["dataset_label"] == "DS30-0008" and r["authority_eligible"]
            and r["sealed_metadata_digests_verified"])
    truth = [ref["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    errors = {name: {key: distance_km(truth, arm["latlon"]) if arm["latlon"] else None
                     for key, arm in packet["science"]["arms"].items()}
              for name, packet in (("unfiltered", original), ("selected", selected))}
    historical = json.loads(checked(HERE / "measurements/anchor-route-selector.json", ANCHOR_OUTCOMES_PIN))
    return dict(errors=errors, archived_unfiltered_same_science=same_science, archived_unfiltered_same_images=same_images,
                differing_historical_sources=differing, historical_unfiltered_process=archived["clock"],
                historical_unfiltered_solve=archived["worker"]["solve"], reference_sha256=REFERENCE_SHA256,
                historical_south=historical["containing"]["south"], historical_omissions=historical["missing"],
                historical_named_dense_errors=historical["containing"]["DS30-0008"].get("installed_error_km"),
                paired_fresh_routes=len(results), selected_route=decision["choice"]["route"],
                owners={arm: owner_delta(original["owner_rows"].get(arm, []), selected["owner_rows"].get(arm, []))
                        for arm in ("c0", "fitted_c")})


def run(root, medium):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use one private tmpfs saved publication root")
    root.mkdir()
    (root / "tmp").mkdir()
    begin = process_time(), perf_counter()
    request, decision = stage(root, medium)
    staging = dict(cpu_s=process_time()-begin[0], elapsed_s=perf_counter()-begin[1])
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    arms = ("original", "selected") if decision["choice"]["route"] == "history" else ("selected",)
    clocks = {}
    for arm in arms:
        command = [python, "-IB", __file__, "worker", root / "request.json", arm, root / arm]
        timers = measure(command, env, root / arm)
        write(root / f"{arm}-clock.json", dict(timing=timers, command=list(map(str, command))))
        clocks[arm] = timers
    if any(row["exit_code"] for row in clocks.values()):
        raise ValueError("The attempted saved worker clocks are sealed; a saved publication failed")
    results = {a: evidence(root / a, a, clocks[a], request) for a in arms}
    score = evaluate(results, decision)
    write(root / "result.json", dict(case="DS30-0008", machine=machine, inputs=request, sealed_selection=decision,
          stage=staging, runs=results, scores=score, waveform_calls=0, raw_acquisitions=0,
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("request", type=Path)
        parser.add_argument("arm", choices=("original", "selected"))
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("root", type=Path)
        parser.add_argument("medium", type=Path)
        run(**vars(parser.parse_args()))
