"""Run and verify the normal no-plan first-use route on the resident North simulation."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
RECEIPTS = {
    "legacy-first-use-original-panel": "edbaa35c4b18e9f593d1d7f7ac7928a1d6e65bc259d8e46a385c645fdb3f684d",
    "history-risk-raw": "ff335cb69524253255168c93138497639e3342ab615a602d0d502aab873ff75b",
    "strict-history-raw": "a11e30e13129f95e1d944b0c966ed06ffbdb15a0894fc2637fcda4edfc5742a5",
    "current-north-control": "f6d27d8a834ab078dddfb6486082b5aa397e72577b249fc319640d476e788614",
}
ENTRY = "legacy_first_map_entry.py"
LIBRARIES = ("--short-binary", "--geographic-library", "--regional-track-library", "--frontier-block-library")
MAP_BINARIES = {
    "history": Path("/dev/shm/leo-v3-first-map-pytest/history0/history.so"),
    "replay": Path("/dev/shm/leo-v3-first-map-pytest/test_first_use_map_reopens_fro0/replay.so"),
}


def archived(name):
    from empty_bootstrap import checked

    return json.loads(gzip.decompress(checked(HERE / "measurements" / f"{name}.json.gz", RECEIPTS[name])))


def controls():
    old = archived("history-risk-raw")["raw"]
    job = old["binding.json"]["value"]
    routed = old["verified-result-grid.json"]["value"]
    routed_raw = old["candidate/unified-short-bootstrap.json"]["value"]
    strict = archived("strict-history-raw")["run"]
    readback = strict["result.json"]["value"]
    named = archived("current-north-control")
    if (job["request"] != strict["binding.json"]["value"]["request"]
            or not readback["same_routed_science"] or not all(readback["named"]["checks"].values())
            or not all(named["checked_fields"].values())
            or readback["named"]["native_sha256"] != named["new"]["native_sha256"]
            or any(value["exit_code"] for value in (routed["clock"], readback["clocks"]["named"], named["new"]["clock"]))):
        raise ValueError("The signed controls must agree on the North input and completed publication")
    return job, routed, routed_raw, readback, named


def command_for(template, north, output):
    def option(name, value):
        command[command.index(name) + 1] = str(value)

    command = list(template)
    required = ("--history-risk-route", "--cairo-residual-layout", "--portable-orbit-index",
                "--legacy-first-map-history", "--legacy-first-map-replay")
    forbidden = ("--legacy-first-map-plan", "--legacy-map-", "--visit-frame-", "--packed-ci16-",
                 "--strict-packed-eight", "--cairo-six-sheets", "--research-adaptive-position-map")
    if (Path(command[5]).name != ENTRY or not all(flag in command for flag in required)
            or any(word.startswith(forbidden) for word in command)):
        raise ValueError("Expected the qualified no-plan original entry with the full route")
    command[5] = str(HERE / ENTRY)
    request = north["request"]
    for name, value in (
        ("--recording", request["recording"]), ("--archive", request["archive"]["root"]),
        ("--archive-sha256", request["archive"]["snapshots_sha256"]),
        ("--region", request["inside_offer"]), ("--output", output),
    ):
        option(name, value)
    for name, path in MAP_BINARIES.items():
        option("--legacy-first-map-" + name, path)
    for flag in LIBRARIES:
        if command[command.index(flag) + 1] != north["command"][north["command"].index(flag) + 1]:
            raise ValueError("Receiver or solver library differs from the frozen North control")
    return command


def source_pins():
    from legacy_first_map_0016 import runtime_pins

    names = (Path(__file__).name, "legacy-first-map-north-protocol.md", "legacy_first_map_panel.py")
    return runtime_pins() | {f"reports/ALGO08/v3/{name}": sha256((HERE / name).read_bytes()).hexdigest() for name in names}


def admit(root):
    from adaptive_raw_trial import control, work
    from combined_raw_trial import checked_producer
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from exact_named_raw import staged_path
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore
    from reports.ALGO08.v3 import legacy_block_input as ports
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot, load_query
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    historical, _, _, strict, _ = controls()
    previous, launch, _, _ = control("north")
    before_request = historical["request"]
    recording = staged_path(Path(before_request["recording"]))
    archive = staged_path(Path(before_request["archive"]["root"]))
    offer = staged_path(Path(before_request["inside_offer"]))
    checked(offer, before_request["inside_offer_sha256"])
    # Authenticate path confinement for every leaf before any waveform probe.
    manifest_path = staged_path(recording / "manifest.json", root=recording)
    (declared,) = before_request["manifests"]
    if staged_path(Path(declared["path"]), root=recording) != manifest_path:
        raise ValueError("Expected the original signed single-segment North archive")
    manifest = json.loads(checked(manifest_path, declared["digest"].removeprefix("sha256:")))
    paths = [
        staged_path(recording / chunk[field + "_relative_path"], root=recording)
        for chunk in manifest["chunks"] for field in ("index", "payload")
    ]
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    bodies = [staged_path(row.path, root=archive) for row in refs]
    if archive_identity(archive) != before_request["archive"]:
        raise ValueError("Original North causal archive changed")
    request, cache = work("north", root)
    machine = host()
    if (request != before_request or request != launch["request"]
            or machine != historical["machine"]
            or request["compressed_bytes"] != strict["original_input"]["compressed_bytes"]):
        raise ValueError("Original resident requests or the matched worker settings changed")
    session, inventory_pin, inventory = FastScanStore(root).inventory(recording, verify_windows=False)
    original = [ports.member_identity(reader, chunk) for reader, chunk in ports.ordered_members(inventory)]
    if ((session, inventory_pin, inventory["window_count"], len(original), sum(r["windows"] for r in original))
            != (request["session"], request["inventory"], 1200, 19, 1200)):
        raise ValueError("The complete original North geometry changed")
    matching = {row.sha256 for row in refs if row.collected_utc_ns < request["cutoff_utc_ns"]}
    producer = checked_producer(request["cutoff_utc_ns"], matching)
    if not producer["overlapping_bodies"]:
        raise ValueError("Portable orbit producer has no eligible causal bodies")
    physical = archived("legacy-first-use-original-panel")["admission"]["commands"]["DS30-0016"]
    command = command_for(physical, historical, root / "candidate")
    for name in MAP_BINARIES:
        flag = "--legacy-first-map-" + name
        path = staged_path(Path(command[command.index(flag) + 1]))
        checked(path, command[command.index(flag + "-sha256") + 1].removeprefix("sha256:"))
    for flag in LIBRARIES:
        item = launch["libraries"][flag]
        checked(Path(item["path"]), item["sha256"])
    checked(CACHE_LIB, CACHE_SHA)
    catalogue = cache_snapshot([(path.parent, path.name, row.byte_size) for path, row in zip(bodies, refs, strict=True)],
                               os.sysconf("SC_PAGE_SIZE"), load_query(CACHE_LIB))
    if catalogue["unavailable"] or catalogue["observed_members"] != len(bodies):
        raise ValueError("The original tmpfs catalogue cannot be observed")
    bindings = dict(request=request, originals=original, machine=machine, references=RECEIPTS,
                    command=command, sources=source_pins(), producer=producer, prior_maps_read=0,
                    archives=dict(catalogue=catalogue, cached=cache(), recording_leaves=len(paths) + 1))
    return bindings, cache, previous / "fonts"


def launch(root):
    from aperture_trial import write
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import clock, now
    from frame_portable_0016 import seal
    from short_raw_diagnostic import measure

    if root.parent.resolve() != Path("/dev/shm") or root.exists():
        raise ValueError("The one complete candidate requires a new tmpfs destination")
    started = now()
    book, cache, fonts = admit(root)
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir()
    shutil.copytree(fonts, root / "fonts")
    prep = clock(started)
    probe_start = now()
    probe = subprocess.run([*book["command"], "--first-map-setup-only"], env=environment_for(root),
                           capture_output=True, text=True, timeout=15)
    setup = clock(probe_start)
    write(root / "probe.json", dict(clock=setup, exit_code=probe.returncode, stdout=probe.stdout, stderr=probe.stderr))
    probe.check_returncode()
    witness = json.loads(probe.stdout)
    if (not witness["reached_scanner"] or witness["waveform_opens"]
            or witness["audit"]["authority_mode"] != "verified-first-use" or (root / "candidate").exists()):
        raise ValueError("The real first-use scanner must pass the waveform-blocked setup")
    elapsed_setup = clock(started)
    write(root / "admission.json", book | {"preparation": prep, "setup_through_probe": elapsed_setup})
    result = measure(book["command"], environment_for(root), root / "candidate")
    write(root / "clock.json", result)
    write(root / "cache-after.json", cache())
    write(root / "prediction-seal.json", seal(root))
    if result["exit_code"]:
        raise RuntimeError(result["stderr_tail"])


def maps(root, book):
    from reports.ALGO08.v3 import legacy_block_input as port, legacy_block_multi as multi, legacy_block_seek as core
    from visit_frame_raw_0016 import read

    audit = read(root / "legacy-first-map-acquisition.json")
    bundle = root / "legacy-first-maps"
    request = book["request"]
    pin = audit["plan_sha256"]
    plan = port.load_custody(bundle / "custody.json", pin)
    if ((plan["session"], plan["inventory"], plan["raw_authority"], plan["windows"])
            != (request["session"], request["inventory"], request["authority"], 1200)
            or audit["finished_raw_authority"] != request["authority"]
            or audit["authority_mode"] != "verified-first-use"):
        raise ValueError("Fresh maps do not bind the complete independently signed North source")
    expected_files = {"custody.json"}
    for index, (row, observed, original) in enumerate(zip(plan["members"], audit["members"], book["originals"], strict=True)):
        if (any(row[k] != v for k, v in original.items()) or any(observed[k] != v for k, v in row.items())):
            raise ValueError("The published map plan changed a signed member or its issuance order")
        if row["map_kind"] == "ordinary":
            if row["map"] or row["map_sha256"] or not (observed.get("fallback") or observed.get("verified_without_map")):
                raise ValueError("Ordinary fallback needs its actual authenticated reason with no detached entry")
            continue
        name = port.map_name(index)
        if row["map"] != name or observed["proof"]["original_encoded_reused"] != row["encoded"]:
            raise ValueError("Expected one independent ready reopen on the authenticated original snapshot")
        expected_files.add(name)
        data = port.checked_file(bundle / name, row["map_sha256"],
                                 multi.MAX_SIDECAR if row["map_kind"] == "exception" else core.MAX_MAP)
        if len(data) != observed["map_bytes"] or observed["proof"]["prefix_bytes"] != 640_000:
            raise ValueError("A sealed replay map or its first original prefix differs")
    if {path.name for path in bundle.iterdir()} != expected_files:
        raise ValueError("Fresh custody has unexpected or incomplete sidecars")
    kinds = dict(Counter(row["map_kind"] for row in plan["members"]))
    return dict(plan=plan, audit=audit, kinds=kinds, bundle_bytes=sum(path.stat().st_size for path in bundle.iterdir()))


def score(root):
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from aperture_trial import write
    from exact_named_raw_transfer import authenticate_packet
    from frame_portable_0016 import seal
    from history_risk_cairo_0402 import ORBIT_SHEETS
    from history_risk_residual_layout_0402 import media_identity, require_active
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from publication_media_checks import verify_position_sidecars
    from tools.pipeline_eval.qualification.paired_publication import evidence
    from visit_frame_raw_0016 import read

    book, clock, after = (read(root / name) for name in ("admission.json", "clock.json", "cache-after.json"))
    if (book["sources"] != source_pins() or read(root / "prediction-seal.json") != seal(root) or clock["exit_code"]
            or {k: v["cached_pages"] for k, v in after.items()}
            != {k: v["cached_pages"] for k, v in book["archives"]["cached"].items()}):
        raise ValueError("The frozen one-candidate result, residency or executed source changed")
    old_job, old, old_raw, prior, named = controls()
    req = book["request"]
    candidate = root / "candidate"
    raw = read(candidate / "unified-short-bootstrap.json")
    witness = read(candidate / "exact-named-raw-witness.json")
    receipt = raw["receipt"]
    native = authenticate_packet(candidate, req, old["signed_native"], old_raw["detector_recipe_sha256"][7:])
    independent = evidence(candidate, receipt, clock["started_unix_ns"], read_only=True)
    media = artifacts(candidate, receipt)
    current, before = witness["evidence"], old["witness"]["evidence"]
    immutable = ("native_sha256", "detector_recipe_sha256", "receiver_recipe", "causal_cutoff_utc_ns",
                 "requested_offer_sha256", "archive_root", "raw_acquisitions", "verified_handoffs")
    if (any(raw[key] != old_raw[key] for key in immutable) or raw["scientific_imports_before"]
            or receipt["decision"] != "complete" or receipt["window_count"] != 1200
            or receipt["region"] != old["region"] or receipt["counts"] != old_raw["receipt"]["counts"]
            or independent["raw_authority"] != req["authority"] or set(independent["arms"]) != {"c0", "fitted_c"}
            or independent["receipt"]["terminal_sha256"] != before["detail"]["terminal_sha256"]
            or current["owner_rows"] != before["owner_rows"] or current["detail"]["arms"] != before["detail"]["arms"]
            or current["grid"] != before["grid"] or len(current["images"]) != 8
            or media_identity(current["images"]) != media_identity(media["images"])):
        raise ValueError("Original signed receiver, terminal, ownership or standards publication changed")
    for arm, rows in current["owner_rows"].items():
        if independent["owners"][arm] != canonical_digest({row[0]: row[1] for row in rows}):
            raise ValueError("Ordered owners did not bind their published labels")
    raw_native = raw["receiver_audit"]["native"]
    if raw_native["native_calls"] != {"full": 304, "short_primary": 2096}:
        raise ValueError("Expected two-scan 20 ms anchors and every admitted stereo visit")
    old_argv = old_job["command"]
    old_candidate = Path(old_argv[old_argv.index("--output") + 1])
    sidecars = verify_position_sidecars(old_candidate, candidate, receipt["run_id"], before["images"], current["images"])
    grid = FastStandardAnalysisStore(candidate).position_grid(receipt["run_id"])
    if not grid["complete"] or grid["evaluated_points"] != 137:
        raise ValueError("North transfer requires the full standard ordered numerical grid")
    media_equal = {name: row == media_identity(before["images"])[name]
                   for name, row in media_identity(current["images"]).items()}
    if (any(not media_equal[name] for name in ORBIT_SHEETS) or any(
            current["images"][name]["size"] != old_image["size"] for name, old_image in before["images"].items())):
        raise ValueError("An ordinary orbit sheet or standard PNG extent changed")
    renderer = witness["ports"]["cairo_layout"]
    require_active(renderer)
    if renderer["original_recording_title"] != Path(req["recording"]).name:
        raise ValueError("A standard figure omitted the original recording title")
    (transfer,) = witness["ports"]["portable"]["transfers"]
    if (transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]
            or transfer["sha256"] != book["producer"]["artifact_sha256"]
            or transfer["counts"]["sidecar_hit_bodies"] != book["producer"]["overlapping_bodies"]):
        raise ValueError("The complete North candidate did not use the pinned prior causal orbit data")
    index = maps(candidate, book)
    for lib in ("history", "replay"):
        flag = f"--legacy-first-map-{lib}-sha256"
        if index["audit"][f"{lib}_sha256"] != book["command"][book["command"].index(flag) + 1]:
            raise ValueError("Different map libraries ran from those pinned before launch")
    controls_clocks = dict(routed=old["clock"], installed_readback=prior["clocks"]["named"],
                           installed_postclock_readback=named["new"]["clock"])
    ratios = {name: {key: ref[key] / clock[key] for key in ("elapsed_s", "cpu_s")}
              for name, ref in controls_clocks.items()}
    write(root / "result.json", dict(qualified=True, scope="public North simulation", admission=book, clock=clock,
          cache_after=after, controls=controls_clocks, ratios=ratios, maps=index,
          native=dict(digest=raw["native_sha256"], original=native["source"]["raw_recording_authority_digest"],
                      probes=len(native["source"]["probes"]), audit=raw_native),
          phases=raw["phases"], arms=old["arms"], named_arms=prior["named_arms"],
          terminal_sha256=receipt["terminal_sha256"], owner_rows=current["owner_rows"], sidecars=sidecars,
          images=current["images"], standard_matches=media_equal, render=renderer, portable=transfer,
          prediction_sha256=sha256((root / "prediction-seal.json").read_bytes()).hexdigest()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    {"launch": launch, "score": score}[args.mode](args.root)
