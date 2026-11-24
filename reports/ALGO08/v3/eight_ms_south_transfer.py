"""Time one original South native 8 ms transfer and its saved geographic control."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PROTOCOL = HERE / "eight-ms-south-transfer-protocol.md"
MODES = ("containing", "near-omitted")
ARM_NAMES = ("c0", "fitted_c")
PACKS = {
    "north": ("eight-ms-native-live.json.gz", "2604afe118cebc24fa4fb0a975a439e5a6e9c2858ca4ae793dbc5b7f7afe7b9d"),
    "guarded": ("combined-raw-south.json.gz", "32c61a85609fffbbc4cf23c0c10990f693415fb01593dcac71901de065e6c71d"),
    "mirror": ("south-raw-omitted.json.gz", "5384df7b313f0d8f8300d6743e517f85ead5dd79cf82564364e05d31b0c4051c"),
}
KEY_SHA = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"
SOURCES = ("combined_raw_research.py", "unified_short_bootstrap.py", "eight_ms_native_receiver.py", "eight_ms_held_fit.py",
           "mixed_aperture_receiver.py", "raw_cfo_north_trial.py", "south_cfo_route.py", "catalogue_block_port.py",
           "historical_orbit_index.py", "eight_ms_south_transfer.py", PROTOCOL.name)


def pin(path):
    return sha256(path.read_bytes()).hexdigest()


def archived(label):
    from empty_bootstrap import checked

    file, digest = PACKS[label]
    return json.loads(gzip.decompress(checked(HERE / "measurements" / file, digest)))


def command_for(north, request, output):
    command = list(north["command"])
    if ("--eight-ms-native-history" not in command or "--catalogue-block-rank" not in command
            or any(flag in command for flag in ("--full-anchor-primary-library", "--whole-stereo-blocks",
                                                "--short-lane-mask", "--anchored-cfo-pack", "--select-before-cfo"))
            or Path(command[5]).name != "combined_raw_research.py"):
        raise ValueError("Expected the frozen North all-visit two-scan anchor command")
    command[5] = str(HERE / "combined_raw_research.py")
    for flag, value in (("--recording", request["recording"]), ("--archive", request["archive"]["root"]),
                        ("--region", request["offers"][MODES[0]]), ("--output", output)):
        command[command.index(flag) + 1] = str(value)
    return command


def environment_for(root):
    from full_short_physical import environment

    return environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}


def raw(root):
    from aperture_trial import RELEASE, write
    from combined_raw_trial import checked_producer
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_run import EIGHT_MS_SHA
    from leo.operations.tle_archive import TleArchiveReader
    from north_orbit_index_trial import snapshot_census
    from short_raw_diagnostic import measure
    from south_cfo_route import admissible, assigned, residency

    job, chunks = assigned()
    machine = host()
    all_paths = (root.parent, job["recording"], job["archive"]["root"], job["saved_inventory"], *job["offers"].values())
    if any(subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", p], text=True).strip() != "tmpfs" for p in all_paths):
        raise ValueError("The original South raw and archive scope must be staged tmpfs")
    git = ["git", "-C", str(HERE.parents[2])]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"]).strip():
        raise ValueError("Commit the executing trial before signing the raw request")
    north = archived("north")["raw_binding"]
    if north["libraries"]["--short-binary"]["sha256"] != EIGHT_MS_SHA:
        raise ValueError("Original North native 8 ms pin changed")
    for data in north["libraries"].values():
        checked(Path(data["path"]), data["sha256"])
    archive = TleArchiveReader(Path(job["archive"]["root"]))
    census = snapshot_census(archive.list_snapshots("space-track"), job["cutoff_utc_ns"])
    producer = checked_producer(job["cutoff_utc_ns"], census["72"]["body_digests"])
    root.mkdir()
    (root / "tmp").mkdir()
    env = environment_for(root)
    subprocess.run([RELEASE / "venv/bin/python", "-Bc",
                    "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"], env=env, check=True, timeout=25)
    target = root / MODES[0]
    command = command_for(north, job, target)
    help_text = subprocess.run([*command[:7], "--help"], env=env, capture_output=True, check=True, timeout=10).stdout
    if b"--held-anchor-route" not in help_text or b"--named-survivor-finish" not in help_text:
        raise ValueError("The genuine raw entry did not load the intended receiver and solver options")
    binding = dict(command=command, request=job, machine=machine, libraries=north["libraries"], producer=producer,
                   north_control_sha256=PACKS["north"][1],
                   commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                   sources={name: pin(HERE / name) for name in SOURCES})
    write(root / "binding.json", binding)
    before = residency(chunks)
    write(root / "cache-before.json", before)
    if not admissible(before):
        write(root / "admission.json", dict(resident=False, raw_children=0, warmed_pages=0))
        return
    clock = measure(command, env, target)
    write(root / "clock.json", clock)
    after = residency(chunks)
    write(root / "cache-after.json", after)
    if clock["exit_code"] or not admissible(after):
        raise RuntimeError(clock["stderr_tail"] or "The resident South input changed during the single launch")


def verify_options(root, expected, decision):
    from aperture_trial import read

    ranked, orbits = (read(root / name) for name in ("catalogue-block-rank.json", "orbits-indexed.json"))
    transfers = orbits.get("transfers", [])
    if not transfers and decision != "complete":
        return dict(ranked=ranked, orbits=orbits, reused_orbit_bodies=0)
    (transfer,) = transfers
    if (not ranked["requested"] or transfer["compatibility"]["fallback"] or transfer["loading"]["fallback"]
            or transfer["counts"]["invalid_bodies"] or transfer["counts"]["sidecar_hit_bodies"] != expected):
        raise ValueError("The requested original portable options do not bind the South execution")
    return dict(ranked=ranked, orbits=orbits, reused_orbit_bodies=expected)


def native_probe(root, request):
    from aperture_trial import read
    from empty_bootstrap import bind_native, checked
    from leo.contracts.digests import canonical_digest
    from raw_cfo_north_trial import native_file

    home = root / MODES[0]
    raw = read(home / "unified-short-bootstrap.json")
    file = native_file(home)
    native = json.loads(checked(file, raw["native_sha256"][7:]))
    recipe = raw["receiver_recipe"]
    selection = raw["held_anchor_route"]
    counts = raw["receiver_audit"]
    if (raw["raw_acquisitions"] != 1 or raw["verified_handoffs"] != 1 or raw["causal_cutoff_utc_ns"] != request["cutoff_utc_ns"]
            or raw["requested_offer_sha256"] != request["offer_sha256"][MODES[0]] or raw["archive_root"] != request["archive"]["root"]
            or canonical_digest(recipe) != raw["detector_recipe_sha256"] or recipe["aperture_samples"] != [200_000, 80_000]
            or "full_anchor_primary_only" in recipe or "fixed_epoch_cfo_refinement" in recipe
            or selection["refinement_calls"] or selection["native_sha256"] != raw["native_sha256"]
            or counts["issued"] != request["issued"] or counts["recording_authority"] != request["authority"]
            or counts["native"]["native_calls"] != {"full": 304, "short_primary": 2096}
            or counts["selected"] != selection["observed"]
            or selection["selected"] != sum(bool(p["candidates"]) for p in native["source"]["probes"])
            or native["source"]["raw_recording_authority_digest"] != request["authority"]):
        raise ValueError("The original all-visit 20/8 ms native route and exact selected packet diverge")
    bind_native(native, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:], expected=raw["native_sha256"])
    return file, native, raw


def verified_publication(target, receipt, request, mode, clock, expected_native):
    from aperture_trial import read
    from empty_bootstrap import checked
    from joint_publication import artifacts
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from raw_cfo_north_trial import native_file
    from tools.pipeline_eval.qualification.paired_publication import evidence

    offer = Algo08Region.parse(json.loads(checked(Path(request["offers"][mode]), request["offer_sha256"][mode]))).document()
    observed = evidence(target, receipt, clock["started_unix_ns"], read_only=True)
    checked(native_file(target), expected_native[7:])
    if (clock["exit_code"] or observed["raw_authority"] != request["authority"] or receipt["region"] != offer
            or receipt["session_id"] != request["session"] or receipt["window_count"] != request["issued"]
            or set(observed["arms"]) != set(ARM_NAMES)):
        raise ValueError("Published authority, offers or original RF calibration arms differ")
    media = artifacts(target, receipt)
    research = target / "joint-research-receipt.json"
    report = read(research) if research.exists() else {}
    rows = report.get("selected_rows", {})
    grid_points = None
    if receipt["decision"] == "complete":
        store = FastStandardAnalysisStore(target)
        grid, path = store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"])
        if (len(media["images"]) != 8 or not grid["complete"] or not grid["matched_c_grid"] or set(rows) != set(ARM_NAMES)
                or grid["evaluated_points"] != grid["planned_points"]
                or any(doc["binding"]["position_png_sha256"] != media["images"]["position"]["sha256"] for doc in (grid, path))
                or any(observed["owners"][a] != canonical_digest({uid: norad for uid, norad, _ in rows[a]}) for a in ARM_NAMES)):
            raise ValueError("Incomplete grid, original owner rosters, path or eight PNGs")
        grid_points = grid["evaluated_points"]
    return dict(evidence=observed, media=media, owner_rows=rows, grid_points=grid_points,
                regional=report.get("early_regional"), route=report.get("route_details"), solve=report.get("solve"))


def seal_raw(root):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from south_cfo_route import admissible

    binding, clock = (read(root / name) for name in ("binding.json", "clock.json"))
    for name, sha in binding["sources"].items():
        checked(HERE / name, sha)
    request = binding["request"]
    if not all(admissible(read(root / f"cache-{key}.json")) for key in ("before", "after")):
        raise ValueError("The preserved raw trial must use entirely resident input")
    packet, _native, raw = native_probe(root, request)
    observation = verified_publication(root / MODES[0], raw["receipt"], request, MODES[0], clock, raw["native_sha256"])
    write(root / "seal.json", dict(binding_sha256=pin(root / "binding.json"), packet=str(packet), raw=raw, clock=clock,
          observation=observation, options=verify_options(root, binding["producer"]["overlapping_bodies"], raw["receipt"]["decision"])))


def omitted_worker(root, job_path=None):
    import empty_bootstrap as staged
    from aperture_trial import read, write
    from combined_raw_research import combined_runtime, rank_status
    from combined_raw_trial import PRODUCER
    from raw_cfo_north_trial import ORDER, PUBLICATION_FLAGS, publish_saved

    started = process_time(), perf_counter()
    job = read(job_path or root / "omitted-job.json")
    binding = json.loads(staged.checked(root / "binding.json", job["binding_sha256"]))
    sealed = json.loads(staged.checked(root / "seal.json", job["seal_sha256"]))
    request = binding["request"]
    offer = Path(request["offers"][MODES[1]])
    for row in binding["libraries"].values():
        staged.checked(Path(row["path"]), row["sha256"])
    rank, orbit = {"requested": True}, {"requested": "portable"}
    with combined_runtime(orbit, rank, PRODUCER, use_blocks=True):
        runtime = staged.load_runtime()
        from named_constrained_research import deny_waveform
        from unittest.mock import patch
        from leo.storage.fast_scan import FastSegmentSource

        packet, native, raw = native_probe(root, request)
        if str(packet) != sealed["packet"] or raw["native_sha256"] != job["native_sha256"]:
            raise ValueError("The saved mirror must consume the authentic issued detector")
        request = dict(request, offer_sha256={ORDER[1]: request["offer_sha256"][MODES[1]]},
                       libraries={flag[2:].replace("-", "_"): row["path"] for flag, row in binding["libraries"].items()})
        with patch.object(FastSegmentSource, "windows", deny_waveform):
            publish_saved(request, root / MODES[1], offer, packet, native, raw, started=started, runtime=runtime,
                          receipt_name="saved-south.json", flags=PUBLICATION_FLAGS)
    orbit["adapter_sha256"] = pin(HERE / "historical_orbit_index.py")
    rank["status"] = rank_status(True, rank)
    write(root / MODES[1] / "catalogue-block-rank.json", rank)
    write(root / MODES[1] / "orbits-indexed.json", orbit)


def omitted(root):
    from aperture_trial import RELEASE, read, write
    from short_raw_diagnostic import measure

    result = read(root / "containing-score.json")
    if not result["eligible_omitted"] or result["seal_sha256"] != pin(root / "seal.json"):
        raise ValueError("The one geographic control requires the sealed containing gate")
    seal = read(root / "seal.json")
    target = root / MODES[1]
    label, timing_target = "omitted", target
    if (root / "omitted-job.json").exists():
        prior = read(root / "omitted-clock.json")
        if (target.exists() or prior["exit_code"] != 1 or "ModuleNotFoundError: No module named 'leo'" not in prior["stderr_tail"]):
            raise ValueError("The saved comparison already launched beyond its raw-free initialization")
        label, timing_target = "omitted-recovery", root / "near-omitted-recovery"
    job = root / f"{label}-job.json"
    command = [RELEASE / "venv/bin/python", "-IB", Path(__file__), "omitted-worker", root, "--job-path", job]
    write(job, dict(command=list(map(str, command)), seal_sha256=result["seal_sha256"], source_sha256=pin(Path(__file__)),
                    binding_sha256=seal["binding_sha256"], native_sha256=seal["raw"]["native_sha256"]))
    clock = measure(command, environment_for(root), timing_target)
    write(root / f"{label}-clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    worker = read(target / "saved-south.json")
    request = read(root / "binding.json")["request"]
    if (worker["waveform_calls"] or worker["handoffs"] != 1 or not worker["staged_inventory"]
            or worker["native_sha256"] != seal["raw"]["native_sha256"]):
        raise ValueError("The mirror must use one exact signed packet and zero waveform calls")
    observation = verified_publication(target, worker["receipt"], request, MODES[1], clock, worker["native_sha256"])
    write(root / "omitted-seal.json", dict(clock=clock, saved=worker, observation=observation,
          options=verify_options(target, seal["options"]["reused_orbit_bodies"], worker["receipt"]["decision"])))


def geographic_status(clearance, decision):
    if clearance >= 0:
        return "valid_fix" if decision == "complete" else "false_withhold"
    return "false_fix" if decision == "complete" else "valid_withhold"


def score(root, mode):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import owner_delta
    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    seal_path = root / ("seal.json" if mode == MODES[0] else "omitted-seal.json")
    seal = read(seal_path)
    observation = seal["observation"]
    binding = read(root / "binding.json")
    path = HERE.parent / "regional-release/scoring-key.json"
    keys = json.loads(checked(path, KEY_SHA))
    (truth,) = {tuple(row["truth"]) for row in keys["answers"].values()
                if row["recording"] == Path(binding["request"]["recording"]).name}
    if mode == MODES[0]:
        old = archived("guarded")
        control = old["current"]["arms"]
        named = old["historical_named"]["arms"]
        guarded_owners = old["current"]["owners"]
        guarded_order_pin = old["current"]["ordered_roles_sha256"]
    else:
        old = archived("mirror")
        control, named = old["arms"], old["historical_named"]
        guarded_owners = old["owners"]
        guarded_order_pin = None
    control_path = Path(old["binding"]["command"][old["binding"]["command"].index("--output") + 1])
    guarded_rows = read(control_path / "joint-research-receipt.json")["selected_rows"]
    if (guarded_order_pin and canonical_digest(guarded_rows) != guarded_order_pin) or any(
            canonical_digest({uid: norad for uid, norad, _ in guarded_rows[a]}) != guarded_owners[a] for a in ARM_NAMES):
        raise ValueError("Archived raw guarded 12 ms owner rows differ from sealed digests")
    published = observation["evidence"]
    offer = published["receipt"]["region"]
    truth_clearance = face_clearance_km(offer, truth)
    decision = published["receipt"]["decision"]
    geography = geographic_status(truth_clearance, decision)
    if (mode == MODES[0]) != (truth_clearance >= 0):
        raise ValueError("Read the original public South scoring reference only for the correct offer")
    out = {}
    for label, arms in (("candidate", published["arms"]), ("named_v3", named), ("guarded_12ms", control)):
        out[label] = {a: dict(latlon=row["latlon"], rf_rms_hz=row["rf_rms_hz"], error_km=distance_km(truth, row["latlon"]),
                              depth_km=face_clearance_km(offer, row["latlon"]) if row["latlon"] else None) for a, row in arms.items()}
    eligible = (mode == MODES[0] and geography == "valid_fix" and all(
        out["candidate"][a]["error_km"] - out["named_v3"][a]["error_km"] <= .250 for a in ARM_NAMES))
    write(root / f"{mode}-score.json", dict(seal_sha256=pin(seal_path), mode=mode, decision=decision, geography=geography,
          truth_clearance_km=truth_clearance, positions=out, historical_raw_clock=old["clock"], reference_sha256=KEY_SHA,
          owners_against_guarded={a: owner_delta(guarded_rows[a], observation["owner_rows"].get(a, [])) for a in ARM_NAMES},
          eligible_omitted=eligible))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="action", required=True)
    for action in ("raw", "seal", "score", "omitted", "omitted-worker"):
        command = sub.add_parser(action)
        command.add_argument("root", type=Path)
        if action == "score":
            command.add_argument("mode", choices=MODES)
        if action == "omitted-worker":
            command.add_argument("--job-path", type=Path)
    args = vars(cli.parse_args())
    {"raw": raw, "seal": seal_raw, "score": score, "omitted": omitted, "omitted-worker": omitted_worker}[args.pop("action")](**args)
