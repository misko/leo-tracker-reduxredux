"""Verify the one medium cumulative publication input and measure an admitted pair."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch


ENTRY = process_time(), perf_counter()
HERE = Path(__file__).resolve().parent
CONTROL = "7b12b73f5e104a56d9da7c47641c6014e8003bed54efc4e4174b8c08abd35e67"
MAX_FULL_IO_STALL = 10.0
SEALED = Path("/tmp/leo-protected-DS30-0057-01")
PRIOR_RAW = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-short-raw-diagnostic-pairs/DS30-0057")
LAYOUT_BLOCK = Path("/srv/bulk/leo-dev/regional-probe-block-20261123/block.so")


def control():
    from short_raw_diagnostic import CASES, assignment, checked, read

    case, pin, decision, visits, _ = CASES[1]
    source, archived = assignment(case, pin, decision, visits)
    row = read(checked(HERE / "measurements/short-raw-diagnostic.json", CONTROL))["cases"][1]
    if (case, decision, visits) != ("DS30-0057", "complete", 2717):
        raise ValueError("Require the frozen medium physical workload")
    if any(row[key] != source[key] for key in ("recording", "archive")) or row["region_file"] != source["region"]:
        raise ValueError("Archived medium control no longer binds original acquisition or prior")
    return row, archived


def full_io_share(document):
    full = [line.split() for line in document.splitlines() if line.startswith("full ")]
    (row,) = full
    return float(dict(pair.split("=", 1) for pair in row[1:])["avg10"])


def admitted(cache, pressures):
    return (not cache["unavailable"] and cache["members"] == cache["observed_members"] > 0
            and cache["cached_pages"] == cache["observed_file_pages"] > 0
            and all(0 <= full_io_share(sample) <= MAX_FULL_IO_STALL for sample in pressures))


def preflight(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, FastScanStore, cache_residency, checked

    settings = host()
    row, _ = control()
    root.mkdir()
    recording = Path(row["recording"])
    store = FastScanStore(root)
    session, digest, inventory = store.inventory(recording, verify_windows=False)
    if digest != row["runs"]["candidate"]["input_manifest"] or inventory["window_count"] != row["issued"]:
        raise ValueError("Medium input no longer matches the archived signed inventory")
    source = tuple((Path(m["path"]) / "manifest.json", m["manifest_digest"]) for m in inventory["segments"])
    query = cache_residency.load_query(checked(CACHE_LIB, CACHE_SHA))
    pressure = Path("/proc/pressure/io")
    start = pressure.read_text()
    cache = cache_residency.bound_snapshot(store, recording, source, os.sysconf("SC_PAGE_SIZE"), query)
    end = pressure.read_text()
    out = dict(case=row["case"], admission="raw" if admitted(cache, (start, end)) else "saved",
               max_full_io_stall_pct=MAX_FULL_IO_STALL, settings=settings, recording=str(recording), issue=row["issued"],
               session=session, input_manifest=digest, cache=cache, pressure=[start, end], waveform_calls=0,
               archive=row["archive"], region=row["region"], control_sha256=CONTROL)
    write(root / "admission.json", out)
    print(json.dumps(out))


def time_since(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def saved_worker(job, arm, output):
    """Use the identical active publication boundary on an authenticated packet."""
    import empty_bootstrap as staged
    import unified_short_bootstrap as cumulative

    _, specification, sources, publication, checks = staged.load_runtime()
    from aperture_trial import read, write
    from combined_frontier_run import BLOCK_SHA
    from full_short_run import GEOGRAPHIC_SHA, RECIPE_SHA, TRACK_SCORES_SHA
    from short_graph_guard import prove

    request = read(job)
    file = Path(request["packets"][arm])
    native = json.loads(staged.checked(file, request["native"][arm].removeprefix("sha256:")))
    scan = staged.staged_scanner(sources)
    options = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                              region=Path(request["region"]), output=output, one_pass_web_png=True,
                              **{key: Path(request[key]) for key in ("geographic_library", "regional_track_library", "frontier_block_library")})
    session, digest, evidence = scan.FastScanStore(output).inventory(options.recording, verify_windows=False)
    receiver = RECIPE_SHA if arm == "candidate" else specification["detector_sha256"]
    staged.bind_native(native, session, digest, receiver, expected=request["native"][arm])
    if (digest != request["input_manifest"] or evidence["window_count"] != 2717
            or native["source"]["raw_recording_authority_digest"] != request["raw_authority"]
            or sha256(options.region.read_bytes()).hexdigest() != request["region_sha256"]):
        raise ValueError("Saved detector handoff changed physical source, chronology or offer")
    handoff = cumulative.Handoff(session, digest, receiver, native)
    captured, metrics, layout = [], {}, {}
    if arm == "candidate":
        for library, pin in ((options.geographic_library, GEOGRAPHIC_SHA), (options.regional_track_library, TRACK_SCORES_SHA),
                             (options.frontier_block_library, BLOCK_SHA), (HERE / "one_pass_web_png.py", cumulative.LAYOUT_SHA256)):
            staged.checked(library, pin)
        proof = prove(native, staged.RELEASE / "assets")
        if proof["proven"]:
            raise ValueError("The archived active medium packet must use the complete numerical route")
        render_context = cumulative.layout_renderer

        @contextmanager
        def capture_layout(live, enabled, clocks):
            original = live.render
            with render_context(live, enabled, clocks):
                layout_render = live.render

                def capture(packet, **values):
                    captured.append((original, packet, values))
                    return layout_render(packet, **values)

                with patch.object(live, "render", capture):
                    yield

        with patch.object(cumulative, "layout_renderer", capture_layout):
            receipt, detail = cumulative.publish_active(options, publication, specification, handoff, layout)
        metrics["solve"] = detail["solve"]
    else:
        from tools import algo08_scan

        proof = None
        output.mkdir()
        original = algo08_scan.analyze

        def analyzed(*args, **kwargs):
            def timed(name):
                function = getattr(algo08_scan, name)

                def wrapper(*values, **settings):
                    start = process_time(), perf_counter()
                    result = function(*values, **settings)
                    metrics[name] = time_since(start)
                    return result

                return wrapper

            with (handoff.install(algo08_scan), patch.object(algo08_scan, "solve", timed("solve")),
                  patch.object(algo08_scan, "render", timed("render"))):
                return original(*args, **kwargs)

        with patch.object(algo08_scan, "analyze", analyzed):
            receipt = publication.run(SimpleNamespace(recording=options.recording, archive=options.archive,
                                      region=options.region, bulk_root=output), dict(specification, startup="stock"))
    spent = time_since(ENTRY)
    if handoff.calls != 1 or receipt["decision"] != "complete":
        raise ValueError("Expected complete saved publication through one verified handoff")
    write(output / "medium-saved-publication.json", dict(mode=arm, receipt=receipt, complete_saved_publication=spent,
          source_checks=checks, clocks=metrics, layout=layout, graph_proof=proof, waveform_calls=0, bound_handoffs=handoff.calls,
          receiver="sha256:"+receiver, source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          native=request["native"][arm], clock_cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"]))
    if arm == "candidate":
        ((original, packet, values),) = captured
        write(output / "medium-layout-audit.json", audit_layout(original, packet, values, output, receipt, request))
    print(json.dumps(receipt))


def verify_artist_safety(current, standard):
    return ([row[0] for row in current] == [row[0] for row in standard]
            and all(not set(label for label, _ in new[1]) - set(label for label, _ in old[1])
                    for new, old in zip(current, standard, strict=True)))


def audit_layout(original, packet, values, output, receipt, request):
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from one_pass_web_png import render
    from one_pass_web_png_trial import observe_artists
    from publication_media_checks import image_comparison_fields, verify_position_sidecars
    from saved_publication_trial import image_evidence

    start = process_time(), perf_counter()
    inventory, figures = {}, {}
    clocks = {}
    for name, enabled in (("original", False), ("direct", True)):
        until = process_time(), perf_counter()
        with observe_artists() as artists:
            images, _ = render(original, packet, enabled=enabled, **values)
        clocks[name] = time_since(until)
        if set(images) != set(PLOTS) or len(artists) != len(PLOTS):
            raise ValueError("The medium plotting packet did not produce its eight recorded figures")
        figures[name] = {key: image_evidence(value) for key, value in images.items()}
        inventory[name] = artists
    store = FastStandardAnalysisStore(output)
    run_id = receipt["run_id"]
    current = {name: image_evidence(store.artifact(run_id, name, figure["sha256"]))
               for name, figure in figures["direct"].items()}
    checks = dict(direct_replay_matches_published=current == figures["direct"],
                  changed_layout=figures["original"] != figures["direct"],
                  original_equals_archived=image_comparison_fields(figures["original"]) == request["original_figures"],
                  artists_and_overlap=verify_artist_safety(inventory["direct"], inventory["original"]),
                  image_metadata=all(figures["original"][name][key] == current[name][key]
                                     for name in PLOTS for key in ("size", "mode", "metadata")))
    if not all(checks.values()):
        raise ValueError(f"DS30-0057 explicit layout differs: {checks}")
    sidecars = verify_position_sidecars(Path(request["candidate_archive"]), output, run_id, figures["original"], current)
    canonical_artists = json.loads(json.dumps([row[0] for row in inventory["original"]], default=_json_value))
    return dict(artist_sha256=canonical_digest(canonical_artists), artists=len(canonical_artists), sidecars=sidecars, checks=checks,
                figures=figures, clipping={name: [row[1] for row in items] for name, items in inventory.items()},
                verification_cost=time_since(start), audited_replays=clocks)


def references(row):
    a = row["runs"]["stock"]["retained_handoff"]
    return dict(stock=dict(row["archived_stock_publication"], native_sha256=a["native_sha256"], terminal_sha256=a["terminal_sha256"]),
                candidate=row["runs"]["candidate"])


def saved_pair(root, admission):
    from aperture_trial import read, write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from combined_frontier_run import BLOCK_SHA
    from short_raw_diagnostic import checked, measure, pairs

    settings = host()
    approved = read(admission)
    row, archived = control()
    if (approved["admission"] != "saved" or approved["case"] != row["case"] or approved["waveform_calls"] != 0
            or approved["control_sha256"] != CONTROL or approved["input_manifest"] != row["runs"]["candidate"]["input_manifest"]):
        raise ValueError("A sealed passive admission must select this bounded saved pair")
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("The saved pair requires fresh tmpfs publication")
    refs = references(row)
    original = read(checked(HERE / "measurements/short-raw-diagnostic.json", CONTROL))
    libs = {name+"_library": str(checked(Path(original["native_libraries"][key]["path"]), pin))
            for name, key, pin in (("geographic", "geographic", GEOGRAPHIC_SHA), ("regional_track", "regional", TRACK_SCORES_SHA))}
    libs["frontier_block_library"] = str(checked(LAYOUT_BLOCK, BLOCK_SHA))
    # These are immutable copies of the genuine unfiltered and named detector bytes.
    packets = {}
    for arm, source in (("stock", "stock"), ("candidate", "forward")):
        (path,) = (SEALED / source / "fast-scan-automatic-work").glob("*/detections.json")
        packets[arm] = str(checked(path, refs[arm]["native_sha256"]))
    stock_build = pairs.verified_v3(pairs.NAMED_V3)
    root.mkdir()
    (root / "tmp").mkdir()
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    job = root / "binding.json"
    write(job, dict(recording=row["recording"], archive=row["archive"], region=row["region_file"],
                    region_sha256=sha256(Path(row["region_file"]).read_bytes()).hexdigest(),
                    input_manifest=approved["input_manifest"], raw_authority=archived["raw_authority"],
                    packets=packets, native={arm: info["native_sha256"] for arm, info in refs.items()},
                    original_figures=refs["candidate"]["pngs"], candidate_archive=str(PRIOR_RAW / "candidate"),
                    admission_sha256=sha256(admission.read_bytes()).hexdigest(), **libs))
    result = {}
    for arm in ("stock", "candidate"):
        output = root / arm
        command = [python, "-IB", __file__, "saved-worker", job, arm, output]
        timing = measure(command, env, output)
        write(root / f"{arm}-clock.json", dict(command=list(map(str, command)), timing=timing))
        if timing["exit_code"]:
            raise RuntimeError(f"{arm}: {timing['stderr_tail']}")
        result[arm] = verify_saved(output, timing, refs[arm], approved)
    summarize(root, admission, result, settings, stock_build)


def recover_audit(root, admission):
    """Repeat only the sealed candidate to recover the separate artist witness."""
    from aperture_trial import read, write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from short_raw_diagnostic import measure, pairs

    settings = host()
    authorization = read(admission)
    row, _ = control()
    refs = references(row)
    clocks = {arm: read(root / f"{arm}-clock.json")["timing"] for arm in refs}
    job = root / "binding.json"
    original = read(root / "candidate/medium-saved-publication.json")
    if (authorization["admission"] != "saved" or original["receipt"]["terminal_sha256"] != refs["candidate"]["terminal_sha256"]
            or original["native"] != refs["candidate"]["native_sha256"]
            or clocks["stock"]["exit_code"] != 0 or clocks["candidate"]["exit_code"] == 0
            or "cannot import name 'cache_residency'" not in clocks["candidate"]["stderr_tail"]
            or sha256(admission.read_bytes()).hexdigest() != read(job)["admission_sha256"]):
        raise ValueError("Recovery requires the one sealed pair and the known post-publication import failure")
    result = {"stock": verify_saved(root / "stock", clocks["stock"], refs["stock"], authorization)}
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    replay = root / "artist-recovery"
    command = [RELEASE / "venv/bin/python", "-IB", __file__, "saved-worker", job, "candidate", replay]
    timing = measure(command, env, replay)
    write(root / "artist-recovery-clock.json", dict(command=list(map(str, command)), timing=timing))
    if timing["exit_code"]:
        raise RuntimeError(f"Candidate artist recovery: {timing['stderr_tail']}")
    audit = replay / "medium-layout-audit.json"
    result["candidate"] = verify_saved(root / "candidate", clocks["candidate"], refs["candidate"], authorization, audit_path=audit)
    summarize(root, admission, result, settings, pairs.verified_v3(pairs.NAMED_V3), recovery=timing)


def summarize(root, admission, result, settings, stock_build, *, recovery=None):
    from aperture_trial import read, write
    from short_raw_diagnostic import checked
    from unified_short_bootstrap_trial import SURVEY
    from aperture_score import PHYSICAL, distance_km

    row, _ = control()
    survey, = [obj["reference"] for obj in read(checked(PHYSICAL, SURVEY))["cases"]
               if obj["dataset_label"] == row["case"] and obj["authority_eligible"]]
    truth = [survey["latitude_deg"], survey["longitude_deg"]]
    for arm in result.values():
        arm["horizontal_errors_km"] = {name: distance_km(item["latlon"], truth) for name, item in arm["evidence"]["arms"].items()}
    write(root / "result.json", dict(case=row["case"], setting=settings, stock_build=stock_build, admission=read(admission),
          admission_digest=sha256(admission.read_bytes()).hexdigest(), boundary="fresh saved handoff through standard publication",
          order=["stock", "candidate"], runs=result, candidate_artist_recovery=recovery,
          protocol_sha256=sha256((HERE / "cumulative-medium-protocol.md").read_bytes()).hexdigest()))


def verify_saved(output, timing, archive, admitted, *, audit_path=None):
    from aperture_trial import read
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs
    from publication_media_checks import image_comparison_fields

    phases = read(output / "medium-saved-publication.json")
    receipt = phases["receipt"]
    actual = pairs.evidence(output, receipt, timing["started_unix_ns"], read_only=True)
    images = artifacts(output, receipt)["images"]
    if (receipt["terminal_sha256"] != archive["terminal_sha256"] or receipt["region"] != admitted["region"]
            or phases["waveform_calls"] != 0 or phases["bound_handoffs"] != 1
            or sha256(native_packet(output).read_bytes()).hexdigest() != archive["native_sha256"].removeprefix("sha256:")
            or any(actual[key] != archive[key] for key in ("arms", "owners", "scientific_digests"))):
        raise ValueError("The sealed medium publication differs from its own prior scientific outcome")
    audit = read(audit_path or output / "medium-layout-audit.json") if output.name == "candidate" else None
    target = image_comparison_fields(audit["figures"]["direct"]) if audit else archive["pngs"]
    store = FastStandardAnalysisStore(output)
    grid = store.position_grid(receipt["run_id"])
    if ({key: dict(val, size=list(val["size"])) for key, val in images.items()} != target or len(images) != 8
            or not grid["complete"] or grid["evaluated_points"] != 179):
        raise ValueError("Expected all eight verified source-specific figures and complete grid")
    return dict(external_through_exit=timing, phases=phases, evidence=actual, figures=images, audit=audit)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_subparsers(dest="mode", required=True)
    probe, pair, worker, recovery = (action.add_parser(name) for name in ("admission", "saved-pair", "saved-worker", "recover-audit"))
    probe.add_argument("root", type=Path)
    pair.add_argument("root", type=Path)
    pair.add_argument("admission", type=Path)
    worker.add_argument("job", type=Path)
    worker.add_argument("arm", choices=("stock", "candidate"))
    worker.add_argument("output", type=Path)
    recovery.add_argument("root", type=Path)
    recovery.add_argument("admission", type=Path)
    values = vars(parser.parse_args())
    mode = values.pop("mode")
    {"admission": preflight, "saved-pair": saved_pair, "saved-worker": saved_worker, "recover-audit": recover_audit}[mode](**values)
