"""Compare the exact Graph and grid opt-ins through the active saved publication."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
WEAK = Path("/dev/shm/leo-v3-combined-frontier-weak-01")
WEAK_PINS = {
    "binding.json": "afeb71af78edb21f3460d64712fc710eff22bcb257bdba3bfd7135b26bd3510d",
    "candidate/joint-research-receipt.json": "5593e656b928a1f33912c8e0a96e237389375841e1f3a0521974928c22856736",
}
WEAK_SCIENCE = "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233"
LAYOUTS = {
    "weak": ("unified-short-layout.json.gz", "d1eee8981f1be7e09c79019b7c3e0dbf2136cebaa453e2ae0ff5440d222ace7e"),
    "dense": ("cumulative-dense-graph-DS30-0008.json.gz", "f335120b34ddc8775a55fee321a28826c7bbecfadf6fb16f2efcf335473e387d"),
}
CASES = {"weak": "DS30-0016", "dense": "DS30-0008"}
MODES = ("installed", "combined")


def proof_fields(record):
    return {key: value for key, value in record["result"].items()
            if key not in ("cpu_s", "elapsed_s")}


def enrolled(case):
    from cumulative_dense_graph import LIBRARIES, NATIVE_SHA, RAW_SOURCE, read_archives
    from empty_bootstrap import checked
    from local_future_cli_trial import native_packet

    name, pin = LAYOUTS[case]
    data = gzip.decompress((HERE / "measurements" / name).read_bytes())
    if sha256(data).hexdigest() != pin:
        raise ValueError("The original explicit-layout qualification changed")
    layout = json.loads(data)
    if case == "weak":
        binding, research = (json.loads(checked(WEAK / name, pin)) for name, pin in WEAK_PINS.items())
        source = binding["request"]
        science = read_checked_science(WEAK_SCIENCE)
        (regional,) = research["early_regional"]
        expected = dict(science, owner_rows=research["selected_rows"], proof=proof_fields(regional),
                        figures=layout["layout"]["direct"])
        request = dict(recording=source["recording"], region=source["region_file"],
                       offer_sha256=source["offer_sha256"], authority=source["raw_authority"],
                       session=source["session"], inventory=binding["inventory"],
                       archive=source["archive"], issued=808, native=science["native_sha256"])
        packet = native_packet(WEAK / "candidate")
    else:
        source, replay, publication = read_archives()
        (regional,) = replay["regional"]
        expected = dict(arms=replay["arms"], owners=replay["owners"], scientific_digests=replay["science"],
                        terminal_sha256=publication["terminal_sha256"], owner_rows=replay["selected_rows"],
                        figures=layout["runs"]["reused"]["images"], proof=proof_fields(regional))
        command = source["command"]
        request = dict(recording=command[command.index("--recording")+1], region=source["region"],
                       offer_sha256=source["region_sha256"], authority=source["authority"],
                       session=source["session"], inventory=source["inventory"],
                       archive=source["archive"], issued=6772, native="sha256:"+NATIVE_SHA)
        packet = native_packet(RAW_SOURCE / "publication")
    request["libraries"] = {key: str(path) for key, path in LIBRARIES.items()}
    return request, packet, expected


def read_checked_science(pin):
    from empty_bootstrap import checked

    return json.loads(checked(HERE / "measurements/weak-combined-raw.json", pin))["runs"]["candidate"]


def worker(job, mode, output, named_survivor_finish=False):
    started = process_time(), perf_counter()
    import empty_bootstrap as staged
    import unified_short_bootstrap as cumulative

    from aperture_trial import read, write
    from full_short_raw import RECIPE_SHA

    _, specification, sources, publication, pins = staged.load_runtime()
    request = read(job)
    args = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                           region=Path(request["region"]), output=output, one_pass_web_png=True,
                           exact_graph_reuse=mode == "combined", named_survivor_finish=named_survivor_finish,
                           grid_feature_projection_library=Path(request["projection"]) if mode == "combined" else None,
                           **{key: Path(path) for key, path in request["libraries"].items()})
    scan = staged.staged_scanner(sources)
    session, inventory, manifest = scan.FastScanStore(output).inventory(args.recording, verify_windows=False)
    native = json.loads(staged.checked(Path(request["packet"]), request["native"].removeprefix("sha256:")))
    staged.bind_native(native, session, inventory, RECIPE_SHA, expected=request["native"])
    if (session, inventory, manifest["window_count"]) != (request["session"], request["inventory"], request["issued"]):
        raise ValueError("The original signed inventory changed")
    if (native["source"]["raw_recording_authority_digest"] != request["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]
            or sha256(args.region.read_bytes()).hexdigest() != request["offer_sha256"]):
        raise ValueError("The signed acquisition or supplied offer changed")
    handoff = cumulative.Handoff(session, inventory, RECIPE_SHA, native)
    graph, layout = {}, {}
    receipt, detail = cumulative.publish_active(args, publication, specification, handoff, layout, graph_audit=graph)
    clocks = dict(cpu_s=process_time()-started[0], elapsed_s=perf_counter()-started[1])
    if handoff.calls != 1 or receipt["decision"] != "complete":
        raise ValueError("Expected a verified handoff and one full active publication")
    write(output / "cumulative-grid-worker.json", dict(receipt=receipt, graph=graph, layout=layout, pins=pins,
          waveform_calls=0, handoffs=handoff.calls, solve=detail["solve"], complete_publication=clocks,
          sources=detail["source_sha256"], projection=detail.get("grid_feature_projection"),
          named_survivor_finish=detail.get("named_survivor_finish")))
    print(json.dumps(receipt, allow_nan=False))


def run(case, root, projection, after_weak):
    from aperture_trial import RELEASE, archive_identity, read, write
    from combined_frontier_run import BLOCK_SHA
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from full_short_raw import RECIPE_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from publication_media_checks import verify_position_sidecars
    from short_raw_diagnostic import measure, pairs
    from unified_short_bootstrap import LAYOUT_SHA256

    machine = host()
    if (case == "dense" and (after_weak is None or read(after_weak)["case"] != CASES["weak"]
                            or not read(after_weak)["verified"])):
        raise ValueError("Complete the exact weak pair before the dense pair")
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use a private tmpfs parent")
    request, packet, expected = enrolled(case)
    data = checked(packet, request["native"].removeprefix("sha256:"))
    native = json.loads(data)
    source = native["source"]
    if (source["analysis_manifest_sha256"] != canonical_digest(
            ["cancellation", request["authority"], RECIPE_SHA, source["probes"]])
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]):
        raise ValueError("The enrolled acquisition or causal archive changed")
    for path, pin in zip(request["libraries"].values(), (GEOGRAPHIC_SHA, TRACK_SCORES_SHA, BLOCK_SHA), strict=True):
        checked(Path(path), pin)
    checked(HERE / "one_pass_web_png.py", LAYOUT_SHA256)
    projection = projection.resolve(strict=True)
    checked(projection, LIBRARY_SHA)
    root.mkdir()
    (root / "tmp").mkdir()
    local = root / "detections.json"
    local.write_bytes(data)
    request.update(packet=str(local), cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"],
                   projection=str(projection))
    job = root / "binding.json"
    write(job, request)
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)

    order = MODES if case == "weak" else MODES[::-1]
    results, selection = {}, {}
    for mode in order:
        output = root / mode
        command = [python, "-IB", __file__, "worker", job, mode, output]
        clock = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=clock, command=list(map(str, command))))
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])
        observed = read(output / "cumulative-grid-worker.json")
        research = read(output / "joint-research-receipt.json")
        receipt = observed["receipt"]
        science = pairs.evidence(output, receipt, clock["started_unix_ns"], read_only=True)
        images = artifacts(output, receipt)["images"]
        grid = FastStandardAnalysisStore(output).position_grid(receipt["run_id"])
        selection[mode] = research["selected_rows"]
        (regional,) = research["early_regional"]
        if (any(science[key] != expected[key] for key in ("arms", "owners", "scientific_digests"))
                or receipt["terminal_sha256"] != expected["terminal_sha256"]
                or selection[mode] != expected["owner_rows"] or proof_fields(regional) != expected["proof"]
                or science["raw_authority"] != request["authority"] or sha256(native_packet(output).read_bytes()).hexdigest()
                != request["native"].removeprefix("sha256:") or not grid["complete"] or grid["evaluated_points"] != 179
                or canonical_digest(images) != canonical_digest(expected["figures"]) or len(images) != 8
                or observed["handoffs"] != 1 or observed["waveform_calls"]
                or observed["graph"]["enabled"] != (mode == "combined")):
            raise ValueError(f"{case} {mode} differs from the enrolled signed publication")
        if mode == "combined":
            counts = observed["projection"]["calls"]
            if (counts.get("grids") != 1 or counts.get("native_projection", 0) <= 0
                    or counts.get("native_selection") != 356
                    or any(value for key, value in counts.items() if "fallback" in key)
                    or observed["graph"]["graph"].get("edge_fallbacks", 0)):
                raise ValueError("Expected native map projection, packing and exact Graph without fallback")
        results[mode] = dict(clock=clock, worker=observed, science=science, images=images,
                             role_sha256=canonical_digest(selection[mode]), regional=proof_fields(regional))
        write(root / f"{mode}-verified.json", results[mode])

    original, combined = (results[mode] for mode in MODES)
    run_id = original["worker"]["receipt"]["run_id"]
    sidecars = verify_position_sidecars(root / MODES[0], root / MODES[1], run_id, original["images"], combined["images"])
    stores = [FastStandardAnalysisStore(root / mode) for mode in MODES]
    for name, image in original["images"].items():
        if stores[0].artifact(run_id, name, image["sha256"]) != stores[1].artifact(run_id, name, image["sha256"]):
            raise ValueError(f"Official PNG bytes changed for {name}")
    if (original["worker"]["layout"]["work"] != combined["worker"]["layout"]["work"]
            or original["regional"] != combined["regional"]):
        raise ValueError("Rendering route or regional proof changed")
    for key in ("calls", "edge_lanes", "edges", "assigned", "tracks"):
        if any(row["worker"]["graph"]["graph"][key] != original["worker"]["graph"]["graph"][key]
               for row in results.values()):
            raise ValueError(f"The exact Graph changed its {key} count")
    write(root / "result.json", dict(case=CASES[case], verified=True, machine=machine, order=order,
          runs=results, inputs=request, sidecars=sidecars, layout_reference=LAYOUTS[case],
          weak_gate_sha256=None if after_weak is None else sha256(after_weak.read_bytes()).hexdigest(),
          source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
              "cumulative-grid-projection-protocol.md", "cumulative_grid_projection.py", "unified_short_bootstrap.py",
              "grid_phase_state_reuse.py", "grid_feature_projection.py", "grid_feature_projection.c",
          )}))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("job", type=Path)
        parser.add_argument("mode", choices=MODES)
        parser.add_argument("output", type=Path)
        parser.add_argument("--named-survivor-finish", action="store_true",
                            help="Apply the same original final-fit option as the raw research launcher")
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("case", choices=CASES)
        parser.add_argument("root", type=Path)
        parser.add_argument("projection", type=Path)
        parser.add_argument("--after-weak", type=Path)
        run(**vars(parser.parse_args()))
