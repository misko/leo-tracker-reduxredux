"""Compare cumulative active settings on one already authenticated medium packet."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


ENTRY = process_time(), perf_counter()
HERE = Path(__file__).resolve().parent
SEALED = Path("/dev/shm/leo-cumulative-medium.OBSGQ15J/pair")
CONTROLS = {
    "binding.json": "2690934ebd8df12b3a9eab50cad06b091984780ab24bfeff316536d0271afb44",
    "result.json": "8b716e18d0275e259d2541587662980515d0781a328a923c0982b16995bf534b",
    "candidate/joint-research-receipt.json": "f9ff8b1566e88746c50016158abbacfe506b717f0603f897d6708b135db95f7c",
}
PROJECTOR = Path("/dev/shm/leo-cumulative-grid-projection-01/projection.so")
MODES = ("stock", "combined")


def worker(job, mode, output):
    import empty_bootstrap as staged
    import unified_short_bootstrap as unified
    from aperture_trial import read, write
    from combined_frontier_run import BLOCK_SHA
    from full_short_run import GEOGRAPHIC_SHA, RECIPE_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    from short_graph_guard import prove

    _, specification, sources, publication, _ = staged.load_runtime()
    request = read(job)
    options = SimpleNamespace(
        recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
        region=Path(request["region"]), output=output, one_pass_web_png=True, exact_graph_reuse=True,
        reuse_verified_png_reads=True, grid_feature_projection_library=PROJECTOR,
        lazy_scanner_detector=mode == "combined", exact_phase_forecast=mode == "combined",
        **{key: Path(request[key]) for key in ("geographic_library", "regional_track_library", "frontier_block_library")},
    )
    for path, pin in ((options.geographic_library, GEOGRAPHIC_SHA), (options.regional_track_library, TRACK_SCORES_SHA),
                      (options.frontier_block_library, BLOCK_SHA), (HERE / "one_pass_web_png.py", unified.LAYOUT_SHA256),
                      (options.region, request["region_sha256"]), (PROJECTOR, LIBRARY_SHA)):
        staged.checked(path, pin)
    pin = request["native"]["candidate"]
    native = json.loads(staged.checked(Path(request["packets"]["candidate"]), pin.removeprefix("sha256:")))
    scan = staged.staged_scanner(sources)
    session, inventory, evidence = scan.FastScanStore(output).inventory(options.recording, verify_windows=False)
    staged.bind_native(native, session, inventory, RECIPE_SHA, expected=pin)
    if (inventory != request["input_manifest"] or evidence["window_count"] != 2717
            or native["source"]["raw_recording_authority_digest"] != request["raw_authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["clock_cutoff_utc_ns"]):
        raise ValueError("Original medium authorities changed")
    proof = prove(native, staged.RELEASE / "assets")
    scientific_before = [name for name in (*staged.SCIENTIFIC_IMPORTS, "exact_phase_forecast") if name in sys.modules]
    if proof["proven"] or scientific_before:
        raise ValueError("Expected an active graph and a fresh scientific stack")
    handoff = unified.Handoff(session, inventory, RECIPE_SHA, native)
    layout, graph, png = {}, {}, {}
    detector = {} if options.lazy_scanner_detector else None
    receipt, detail = unified.publish_active(options, publication, specification, handoff, layout,
                                             graph_audit=graph, png_read_audit=png, detector_import_audit=detector)
    cpu, wall = process_time() - ENTRY[0], perf_counter() - ENTRY[1]
    if receipt["decision"] != "complete" or handoff.calls != 1:
        raise ValueError("Expected one verified medium handoff and a complete publication")
    receiver = staged.RECEIVER.removesuffix(".py").replace("/", ".")
    write(output / "cumulative-forecast-worker.json", dict(
        mode=mode, receipt=receipt, cpu_s=cpu, elapsed_s=wall, solve=detail["solve"], layout=layout,
        graph=graph, png_reads=png, projection=detail["grid_feature_projection"],
        phase_forecast=detail.get("exact_phase_forecast"), detector_import=detector,
        receiver_loaded=receiver in sys.modules, forecast_loaded="exact_phase_forecast" in sys.modules,
        scientific_before=scientific_before, waveform_calls=0, handoffs=handoff.calls,
    ))


def verify(output, mode, timing, reference, research, request, *, observed_fallback=False):
    from aperture_trial import read
    from cumulative_grid_projection import proof_fields
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs

    run = read(output / "cumulative-forecast-worker.json")
    receipt = run["receipt"]
    actual = pairs.evidence(output, receipt, timing["started_unix_ns"], read_only=True)
    archive = reference["evidence"]
    detail = read(output / "joint-research-receipt.json")
    (regional,) = detail["early_regional"]
    (original,) = research["early_regional"]
    products = artifacts(output, receipt)
    store = FastStandardAnalysisStore(output)
    grid, path = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
    if (receipt["terminal_sha256"] != archive["receipt"]["terminal_sha256"]
            or actual["raw_authority"] != request["raw_authority"]
            or sha256(native_packet(output).read_bytes()).hexdigest() != request["native"]["candidate"][7:]
            or any(actual[key] != archive[key] for key in ("arms", "owners", "scientific_digests"))
            or detail["selected_rows"] != research["selected_rows"] or proof_fields(regional) != proof_fields(original)
            or canonical_digest(products["images"]) != canonical_digest(reference["figures"])
            or not grid["complete"] or grid["evaluated_points"] != 179
            or not run["graph"]["enabled"] or not run["projection"]["calls"].get("native_selection")
            or run["scientific_before"] or run["waveform_calls"] or run["handoffs"] != 1):
        raise ValueError("The active medium publication changed its archived evidence")
    if mode == "combined":
        (forecast,) = run["phase_forecast"]["executions"]
        activation = (not forecast["used"] and forecast["fallback"] == "unsupported phase forecast binding"
                      if observed_fallback else forecast["used"] and forecast["julian_cache_hits"] > 0)
        if (not activation or not run["forecast_loaded"]
                or run["detector_import"] != {"deferred": True, "original_calls": 0} or run["receiver_loaded"]):
            raise ValueError("Installed active solve did not have the expected optimization status")
    elif run["phase_forecast"] is not None or run["forecast_loaded"] or not run["receiver_loaded"]:
        raise ValueError("The stock route must leave forecast and receiver imports alone")
    sidecars = {}
    for name, document in (("path", path), ("grid", grid)):
        if document["binding"]["position_png_sha256"] != products["images"]["position"]["sha256"]:
            raise ValueError("Position sidecar does not bind the actual PNG")
        sidecars[name] = canonical_digest({key: value for key, value in document.items() if key != "elapsed_seconds"})
    science = dict(arms=actual["arms"], owners=actual["owners"], science=actual["scientific_digests"],
                   terminal_sha256=receipt["terminal_sha256"], ordered_roles_sha256=canonical_digest(detail["selected_rows"]),
                   regional=proof_fields(regional), grid_points=grid["evaluated_points"],
                   sidecars=sidecars, images=products["images"])
    return dict(process=timing, worker=run, science=science,
                persisted_sidecar_digests={name: products[name] for name in sidecars})


def checked_case():
    from aperture_trial import archive_identity
    from empty_bootstrap import checked

    request, saved, research = (json.loads(checked(SEALED / name, pin)) for name, pin in CONTROLS.items())
    reference = saved["runs"]["candidate"]
    request["clock_cutoff_utc_ns"] = reference["phases"]["clock_cutoff_utc_ns"]
    checked(Path(request["packets"]["candidate"]), request["native"]["candidate"].removeprefix("sha256:"))
    if archive_identity(Path(request["archive"]["root"])) != request["archive"]:
        raise ValueError("The enrolled medium causal archive changed")
    return request, reference, research


def new_arm(root, mode, output, reference, research, request):
    from aperture_trial import write
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    command = [python, "-IB", __file__, "worker", root / "binding.json", mode, output]
    timing = measure(command, env, output)
    write(output.with_name(output.name + "-clock.json"), timing)
    if timing["exit_code"]:
        raise RuntimeError(timing["stderr_tail"])
    result = verify(output, mode, timing, reference, research, request)
    write(output.with_name(output.name + "-verified.json"), result)
    return result


def run(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Choose a private tmpfs output")
    request, reference, research = checked_case()
    root.mkdir()
    (root / "tmp").mkdir()
    write(root / "binding.json", request)
    python = RELEASE / "venv/bin/python"
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    runs = {}
    for mode in MODES:
        runs[mode] = new_arm(root, mode, root / mode, reference, research, request)
    finish(root, runs, request, machine)


def finish(root, runs, request, machine, *, fallback=None):
    from aperture_trial import write

    if runs["stock"]["science"] != runs["combined"]["science"]:
        raise ValueError("Saved complete science differs between the arms")
    write(root / "result.json", dict(machine=machine, order=MODES, runs=runs, inputs=request, controls=CONTROLS,
                                     source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
                                         "cumulative-phase-forecast-protocol.md", "cumulative_phase_forecast_trial.py",
                                         "exact_phase_forecast.py", "unified_short_bootstrap.py", "joint_publication.py",
                                         "lazy_scanner_detector.py")}, waveform_reads=0, fallback=fallback))


def recover(root):
    """Seal the known forecast fallback and pay only the authorized combined arm."""
    from aperture_trial import read, write
    from dense_geographic_trial import host

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root], text=True).strip() != "tmpfs":
        raise ValueError("Require the original admitted tmpfs publication root")
    request, reference, research = checked_case()
    if request != read(root / "binding.json") or (root / "combined-recovery").exists() or (root / "result.json").exists():
        raise ValueError("Require the original unrecovered pair and its immutable request")
    stock = verify(root / "stock", "stock", read(root / "stock-clock.json"), reference, research, request)
    fallback = verify(root / "combined", "combined", read(root / "combined-clock.json"), reference, research, request,
                      observed_fallback=True)
    if stock["science"] != fallback["science"]:
        raise ValueError("The fallback pair failed an independent scientific check")
    write(root / "fallback-verified.json", fallback)
    recovery = new_arm(root, "combined", root / "combined-recovery", reference, research, request)
    finish(root, dict(stock=stock, combined=recovery), request, machine, fallback=fallback)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("job", type=Path)
        parser.add_argument("mode", choices=MODES)
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("root", type=Path)
        parser.add_argument("--recover-known-fallback", action="store_true")
        args = parser.parse_args()
        (recover if args.recover_known_fallback else run)(args.root)
