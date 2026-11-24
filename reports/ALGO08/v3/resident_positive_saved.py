"""Run the ordinary named and combined solvers on one signed physical range."""

import argparse
from contextlib import nullcontext
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from resident_positive_pair import DENSE, TAKE_SEGMENTS, inventory, read_pinned


PARENT = Path("/dev/shm/leo-held-anchor-selected-dense-01")
PARENT_SHA = "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502"
COMBINED = Path("/dev/shm/leo-v3-dense-hybrid-combined-result01/binding.json")
COMBINED_SHA = "5145340dc4851b1668779566fef0a88411a02ad5d54db64b3d6124bec028d9bf"
ORDER = ("stock", "candidate")
RANGE = (0, 1024)
KIND = "saved physical detector range, no waveform acquisition"


def clip(parent, original_inventory, parent_digest):
    from leo.contracts.digests import canonical_digest

    stop = RANGE[1]
    source, audit = parent["source"], parent["provenance"]
    parts = original_inventory["segments"][:TAKE_SEGMENTS]
    if (sum(part["windows"] for part in parts) != stop or
            original_inventory["window_count"] != audit["window_count"] or len(parent["delivery_clocks"]) != audit["window_count"]):
        raise ValueError("Archived parent does not cover the prespecified complete segment range")
    selected = [row for row in source["probes"] if row["visit_index"] < stop]
    excluded = [row for row in audit["excluded_windows"] if row["visit"] < stop]
    omitted = {row["visit"] for row in excluded}
    wanted = [(visit, radio) for visit in range(stop) if visit not in omitted for radio in (0, 1)]
    if [(row["visit_index"], row["receiver_id"]) for row in selected] != wanted or stop-1 in omitted:
        raise ValueError("Clipping would alter the issued physical chronology")
    sample_hz = source["sample_rate_hz"]
    frame = sample_hz * source["probe_ms"] // 1000
    if source["probe_ms"] != 20 or any(row["probe_start_ms"] or row["probe_index"] for row in selected):
        raise ValueError("The retained range must keep its original complete stereo opportunities")
    endpoint = selected[-1]["valid_start_counter"] + frame
    parent_inventory = canonical_digest(original_inventory)
    derived = dict(original_inventory, window_count=stop, segments=parts,
                   recording_name=original_inventory["recording_name"] + "-saved-visits-0000-1023")
    new_inventory = canonical_digest(derived)
    session = "fast-" + new_inventory[7:39]
    witness = dict(kind="physical-saved-receiver-range-v1", range=list(RANGE), original_native=parent_digest,
                   original_raw_authority=source["raw_recording_authority_digest"], parent_inventory=parent_inventory,
                   derived_inventory=new_inventory, selected_probes=canonical_digest(selected),
                   original_detector=audit["detector_sha256"], last_sample_counter=endpoint,
                   causal_cutoff_utc_ns=parent["clock_anchor"]["before"]["realtime_ns"])
    authority = canonical_digest(witness)
    analysis = canonical_digest(["cancellation", authority, audit["detector_sha256"][7:], selected])
    native = dict(parent, last_sample_counter=endpoint, delivery_clocks=parent["delivery_clocks"][:stop],
                  source=dict(source, session_id=session, input_manifest_sha256=new_inventory,
                              raw_recording_authority_digest=authority, analysis_manifest_sha256=analysis, probes=selected),
                  provenance=dict(audit, run_id="blind-compact-"+analysis[7:39], window_count=stop,
                                  processed_windows=len(selected)//2, invalid_capture=len(excluded), excluded_windows=excluded))
    return native, derived, witness


def worker(job, mode, output):
    import empty_bootstrap as staged
    from aperture_trial import read, write
    from combined_raw_research import Portable, combined_runtime, rank_status

    binding = read(job)
    portable = binding["portable"]
    orbit, rank = {"requested": "portable"}, {"requested": mode == "candidate"}
    runtime = combined_runtime(orbit, rank, Portable(Path(portable["file"]), portable["artifact"], portable["producer"]),
                               use_blocks=True) if mode == "candidate" else nullcontext()
    with runtime:
        _, specification, _, publication, _ = staged.load_runtime()
        from leo.contracts.digests import canonical_digest
        from leo.operations.tle_archive import TleArchiveReader
        from leo.storage.fast_scan import FastScanStore, FastSegmentSource
        from leo.storage.short_window import ShortWindowReader
        import joint_publication as joint
        from prospective_0316_solver import denied
        from short_graph_guard import prove
        import unified_short_bootstrap as unified

        native = read_pinned(Path(binding["packet"]), binding["native_sha256"])
        document = read_pinned(Path(binding["inventory_file"]), binding["inventory_sha256"])
        recording = output.parent / document["recording_name"]
        detector = binding["witness"]["original_detector"][7:]
        session = native["source"]["session_id"]
        staged.bind_native(native, session, binding["inventory_sha256"], detector, expected=binding["native_sha256"])
        if (native["source"]["raw_recording_authority_digest"] != canonical_digest(binding["witness"])
                or native["clock_anchor"]["before"]["realtime_ns"] != binding["witness"]["causal_cutoff_utc_ns"]):
            raise ValueError("Saved range is detached from its derivation receipt")
        archive = Path(binding["archive"]["root"])
        original_read = TleArchiveReader.read

        def archive_read(reader, snapshot):
            if reader.root != archive or not snapshot.path.resolve(strict=True).is_relative_to(archive):
                raise ValueError("Use only the original local causal archive")
            return original_read(reader, snapshot)

        def only_range(_, path, *, verify_windows=True):
            if verify_windows or path != recording:
                raise ValueError("The detached inventory has no waveform authority or other scope")
            return session, binding["inventory_sha256"], document

        handoff = unified.Handoff(session, binding["inventory_sha256"], detector, native)
        options = SimpleNamespace(recording=recording, archive=archive, region=Path(binding["offer"]), output=output,
                                  **{k: Path(v) for k, v in binding["libraries"].items()},
                                  **{flag[2:].replace("-", "_"): True for flag in binding["flags"]})
        run = partial(joint.run, detector_override=denied, detector_description=KIND)
        graph, image, layout, guard = {}, {}, {}, None
        with (patch.object(FastScanStore, "inventory", only_range), patch.object(FastSegmentSource, "windows", denied),
              patch.object(ShortWindowReader, "windows", denied), patch.object(TleArchiveReader, "read", archive_read)):
            if mode == "stock":
                opts = SimpleNamespace(recording=recording, archive=archive, region=options.region, output=output,
                                       verify_images=True, stock_control=True, saved=None, saved_digest=None)
                with patch.object(joint, "configuration", return_value=(publication, dict(specification, startup="stock"))):
                    result = run(opts, raw_context=handoff.install, keep_selected_rows=True)
            else:
                guard = prove(native, staged.RELEASE / "assets", use_time_support=True, use_curvature_extent=True)
                with patch.object(joint, "run", run):
                    _, result = unified.publish_active(options, publication, specification, handoff, layout, graph_audit=graph,
                                                       png_read_audit=image, no_active_curvature_sha256=guard.get(
                                                           "curvature_extent", {}).get("native_sha256"))
        if handoff.calls != 1 or result["input"] != KIND:
            raise ValueError("Exactly one saved-only handoff must reach the original publication boundary")
    write(output / "saved-range-worker.json", dict(input=KIND, handoffs=handoff.calls, waveform_opens=0, guard=guard,
                                                   orbit=orbit, rank=rank_status(rank["requested"], rank), rank_counts=rank,
                                                   png_readback=image, layout=layout, graph=graph,
                                                   named_finish=result.get("named_survivor_finish"), receipt=result["receipt"]))


def prepare(root, raw_admission):
    from aperture_trial import archive_identity, read, write
    from dense_hybrid_combined import compatible_producer
    from dense_geographic_trial import host
    from empty_bootstrap import bind_native, checked
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import immutable_json

    admission = read(raw_admission)
    if any(case["admitted"] for case in (*admission["complete"].values(), admission["dense_prefix"])):
        raise ValueError("Use the authorized original waveform path if eligible")
    if root.parent.resolve(strict=True) != Path("/dev/shm"):
        raise ValueError("Keep all derived saved artifacts in scratch tmpfs")
    request = read_pinned(PARENT / "request.json", PARENT_SHA)
    original = request["original"]
    native = read_pinned(Path(original["file"]), original["native_sha256"])
    parent_inventory = inventory(DENSE)
    bind_native(native, request["session"], request["inventory"], original["detector"], expected=original["native_sha256"])
    archive = Path(request["archive"]["root"])
    if (request["inventory"] != "sha256:"+DENSE[1] or archive_identity(archive)["snapshots_sha256"] != request["archive"]["snapshots_sha256"]
            or not archive.resolve(strict=True).is_relative_to(Path("/dev/shm"))
            or native["source"]["raw_recording_authority_digest"] != request["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]):
        raise ValueError("The signed local original physical packet or causal archive changed")
    checked(Path(request["offer"]), request["offer_sha256"])
    combined = read_pinned(COMBINED, COMBINED_SHA)
    portable = combined["portable"]
    file = Path(portable["file"])
    checked(file, portable["artifact"][7:])
    producer = read_pinned(file.parent / "artifact-bind.json", portable["producer"])
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (producer["portable_sha256"] != portable["artifact"] or
            not compatible_producer(producer["source"], request, [ref.sha256 for ref in refs]) or
            any(ref.collected_utc_ns >= request["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("The same-cutoff dense portable pack must contain only the enrolled pre-RF archive")
    from combined_frontier_run import BLOCK_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    pins = dict(geographic_library=GEOGRAPHIC_SHA, regional_track_library=TRACK_SCORES_SHA,
                frontier_block_library=BLOCK_SHA, grid_feature_projection_library=LIBRARY_SHA)
    for name, path in combined["libraries"].items():
        checked(Path(path), pins[name])
    (HERE / "grid_feature_projection.c").stat()
    git = ["git", "-C", str(HERE.parents[2])]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("The enrolled source must be committed")
    native, derived, witness = clip(native, parent_inventory, original["native_sha256"])
    root.mkdir()
    (root / "tmp").mkdir()
    shutil.copytree(PARENT / "fonts", root / "fonts")
    packet, inventory_file = root / "saved-range.json", root / "saved-range-inventory.json"
    immutable_json(packet, native)
    immutable_json(inventory_file, derived)
    binding = dict(machine=host(), case="DS30-0008", witness=witness, native_sha256=canonical_digest(native),
                   inventory_sha256=canonical_digest(derived), original_request_sha256=PARENT_SHA, portable=combined["portable"],
                   source_sha256={name: sha256((HERE/name).read_bytes()).hexdigest() for name in
                                  (Path(__file__).name, "resident-positive-pair-protocol.md", "unified_short_bootstrap.py",
                                   "joint_publication.py", "combined_raw_research.py", "grid_feature_projection.c")},
                   archive=request["archive"], offer=request["offer"], offer_sha256=request["offer_sha256"],
                   flags=[f for f in combined["flags"] if f != "--catalogue-block-rank"],
                   commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                   issued=RANGE[1], conditioned_waveform_bytes=0, physical_waveform_bytes_read=0, order=list(ORDER),
                   libraries=combined["libraries"], library_sha256=pins, packet=str(packet), inventory_file=str(inventory_file),
                   passive_admission_sha256=sha256(raw_admission.read_bytes()).hexdigest(),
                   admitted=native["provenance"]["processed_windows"],
                   span_s=(native["last_sample_counter"]-native["clock_anchor"]["sample_counter"])/native["source"]["sample_rate_hz"])
    write(root / "binding.json", binding)


def measure_child(root, mode, label):
    from aperture_trial import RELEASE, write
    from eight_ms_south_transfer import environment_for
    from short_raw_diagnostic import measure

    output = root / label
    clock_path = root / (label+"-clock.json")
    if output.exists() or clock_path.exists():
        raise ValueError("Choose a fresh child scope")
    command = ["/usr/bin/timeout", "--kill-after=2s", "45s", RELEASE / "venv/bin/python",
               "-IB", Path(__file__).resolve(), "worker", root / "binding.json", mode, output]
    clock = measure(command, environment_for(root), output)
    write(clock_path, dict(**clock, command=list(map(str, command))))


def launch(root):
    from aperture_trial import read
    from dense_geographic_trial import host

    job = root / "binding.json"
    binding = read(job)
    if binding["machine"] != host():
        raise ValueError("Use the enrolled host and resource scope")
    for mode in ORDER:
        measure_child(root, mode, mode)


def recover_metadata(root):
    from aperture_trial import read
    from dense_geographic_trial import host

    clock = read(root / "candidate-clock.json")
    trace = read(root / "candidate" / "joint-research-receipt.json")
    if (read(root / "binding.json")["machine"] != host() or clock["exit_code"] != 1
            or trace["receipt"]["decision"] != "complete" or "FileNotFoundError" not in clock["stderr_tail"]
            or "grid_feature_projection.c" not in clock["stderr_tail"]):
        raise ValueError("This recovery requires the specific missing tracked source receipt failure")
    (HERE / "grid_feature_projection.c").stat()
    measure_child(root, "candidate", "candidate-recovery")


def grid_identity(grid):
    return {key: value for key, value in grid.items() if key != "elapsed_seconds"}


def score(root, *, recovered=False):
    from aperture_trial import read, write
    from contiguous_third import calibration_owners
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file
    from prospective_0316_solver import owner_delta
    from triage_bounds import calibration_comparison

    binding = read(root / "binding.json")
    native = read_pinned(Path(binding["packet"]), binding["native_sha256"])
    results = {}
    for mode in ORDER:
        label = "candidate-recovery" if recovered and mode == "candidate" else mode
        clock = read(root / (label + "-clock.json"))
        results[mode] = dict(clock=clock)
        if clock["exit_code"]:
            continue
        out = root / label
        sealed = read(out / "saved-range-worker.json")
        trace = read(out / "joint-research-receipt.json")
        receipt = sealed["receipt"]
        terminal = read(out / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
        figures = artifacts(out, receipt)
        if (terminal["native_sha256"] != binding["native_sha256"] or receipt["window_count"] != binding["issued"]
                or receipt["counts"]["processed"] != binding["admitted"]
                or canonical_digest(terminal) != receipt["terminal_sha256"] or sealed["waveform_opens"] != 0
                or native_file(out).read_bytes() != Path(binding["packet"]).read_bytes()
                or canonical_digest(figures) != canonical_digest(trace["evidence"])):
            raise ValueError("Saved scientific outcome or figure readback changed")
        calibration_owners(native, trace["selected_rows"])
        results[mode].update(terminal=terminal, worker=sealed, selected_rows=trace["selected_rows"],
                             solve=trace["solve"], figures=figures, decision=receipt["decision"])
    complete = all(arm.get("decision") == "complete" for arm in results.values())
    accuracy = calibration_comparison({mode: row["terminal"] for mode, row in results.items()
                                       if row.get("decision") == "complete"}, "DS30-0008")
    owners = {arm: owner_delta(*(row["selected_rows"][arm] for row in results.values()))
              for arm in ("c0", "fitted_c")} if complete else None
    failed = {}
    if recovered:
        prior_store, current_store = (FastStandardAnalysisStore(root / name) for name in ("candidate", "candidate-recovery"))
        prior = read(root / "candidate" / "joint-research-receipt.json")
        run = prior["receipt"]["run_id"]
        prior_figures = artifacts(root / "candidate", prior["receipt"])
        current_figures = results["candidate"]["figures"]
        if canonical_digest(prior_figures) != canonical_digest(prior["evidence"]):
            raise ValueError("The first candidate's scientific products changed")
        failed = dict(clock=read(root / "candidate-clock.json"), figures=prior["evidence"],
                      same_published_terminal=prior["receipt"]["terminal_sha256"] ==
                      results["candidate"].get("worker", {}).get("receipt", {}).get("terminal_sha256"),
                      same_published_figures=prior_figures["images"] == current_figures["images"],
                      same_position_path=prior_figures["path"] == current_figures["path"],
                      same_position_grid=grid_identity(prior_store.position_grid(run)) ==
                      grid_identity(current_store.position_grid(run)),
                      same_ordered_owners=prior["selected_rows"] == results["candidate"]["selected_rows"],
                      first_solve_cpu_s=prior["solve"]["cpu_s"],
                      grid_projection_source_sha256=sha256((HERE/"grid_feature_projection.c").read_bytes()).hexdigest())
    write(root / ("verified-result.json" if recovered else "result.json"),
          dict(binding=binding, results=results, both_positive=complete, accuracy=accuracy, owners=owners,
               first_candidate_metadata_failure=failed))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("prepare", "launch", "worker", "score", "recover-metadata", "score-recovered"))
    cli.add_argument("root", type=Path)
    cli.add_argument("inputs", nargs="*")
    args = cli.parse_args()
    if args.action == "worker":
        worker(args.root, args.inputs[0], Path(args.inputs[1]))
    elif args.action == "prepare":
        prepare(args.root, Path(args.inputs[0]))
    elif args.action == "recover-metadata":
        recover_metadata(args.root)
    elif args.action == "score-recovered":
        score(args.root, recovered=True)
    else:
        (launch if args.action == "launch" else score)(args.root)
