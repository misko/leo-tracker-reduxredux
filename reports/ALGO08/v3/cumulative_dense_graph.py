"""Time the exact graph composition through complete saved dense publication."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
RAW_SOURCE = Path("/var/tmp/leo-full-short-dense-DS30-0008")
RAW_BINDING_SHA = "1425cca32530cf5ecf22ba9cfb99c79a8aac39dc9a0232202270552968c49ac7"
NATIVE_SHA = "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
DENSE_REPLAY = Path("/var/tmp/leo-v3-dense-full-short-crossover-results/replay.json")
REPLAY_SHA = "07fc95971344bb0eeb50db142a8e0818f9c4ce6dfdbf3b6a2c9cb65421fabfb5"
PUBLISHED = Path("/var/tmp/leo-v3-regional-dense-pair/scored.json")
PUBLISHED_SHA = "6e7e5faff62c531d0fb32e02e2a5d835ee36791ef778282bde8a8e0a4b1a5d62"
LIBRARIES = {
    "geographic_library": Path("/var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so"),
    "regional_track_library": Path("/srv/bulk/leo-dev/regional-probe-block-20261123/scores.so"),
    "frontier_block_library": Path("/srv/bulk/leo-dev/regional-probe-block-20261123/block.so"),
}
ORDER = ("installed", "reused")


def elapsed(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def worker(job, mode, output):
    started = process_time(), perf_counter()
    import empty_bootstrap as staged
    import unified_short_bootstrap as unified

    _, specification, sources, publication, pin_checks = staged.load_runtime()
    from aperture_trial import read, write
    from full_short_raw import RECIPE_SHA
    from short_graph_guard import prove

    request = read(job)
    args = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                           region=Path(request["region_file"]), output=output, one_pass_web_png=True,
                           exact_graph_reuse=mode == "reused", **{k: Path(v) for k, v in request["libraries"].items()})
    scan = staged.staged_scanner(sources)
    session, digest, inventory = scan.FastScanStore(output).inventory(args.recording, verify_windows=False)
    native = json.loads(staged.checked(Path(request["local_packet"]), NATIVE_SHA))
    staged.bind_native(native, session, digest, RECIPE_SHA, expected="sha256:"+NATIVE_SHA)
    if (session != request["session"] or digest != request["inventory"] or inventory["window_count"] != 6772
            or native["source"]["raw_recording_authority_digest"] != request["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]
            or sha256(args.region.read_bytes()).hexdigest() != request["region_sha256"]):
        raise ValueError("Dense signed history or original offer differs from the pair")
    graph_proof = prove(native, staged.RELEASE / "assets")
    if graph_proof["proven"] or graph_proof["winning_rows"] != 7336:
        raise ValueError("The archived dense packet must reach its original signed solver")
    graph, layout = {}, {}
    handoff = unified.Handoff(session, digest, RECIPE_SHA, native)
    receipt, details = unified.publish_active(args, publication, specification, handoff, layout, graph_audit=graph)
    through_publication = elapsed(started)
    if handoff.calls != 1 or receipt["decision"] != "complete":
        raise ValueError("Expected a verified exact handoff and complete dense publication")
    write(output / "dense-graph-execution.json", dict(mode=mode, graph=graph, layout=layout, waveform_calls=0,
          handoffs=handoff.calls, stock_source_checks=pin_checks, through_publication=through_publication,
          solve=details["solve"], sources=details["source_sha256"], receipt=receipt))
    print(json.dumps(receipt, allow_nan=False))


def read_archives():
    from aperture_trial import read
    from dense_full_short_raw import checked

    stored = read(checked(RAW_SOURCE / "binding.json", RAW_BINDING_SHA))
    replay = read(checked(DENSE_REPLAY, REPLAY_SHA))
    published = read(checked(PUBLISHED, PUBLISHED_SHA))
    official = published["runs"]["native"]
    if (stored != replay["raw"]["binding"] or replay["raw"]["raw_native_sha256"] != "sha256:"+NATIVE_SHA
            or official["science"] != replay["science"] or official["arms"] != replay["arms"]
            or official["owners"] != replay["associated"] or not published["same_complete_science"]):
        raise ValueError("Archived dense replays do not describe the same signed solution")
    return stored, replay, official


def run(root):
    from aperture_trial import RELEASE, archive_identity, read, write
    from combined_frontier_run import BLOCK_SHA
    from dense_full_short_crossover import command_path
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from full_short_raw import RECIPE_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from publication_media_checks import verify_position_sidecars
    from short_raw_diagnostic import measure, pairs
    from unified_short_bootstrap import LAYOUT_SHA256

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use a private tmpfs folder for both fresh saved outputs")
    stored, original, official = read_archives()
    (native_file,) = (RAW_SOURCE / "publication/fast-scan-automatic-work").glob("*/detections.json")
    data = checked(native_file, NATIVE_SHA)
    native = json.loads(data)
    rows = native["source"]["probes"]
    program = stored["command"]
    recording = program[program.index("--recording")+1]
    if (sum(len(row["candidates"]) for row in rows) != 7336 or len(rows) != 13530
            or native["source"]["analysis_manifest_sha256"] != canonical_digest(
                ["cancellation", stored["authority"], RECIPE_SHA, rows])
            or archive_identity(Path(stored["archive"]["root"])) != stored["archive"]
            or not command_path(program, "--geographic-library", LIBRARIES["geographic_library"])):
        raise ValueError("Dense factors, causal archive or geographic projector changed")
    for path, pin in zip(LIBRARIES.values(), (GEOGRAPHIC_SHA, TRACK_SCORES_SHA, BLOCK_SHA), strict=True):
        checked(path, pin)
    checked(HERE / "one_pass_web_png.py", LAYOUT_SHA256)
    root.mkdir()
    (root / "tmp").mkdir()
    packet = root / "dense-detections.json"
    packet.write_bytes(data)
    job = root / "binding.json"
    write(job, dict(recording=recording, local_packet=str(packet), archive=stored["archive"], region_file=stored["region"],
          region_sha256=stored["region_sha256"], authority=stored["authority"], session=stored["session"],
          inventory=stored["inventory"], cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"],
          libraries={k: str(v) for k, v in LIBRARIES.items()}))
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    result, selections = {}, {}
    for mode in ORDER:
        output = root / mode
        command = [python, "-IB", __file__, "saved-worker", job, mode, output]
        timing = measure(command, env, output)
        write(root / f"{mode}-clock.json", dict(timing=timing, command=list(map(str, command))))
        if timing["exit_code"]:
            raise RuntimeError(timing["stderr_tail"])
        worker_data = read(output / "dense-graph-execution.json")
        receipt = worker_data["receipt"]
        research = read(output / "joint-research-receipt.json")
        timing_only = {"cpu_s", "elapsed_s"}
        regional, = research["early_regional"]
        historical, = original["regional"]
        proof = {k: v for k, v in regional["result"].items() if k not in timing_only}
        old_proof = {k: v for k, v in historical["result"].items() if k not in timing_only}
        actual = pairs.evidence(output, receipt, timing["started_unix_ns"], read_only=True)
        bundle = artifacts(output, receipt)
        grid = FastStandardAnalysisStore(output).position_grid(receipt["run_id"])
        selections[mode] = research["selected_rows"]
        if (receipt["terminal_sha256"] != official["terminal_sha256"] or actual["arms"] != original["arms"]
                or actual["owners"] != original["owners"] or actual["scientific_digests"] != original["science"]
                or actual["raw_authority"] != stored["authority"] or receipt["region"] != original["raw"]["holder"]["offer"]
                or worker_data["waveform_calls"] != 0 or worker_data["handoffs"] != 1
                or worker_data["graph"]["enabled"] != (mode == "reused")
                or sha256(native_packet(output).read_bytes()).hexdigest() != NATIVE_SHA
                or not grid["complete"] or grid["evaluated_points"] != 179 or len(bundle["images"]) != 8
                or selections[mode] != original["selected_rows"] or proof != old_proof):
            raise ValueError(f"{mode} differs from original dense owners, numerical evidence, or geographic verdict")
        result[mode] = dict(clock=timing, worker=worker_data, science=actual, images=bundle["images"],
                            graph_rows=canonical_digest(selections[mode]), regional=proof)
        write(root / f"{mode}-verified.json", result[mode])

    a, b = (result[mode] for mode in ORDER)
    run_id = a["worker"]["receipt"]["run_id"]
    store_a, store_b = (FastStandardAnalysisStore(root / mode) for mode in ORDER)
    if (a["images"] != b["images"] or any(store_a.artifact(run_id, name) != store_b.artifact(run_id, name) for name in a["images"])
            or a["regional"] != b["regional"] or selections["installed"] != selections["reused"]
            or a["worker"]["layout"]["work"] != b["worker"]["layout"]["work"]
            or b["worker"]["graph"]["cache"].get("best_hits", 0) <= 0
            or b["worker"]["graph"]["graph"].get("edge_fallbacks", 0)):
        raise ValueError("The optimized graph changed dense publication, used fallback or did not reuse best pieces")
    for key in ("calls", "edge_lanes", "edges", "assigned", "tracks"):
        if a["worker"]["graph"]["graph"][key] != b["worker"]["graph"]["graph"][key]:
            raise ValueError(f"Graph differs in {key}")
    sidecars = verify_position_sidecars(root / ORDER[0], root / ORDER[1], run_id, a["images"], b["images"])
    write(root / "result.json", dict(case="DS30-0008", machine=machine, order=ORDER, runs=result, sidecars=sidecars,
          graph_config_sha256=original["track_asset_sha256"], native_sha256=NATIVE_SHA, inputs=read(job),
          archived=dict(raw_binding=RAW_BINDING_SHA, dense_replay=REPLAY_SHA, official=PUBLISHED_SHA,
                        original_artifacts=official["images"]),
          protocol_sha256=sha256((HERE / "cumulative-dense-graph-protocol.md").read_bytes()).hexdigest(),
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["saved-worker"]:
        parser.add_argument("job", type=Path)
        parser.add_argument("mode", choices=ORDER)
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("root", type=Path)
        run(parser.parse_args().root)
