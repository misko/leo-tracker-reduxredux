"""Run the second bounded compatible-archive reader pair and score its withhold."""

import argparse
from pathlib import Path

from visit_frame_raw_0016 import ORDER, command, checked, digest, read, resident
from visit_frame_raw_score import branch_science, native_science, writer_times


HERE = Path(__file__).resolve().parent
ROOT = Path("/dev/shm/leo-v3-frame-visit-0107-recording01")
REFERENCE = Path("/dev/shm/leo-v3-history-risk-0107-cairo-result01")
BASE = Path("/dev/shm/leo-v3-history-risk-0107-cairo-score02.json")
BASE_PIN = "sha256:6f6923e6a4be803069581d5a254148c6e322d9e0c4ea4e93de1062dd2bb485e9"
AUTHORITY = "sha256:007f71e30f97fd6b43e5b7e1e3c6cd76f25616ab6abd07926226ea0249397fb7"
WRITER = "sha256:e979a7fc92be2ea767df087b177387b532a3337b50059f29428de50a17b6aa3e"
SOURCES = (Path(__file__).name, "visit-frame-raw-0107-protocol.md", "visit_frame_input.py", "visit_frame_reader.py",
           "exact_named_raw.py", "visit_frame_raw_0016.py", "visit_frame_raw_score.py")


def admitted():
    from exact_named_raw import staged_path
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader
    from visit_frame_input import CHUNK_FIELDS, bind_inventory, custody

    baseline = checked(BASE, BASE_PIN)
    request = baseline["admission"]["request"]
    authority = staged_path(ROOT/"capture-authority.json")
    writer = checked(staged_path(ROOT/"receipt.json"), WRITER)
    recording = staged_path(Path(writer["new_recording"]))
    plan = custody(authority, AUTHORITY, recording)
    session, manifest, inventory = FastScanStore(ROOT).inventory(recording, verify_windows=False)
    bind_inventory(plan, session, manifest, inventory)
    (segment,) = plan["segments"]
    (member,) = segment["members"]
    folder = recording/segment["directory"]
    reader = ShortWindowReader(folder)
    (chunk,) = reader.manifest.chunks
    (back,) = writer["readback"]["seek_checks"]
    if (writer["case"] != "DS30-0107" or writer["capture_authority_sha256"] != AUTHORITY
            or writer["original_inventory_sha256"] != request["inventory"] or writer["original_raw_authority"] != request["authority"]
            or writer["source_custody_sha256"] != "81a5aa37a01356e56619945b194c831314fdf856175c55a1f90492b2585d6260"
            or writer["payload_extent_counts"] != [[0, 1], [1094856, 1], [1600000, 27]]
            or (plan["window_count"], back["counts"]["prefix_checks"]) != (29, 29)
            or any(plan[name] != writer["readback"][name] for name in ("window_count", "raw_authority", "session_id", "inventory_sha256"))
            or any(member[key] != getattr(chunk, key) for key in CHUNK_FIELDS)
            or any(segment["lifecycle"][key] != segment["original_lifecycle"][key] for key in ("failure", "status", "stop_reason"))):
        raise ValueError("Require the detached, independently read back exact original 29 opportunities")
    files = [authority, *(staged_path(folder/name, root=recording) for name in (
        "manifest.json", chunk.index_relative_path, chunk.payload_relative_path, member["side_name"]))]
    return baseline, request, writer, plan, files


