"""Replay a length-selected small original recording on the two actual process entry points."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from time import perf_counter, process_time

from empty_bootstrap import RELEASE, checked


HERE = Path(__file__).resolve().parent
BULK = Path("/srv/bulk")
BINDING = BULK / "leo-dev/ds30-full-20261121/bindings/DS30-0180.json"
BINDING_SHA = "229d77358a899cdb50ef3cb66701fc2a77e3a67d95a08075b5a11282a09f6be0"
SHORT = Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so")
STAGED = Path("/dev/shm/leo-v3-saved-0402-pair-01")
ORDER = ("stock", "candidate")
RAW_LIMIT = 112 * 1024**2


def stage_orbits(target, source, names, cutoff):
    if len(names) != 50:
        raise ValueError("Unexpected signed causal snapshot count")
    directory = target / "archive/space-track"
    directory.mkdir(parents=True)
    source = source / "archive/space-track"
    unique_bytes, logical = 0, 0
    copies = {}
    for name, digest in sorted(names.items()):
        if Path(name).name != name or int(name.split("-")[0]) >= cutoff or len(digest) != 64:
            raise ValueError("Invalid causal orbit entry")
        path = directory / name
        if digest in copies:
            path.hardlink_to(copies[digest])
        else:
            original = source / name
            unique_bytes += original.stat().st_size
            if unique_bytes > 100 * 1024**2:
                raise ValueError("Orbit staging exceeds the one-recording allowance")
            path.write_bytes(checked(original, digest))
            copies[digest] = path
        logical += path.stat().st_size
    return dict(snapshots=len(names), unique=len(copies), copied_bytes=unique_bytes, logical_bytes=logical)


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from full_short_physical import REGION_SHA, environment
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, FastScanStore, cache_residency, measure, pairs, require_warm
    from triage_bounds import ShortWindowReader, warm_recording

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Research outputs must use a fresh tmpfs directory")
    signed = json.loads(checked(BINDING, BINDING_SHA))
    case = signed["case"]
    request_path = BULK / case["request"]["path"]
    request = json.loads(checked(request_path, case["request"]["sha256"]))
    job = request["job"]
    if (case["id"] != "DS30-0180" or case["recording"]["window_count"] != 92 or job["evaluation_reference"] is not None
            or case["regions"][0]["center"] != job["search_center"]):
        raise ValueError("Changed enrollment or geographic offer")
    manifests = tuple((BULK/r["path"], "sha256:"+r["sha256"]) for r in case["recording"]["segments"])
    recording = manifests[0][0].parent.parent
    root.mkdir()
    (root/"tmp").mkdir()
    store = FastScanStore(root)
    checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)
    def residency():
        return cache_residency.bound_snapshot(store, recording, manifests, os.sysconf("SC_PAGE_SIZE"), query)
    before = residency()
    total = sum(chunk.compressed_bytes for path, _ in manifests for chunk in ShortWindowReader(path.parent).manifest.chunks)
    if total != 111_464_875 or total > RAW_LIMIT or before["members"] != 2 or before["unavailable"]:
        raise ValueError("Original signed payload does not fit the selected recording budget")
    offer = root / "offer.json"
    shared_offer = Path("/tmp/leo-algo08v2-2x-bench/integration02/ds30-station-offer.json")
    original_offer = json.loads(checked(shared_offer, REGION_SHA))
    if original_offer["center"] != job["search_center"] or original_offer["screen_center"] != job["screen_center"]:
        raise ValueError("Archive and original operator offer disagree")
    write(offer, original_offer)
    stage_start = perf_counter()
    orbit = stage_orbits(root/"tle", Path(job["tle_root"]), request["causal_snapshots"], signed["orbit_cutoff_ns"])
    orbit["stage_wall_s"] = perf_counter() - stage_start
    named = pairs.verified_v3(pairs.NAMED_V3)
    env = environment(root)
    env["TMPDIR"] = str(root/"tmp")
    subprocess.run([RELEASE/"venv/bin/python", "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    cpu, wall = process_time(), perf_counter()
    needed = before["cached_pages"] != before["observed_file_pages"]
    if needed:
        warm_recording(manifests)
    conditioning = dict(used=needed, cpu_s=process_time()-cpu, wall_s=perf_counter()-wall, before=before, bytes=total)
    write(root/"admission.json", dict(case=case["id"], binding=BINDING_SHA, request=case["request"]["sha256"],
          order=ORDER, host=machine, stock=named, conditioning=conditioning, archive=orbit, offer=original_offer))
    common = ["--recording", recording, "--region", offer, "--archive", root/"tle"]
    for mode in ORDER:
        target = root/mode
        if mode == "stock":
            target.mkdir()
            cmd = [pairs.NAMED_V3, *common, "--bulk-root", target]
        else:
            cmd = [RELEASE/"venv/bin/python", "-IB", HERE/"unified_short_bootstrap.py", *common,
                   "--output", target, "--short-binary", SHORT, "--geographic-library", STAGED/"geographic_library.so",
                   "--regional-track-library", STAGED/"regional_track_library.so", "--frontier-block-library",
                   STAGED/"frontier_block_library.so", "--prove-empty-graph", "--one-pass-web-png"]
        cache = residency()
        require_warm(cache)
        clock = measure(cmd, env, target)
        write(root/f"{mode}-clock.json", dict(clock=clock, cache=cache, command=list(map(str, cmd))))
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])


def score(root, destination):
    from aperture_trial import read, write
    from empty_bootstrap import bind_native
    from full_short_run import RECIPE_SHA
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import pairs
    from triage_bounds import REFERENCE, REFERENCE_SHA256, distance_km

    signed = json.loads(checked(BINDING, BINDING_SHA))
    case = signed["case"]
    admission = read(root/"admission.json")
    results = {}
    for mode in ORDER:
        target = root/mode
        clock = read(root/f"{mode}-clock.json")
        pub = json.loads(target.with_suffix(".stdout").read_text().splitlines()[-1])
        if "receipt" in pub:
            pub = pub["receipt"]
        if mode == "stock":
            pairs.verify_v3_publication(target, pub)
        bootstrap = None if mode == "stock" else read(target/"unified-short-bootstrap.json")
        if bootstrap and (bootstrap["receipt"] != pub or bootstrap["raw_acquisitions"] != 1
                          or bootstrap["verified_handoffs"] != 1):
            raise ValueError("Expected exactly one authenticated receiver pass")
        raw = read(native_packet(target))
        source = raw["source"]
        science = pairs.evidence(target, pub, clock["clock"]["started_unix_ns"], read_only=True)
        media = artifacts(target, pub)
        recipe = pairs.V3_IDENTITY["detector_sha256"] if mode == "stock" else RECIPE_SHA
        bind_native(raw, case["session_id"], source["input_manifest_sha256"], recipe.removeprefix("sha256:"))
        if (clock["clock"]["exit_code"] or pub["window_count"] != 92 or pub["region"] != admission["offer"]
                or pub["session_id"] != case["session_id"] or pub["counts"]["processed"] != case["valid_visits"]
                or raw["clock_anchor"]["before"]["realtime_ns"] != signed["orbit_cutoff_ns"]
                or source["raw_recording_authority_digest"] != case["raw_authority"]
                or science["raw_authority"] != case["raw_authority"]):
            raise ValueError(f"Mismatched {mode} input, cutoff or geographic offer")
        probes = source["probes"]
        results[mode] = dict(process=clock, decision=pub["decision"], reason=science["reason"], arms=science["arms"],
            owners=science["owners"], counts=pub["counts"], native=canonical_digest(raw), terminal=pub["terminal_sha256"],
            input_manifest=source["input_manifest_sha256"], opportunity=canonical_digest([
                {k:v for k,v in row.items() if k != "candidates"} for row in probes]), grid_path=science["scientific_digests"],
            media=media, probes=len(probes), factors=sum(len(row["candidates"]) for row in probes),
            route=bootstrap["route"] if bootstrap else "named", proof=bootstrap["graph_proof"] if bootstrap else None)
    a, b = (results[mode] for mode in ORDER)
    if any(a[key] != b[key] for key in ("opportunity", "input_manifest", "probes")):
        raise ValueError("The two receiver methods used different opportunities")
    if any(r["decision"] == "complete" for r in results.values()):
        reference, = (c for c in json.loads(checked(REFERENCE, REFERENCE_SHA256))["cases"]
                      if c["dataset_label"] == case["id"] and c["authority_eligible"] and c["sealed_metadata_digests_verified"])
        truth = [reference["reference"][k] for k in ("latitude_deg","longitude_deg")]
        for r in results.values():
            r["errors_km"] = {k: distance_km(truth, v["latlon"]) for k,v in r["arms"].items() if v.get("latlon")}
    write(destination, dict(admission=admission, runs=results, elapsed_ratio=b["process"]["clock"]["elapsed_s"] /
                            a["process"]["clock"]["elapsed_s"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--receipt", type=Path)
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.root)
    elif args.receipt:
        score(args.root, args.receipt)
    else:
        cli.error("Supply --receipt when scoring")