def launch(output):
    import shutil
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import clock, now
    from exact_named_raw import parser, staged_path
    from leo.operations.tle_archive import TleArchiveReader
    from raw_0016_best_trial import measure_mode
    from short_raw_diagnostic import require_warm
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    if output.parent != Path("/dev/shm") or output.exists():
        raise ValueError("Use fresh private tmpfs output")
    start = now()
    machine = host()
    baseline, request, writer, plan, files = admitted()
    archive = staged_path(Path(request["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != 51 or archive_identity(archive) != request["archive"]
            or any(ref.collected_utc_ns >= request["cutoff_utc_ns"] for ref in refs)
            or digest(staged_path(Path(request["region"]))) != "sha256:"+request["offer_sha256"]):
        raise ValueError("The original cutoff and offer must survive the capture conversion")
    tles = [staged_path(ref.path, root=archive) for ref in refs]
    before = resident(tles)
    require_warm(resident(files))
    output.mkdir(mode=0o700)
    (output/"tmp").mkdir()
    shutil.copytree(REFERENCE/"fonts", output/"fonts")
    commands = {mode: command(baseline["admission"]["command"], mode, Path(plan["recording"]), output/mode,
                              ROOT/"capture-authority.json", AUTHORITY) for mode in ORDER}
    for mode, argv in commands.items():
        flags = parser().parse_args(argv[6:])
        if not (flags.history_risk_route and flags.cairo_six_sheets and bool(flags.visit_frame_custody) == (mode == "frames")):
            raise ValueError("The actual research CLI did not activate the matched tiny pair")
    write(output/"admission.json", dict(power=machine, writer=writer, writer_sha256=WRITER, authority_sha256=AUTHORITY,
          historical_cairo_sha256=BASE_PIN, request=request, source=plan, clocks=dict(setup=clock(start)),
          commands=commands, causal_before=before, source_sha256={name: digest(HERE/name) for name in SOURCES}))
    for mode in ORDER:
        measure_mode(output, mode, commands[mode], environment_for(output), lambda: resident(files), require_success=False)
    write(output/"causal-after.json", resident(tles))
    write(output/"sealed.json", {name: digest(output/name) for name in (
        "admission.json", "ordinary-clock.json", "frames-clock.json", "causal-after.json")})


def proof(raw):
    result = branch_science(raw["graph_proof"])
    if result["curvature_extent"].pop("native_sha256") != raw["native_sha256"]:
        raise ValueError("Graph proof must bind its own exact signed native document")
    return result


def score(output):
    from aperture_trial import write
    from empty_bootstrap import bind_native
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence

    admitted = read(output/"admission.json")
    if (admitted["source_sha256"] != {name: digest(HERE/name) for name in SOURCES}
            or any(digest(output/name) != pin for name, pin in read(output/"sealed.json").items())):
        raise ValueError("Admission or sealed tiny process clocks changed")
    base = checked(BASE, BASE_PIN)
    old = base["optional_0107"]["bootstrap"]
    historical, = (REFERENCE/"candidate/fast-scan-automatic-work").glob("*/detections.json")
    old_packet = checked(historical, old["native_sha256"])
    readouts = {}
    for mode in ORDER:
        log = read(output/f"{mode}-clock.json")
        row = readouts[mode] = {"log": log}
        if log["clock"]["exit_code"]:
            continue
        folder = output/mode
        raw = read(folder/"unified-short-bootstrap.json")
        plan, req = admitted["source"], admitted["request"]
        receipt = raw["receipt"]
        packet, = (folder/"fast-scan-automatic-work").glob("*/detections.json")
        native = checked(packet, raw["native_sha256"])
        bind_native(native, plan["session_id"], plan["inventory_sha256"], req["detector"][7:])
        published = evidence(folder, receipt, log["clock"]["started_unix_ns"], read_only=True)
        store = FastStandardAnalysisStore(folder)
        if (receipt["decision"] != "withheld" or published["reason"] != "no_active_curvature"
                or published["artifacts"] or store.position_path(receipt["run_id"]) is not None
                or store.position_grid(receipt["run_id"]) is not None or any(folder.rglob("*.png"))
                or published["arms"] != {arm: dict(latlon=None, rf_rms_hz=None) for arm in ("c0", "fitted_c")}
                or raw["scientific_imports_before"] or raw["scientific_imports_after"] or raw["raw_acquisitions"] != 1
                or raw["verified_handoffs"] != 1 or raw["causal_cutoff_utc_ns"] != req["cutoff_utc_ns"]
                or raw["requested_offer_sha256"] != req["offer_sha256"] or raw["archive_root"] != req["archive"]["root"]
                or receipt["window_count"] != 29 or receipt["counts"] != dict(processed=27, invalid_capture=2, skipped_fast_score=0)
                or published["raw_authority"] != plan["raw_authority"] or native_science(native) != native_science(old_packet)
                or proof(raw) != proof(old)):
            raise ValueError("The new encoding changed the original complete scientific withhold")
        visit = folder/"visit-frame-acquisition.json"
        audit = read(visit) if visit.exists() else None
        if bool(audit) != (mode == "frames"):
            raise ValueError("Unexpected selective-reader activation")
        if audit:
            (member,) = audit["members"]
            counts = member["counts"]
            (segment,) = plan["segments"]
            (expected,) = segment["members"]
            if (audit["custody_sha256"] != AUTHORITY or member["manifest_sha256"] != segment["manifest_sha256"]
                    or member["side_sha256"] != expected["side_sha256"] or member["payload_sha256"] != expected["compressed_sha256"]
                    or counts["authenticated_encoded_bytes"] != expected["compressed_bytes"]
                    or counts["full_checks"] != 8 or counts["prefix_checks"] != 19 or counts["decoded_bytes"] != 24960000):
                raise ValueError("Selective reader failed complete authentication and exact 20/8 demand")
        row.update(science=published, acquisition=raw, selective=audit,
                   checks=dict(withholding_reason=True, both_arms_null=True, no_figures_grid_or_path=True,
                               original_graph_and_physical_observations=True, original_cutoff_and_offer=True))
    qualified = all("science" in row for row in readouts.values())
    if qualified:
        before, after = (readouts[mode]["acquisition"] for mode in ORDER)
        qualified = before["native_sha256"] == after["native_sha256"] and before["receipt"] == after["receipt"]
    write(output/"result.json", dict(qualified=qualified, case="DS30-0107", admission=admitted, arms=readouts,
        measured_children={mode: row["log"] for mode, row in readouts.items()},
        historical_named=base["clocks"]["DS30-0107"]["stock"], historical_ordinary_cairo=base["clocks"]["DS30-0107"]["candidate"],
        writer_costs=writer_times(admitted["writer"]), original_and_new_withheld_parity=qualified, named_reruns=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    (launch if args.action == "launch" else score)(args.output)
