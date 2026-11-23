"""Run a single saved DS30-0374 pair through the current named final finish."""

import argparse
from hashlib import sha256
from itertools import groupby
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from aperture_trial import ARMS, RELEASE, read, write
from prospective_0316_solver import DETECTOR, LIBRARIES, inspect, owner_delta, saved_inventory, worker


BASE = "c0f18de19857aae6729dd7c678da8c7a2bbeb674"
CASE = "DS30-0374"
ORDER = ("combined", "stock")
PAIR_SHA = "b49af1ff154c7123574ffe6190e394c2d4ed7e29ea3da8d0da6dce479f3be82b"
SAVED_MEDIA_SHA = "6283dfb1e942af01e046d7723c6f8cd3366c8e5e00c2fcd8a6655a91a072afa1"
LOCAL = Path("/var/tmp/leo-signed-0374.KBD4SnU5/pair/stock")
NATIVE_SHA = "625adbd4e7601afd026f8b5d111e5daf3355727e63f28923058a69cddc9c933d"
WINDOWS, ADMITTED = 6770, 4644
AUDIT = "named-final-0374-worker.json"
TRACKS_SHA = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
REUSED_ROOTS = tuple(Path("/dev/shm") / name for name in (
    "leo-v3-saved-0402-pair-01", "leo-v3-saved-0160-pair-01", "leo-v3-saved-0155-pair-01",
    "leo-v3-saved-0316-pair-01", "leo-v3-family-endpoint-0169-pair-01", "leo-v3-raw-0016-best-results-01"))
SOURCES = ("unified_short_bootstrap.py", "empty_bootstrap.py", "joint_publication.py", "exact_graph_execution.py",
           "one_pass_web_png.py", "direct_orbit_entry.py", "direct_orbit_figures.py", "direct_residual_entry.py",
           "direct_residual_figures.py", "prepared_exterior.py", "grid_phase_state_reuse.py", "cold_finalist_race.py",
           "isolated_salvage.py", "endpoint_track_repair.py", "named_survivor_fit.py", "blind_joint_signed.py",
           "blind_joint_finish.py", "blind_joint_repair.py", "lighter_joint_estimator.py", "certified_salvage.py")


def verified(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Saved artifact mismatch at {path}")
    return data


def clock(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def reference_pair():
    return json.loads(verified(HERE / "measurements/successor-DS30-0374-pair.json", PAIR_SHA))


def source_pins():
    result = {}
    for name in SOURCES:
        contents = subprocess.check_output(["git", "-c", f"safe.directory={HERE.parents[2]}", "show",
                                            f"{BASE}:reports/ALGO08/v3/{name}"], cwd=HERE)
        digest = sha256(contents).hexdigest()
        verified(HERE / name, digest)
        result[name] = digest
    return result


def stage_archive(original, out, cutoff):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    origin = Path(original["root"])
    refs = TleArchiveReader(origin).list_snapshots("space-track")
    names = {r.path.name: r.sha256 for r in refs}
    total = sum(r.byte_size for r in refs)
    if (len(refs) != 47 or canonical_digest(names) != original["snapshots_sha256"]
            or not 0 < total < 96*1024**2 or any(r.collected_utc_ns >= cutoff for r in refs)):
        raise ValueError("Expected the original bounded, entirely causal DS30-0374 archive")
    reusable = {}
    for root in REUSED_ROOTS:
        for ref in TleArchiveReader(root / "tle").list_snapshots("space-track"):
            reusable.setdefault((ref.sha256, ref.byte_size), ref.path)
    dest = out / "archive/space-track"
    dest.mkdir(parents=True)
    copied, remote_bytes, reused_bytes = {}, 0, 0
    for ref in refs:
        key = (ref.sha256, ref.byte_size)
        requested = dest / ref.path.name
        if key in copied:
            requested.hardlink_to(copied[key])
        else:
            local = reusable.get(key)
            data = verified(local or ref.path, ref.sha256)
            if len(data) != ref.byte_size:
                raise ValueError("TLE snapshot size changed")
            requested.write_bytes(data)
            copied[key] = requested
            reused_bytes += len(data) if local else 0
            remote_bytes += 0 if local else len(data)
    if {r.path.name:r.sha256 for r in TleArchiveReader(out).list_snapshots("space-track")} != names:
        raise ValueError("TLE staging changed the signed chronological snapshot set")
    return dict(root=str(out), snapshots_sha256=original["snapshots_sha256"], snapshots=len(refs), logical_bytes=total,
                reused_distinct_bytes=reused_bytes, archived_distinct_bytes=remote_bytes, distinct=len(copied))


def stage(root, pins):
    from empty_bootstrap import bind_native
    from leo.contracts.algo08_region import Algo08Region

    pair = reference_pair()
    stock = pair["runs"]["baseline"]
    witness = stock["witnesses"]
    session, inventory = witness["session_id"], witness["input_manifest_sha256"]
    native_path, = LOCAL.glob("fast-scan-automatic-work/*/detections.json")
    terminal_path = LOCAL / "fast-scan-automatic-work" / stock["receipt"]["run_id"] / "terminal.json"
    terminal = json.loads(verified(terminal_path, stock["receipt"]["terminal_sha256"]))
    raw = verified(native_path, NATIVE_SHA)
    native = json.loads(raw)
    bind_native(native, session, inventory, DETECTOR, expected="sha256:" + NATIVE_SHA)
    offer = verified(Path(pair["region_file"]), pair["region_file_sha256"])
    source = native["source"]
    if (witness["detection_sha256"] != terminal["native_sha256"] or stock["raw_authority"] != source["raw_recording_authority_digest"]
            or native["provenance"]["window_count"] != WINDOWS or native["provenance"]["processed_windows"] != ADMITTED
            or terminal["region"] != Algo08Region.parse(json.loads(offer)).document() or terminal["session_id"] != session
            or terminal["decision"] != "ok" or stock["receipt"]["decision"] != "complete"):
        raise ValueError("Original signed receiver, retained offer or both valid finishes changed")
    inventory_data = verified(LOCAL / f"fast-scan-inputs/{session}.json", inventory)
    metadata = json.loads(inventory_data)
    manifests = [[str(Path(row["path"]) / "manifest.json"), row["manifest_digest"]] for row in metadata["segments"]]
    if sum(row["windows"] for row in metadata["segments"]) != WINDOWS or any(
            Path(path).parent.parent != Path(pair["recording"]) for path, _ in manifests):
        raise ValueError("The signed inventory does not cover the original recording")
    packet_path, offer_path = root / "named-detections.json", root / "operator-offer.json"
    packet_path.write_bytes(raw)
    offer_path.write_bytes(offer)
    (root / "inventory.json").write_bytes(inventory_data)
    cutoff = native["clock_anchor"]["before"]["realtime_ns"]
    archive = stage_archive(pair["archive"], root / "tle", cutoff)
    libraries = {}
    for name, (_, pin) in LIBRARIES.items():
        p = REUSED_ROOTS[0] / f"{name}.so"
        verified(p, pin)
        libraries[name] = str(p)
    request = dict(case=CASE, recording=pair["recording"], offer=terminal["region"], session=session, inventory=inventory,
                   issued=WINDOWS, admitted=ADMITTED, raw_authority=stock["raw_authority"], native_sha256=NATIVE_SHA,
                   manifests=manifests, causal_cutoff_utc_ns=cutoff, original_pair_sha256=PAIR_SHA,
                   native_file=str(packet_path), offer_file=str(offer_path), offer_sha256=pair["region_file_sha256"],
                   local_archive=archive, local_libraries=libraries, source_pins=pins)
    saved_inventory(request, root / "inventory.json")
    return request


def settings():
    return dict(native_sha=NATIVE_SHA, windows=WINDOWS, admitted=ADMITTED, audit_name=AUDIT)


def invoke(job, mode, output):
    import unified_short_bootstrap as entry

    request = read(job)
    original = entry.publish_active
    paid = {}

    def active(args, *values, **kwargs):
        args.named_survivor_finish = True
        args.direct_residual_figures = args.direct_orbit_figures = True
        receipt, result = original(args, *values, **kwargs)
        paid.update(result["named_survivor_finish"])
        return receipt, result

    if mode == "combined":
        with patch.object(entry, "publish_active", active):
            worker(job, "cumulative", output, source_pins=request["source_pins"], inventory_file=job.parent / "inventory.json",
                   **settings())
        write(output / "named-finish-bound.json", paid)
    else:
        worker(job, "stock", output, source_pins=request["source_pins"], inventory_file=job.parent / "inventory.json",
               **settings())


def launch(root):
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if root.resolve() != root or not root.is_relative_to("/dev/shm"):
        raise ValueError("Use a new canonical tmpfs pair directory")
    pins = source_pins()
    root.mkdir()
    (root / "tmp").mkdir()
    started = process_time(), perf_counter()
    request = stage(root, pins)
    job = root / "request.json"
    write(job, request)
    write(root / "launch.json", dict(machine=machine, order=ORDER, stage=clock(started),
          driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256((HERE / "named-final-0374-protocol.md").read_bytes()).hexdigest()))
    env = environment(root)
    env["TMPDIR"] = str(root / "tmp")
    python = RELEASE / "venv/bin/python"
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=20)
    for name in ORDER:
        out = root / name
        command = [python, "-IB", __file__, "worker", job, name, out]
        measured = measure(command, env, out)
        write(root / f"{name}-clock.json", measured)
        if measured["exit_code"]:
            raise RuntimeError(f"{name} exited {measured['exit_code']}; original clock saved")


def audit(root):
    from family_endpoint_transfer import grid_delta
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from signed_0374_transfer import verify_stock
    from tools.pipeline_eval.scoring import distance_km
    from triage_bounds import REFERENCE, REFERENCE_SHA256

    request = read(root / "request.json")
    historical = reference_pair()["runs"]["baseline"]
    runs = {}
    for mode in ORDER:
        folder = root / mode
        measured = read(root / f"{mode}-clock.json")
        if measured["exit_code"] != 0:
            raise ValueError("Both saved processes must exit successfully")
        witness = read(folder / AUDIT)
        observed = inspect(folder, mode, witness["receipt"], measured, request, **settings())
        if observed["terminal"]["region"] != request["offer"]:
            raise ValueError("Unexpected region change")
        result = read(folder / "joint-research-receipt.json")
        observed.update(publication={f:result[f] for f in ("publication_cpu_s", "publication_elapsed_s")},
                        recovered_inference=result.get("recovered_inference"), timings_sha256=sha256(
                            (folder / "joint-research-receipt.json").read_bytes()).hexdigest())
        runs[mode] = observed
    stock, candidate = (runs[mode] for mode in ("stock", "combined"))
    earlier = json.loads(verified(HERE / "measurements/signed-DS30-0374-publication.json", SAVED_MEDIA_SHA))
    media_ref = earlier["runs"]["stock"]["evidence"]["images"]
    if {name: entry["sha256"] for name, entry in media_ref.items()} != historical["witnesses"]["pngs"]:
        raise ValueError("Archived decoded media do not bind the named publication")
    verify_stock(stock["science"], historical, {"images": json.loads(json.dumps(stock["figures"]))}, {"images": media_ref})
    owners = {arm: owner_delta(stock["selected_rows"].get(arm, []), candidate["selected_rows"].get(arm, [])) for arm in ARMS}
    grids = None
    if stock["sidecars"] and candidate["sidecars"]:
        grids = grid_delta(*(FastStandardAnalysisStore(root / mode).position_grid(runs[mode]["worker"]["receipt"]["run_id"])
                             for mode in ("stock", "combined")))
    finish = read(root / "combined/named-finish-bound.json")
    sealed = dict(request=request, launch=read(root / "launch.json"), runs=runs, owners=owners, grid=grids,
                  named_finish=finish, stock_matches_archived=True, waveform_calls=0)
    write(root / "pair-seal.json", sealed)
    reference, = (r["reference"] for r in json.loads(verified(REFERENCE, REFERENCE_SHA256))["cases"]
                  if r["dataset_label"] == CASE and r["authority_eligible"] and r["sealed_metadata_digests_verified"])
    truth = [reference[key] for key in ("latitude_deg", "longitude_deg")]
    scores = {name: {arm: dict(error_km=distance_km(truth, data["latlon"]) if data["latlon"] else None,
                             rf_rms_hz=data.get("rf_rms_hz")) for arm, data in row["terminal"]["arms"].items()}
              for name, row in runs.items()}
    write(root / "scored.json", dict(scores=scores, reference_sha256=REFERENCE_SHA256,
          pair_seal_sha256=sha256((root / "pair-seal.json").read_bytes()).hexdigest()))


def missing_spans(track, lost):
    positions = [i for i, oid in enumerate(track["observation_ids"]) if oid in lost]
    spans = []
    for _, run in groupby(enumerate(positions), key=lambda ix: ix[1]-ix[0]):
        indexes = [item[1] for item in run]
        first, last = indexes[0], indexes[-1]
        spans.append(dict(start_index=first, stop_index=last+1, points=len(indexes),
                          start_time_s=track["times"][first], end_time_s=track["times"][last]))
    return spans


def audit_ownership(root):
    """Map sealed owners into the original tracks without preparing orbits or fitting position."""
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig

    pair_path = root / "pair-seal.json"
    pair = read(pair_path)
    if not pair["stock_matches_archived"] or pair["owners"]["c0"]["dropped"] != pair["owners"]["fitted_c"]["dropped"]:
        raise ValueError("The two archived owner arms must bind the same missing set")
    lost = set(pair["owners"]["c0"]["dropped"])
    native = json.loads(verified(root / "named-detections.json", NATIVE_SHA))
    config = json.loads(verified(RELEASE / "assets/tracks.json", TRACKS_SHA))["config"]
    prepared = prepare_tracks(native, TrackConfig(**config))
    graph = pair["runs"]["combined"]["worker"]["graph"]["graph"]
    if (prepared["graph_points"], len(prepared["tracks"])) != (graph["assigned"], graph["tracks"]):
        raise ValueError("Graph-only diagnostic does not reproduce the original preparation census")
    original = {oid: (norad, role) for oid,norad,role in pair["runs"]["stock"]["selected_rows"]["c0"]}
    final = {oid: (norad, role) for oid,norad,role in pair["runs"]["combined"]["selected_rows"]["c0"]}
    route = pair["runs"]["combined"]["route_details"]
    support = route["support"]
    salvage = {row["component"]: row["selected"] for row in support["salvage"]}
    tracks, seen = [], set()
    for track in prepared["tracks"]:
        ids = track["observation_ids"]
        affected = lost.intersection(ids)
        if not affected:
            continue
        norad, role = {original[oid] for oid in affected}.pop()
        if seen.intersection(affected) or any(original[oid] != (norad, role) for oid in affected):
            raise ValueError("Expected unique stock ownership by family and role")
        seen.update(affected)
        key = track["key"]
        offer = salvage.get(key)
        tracks.append(dict(component=key, norad=norad, role=role, points=len(ids),
                           named_owners=sum(oid in original for oid in ids), candidate_owners=sum(oid in final for oid in ids),
                           lost=len(affected), spans=missing_spans(track, lost), first_cold_reject=key in support["cold_rejected_tracks"],
                           second_curved_reject=key in support["second_curved_rejections"], salvage_offer=offer,
                           recovered_missing_rows=0 if offer is None else len(affected.intersection(ids[offer["start_index"]:offer["stop_index"]]))))
    if seen != lost:
        raise ValueError("Some original named owners could not be joined to graph tracks")
    write(root / "lost-support.json", dict(pair_seal_sha256=sha256(pair_path.read_bytes()).hexdigest(),
          graph_points=prepared["graph_points"], graph_tracks=len(prepared["tracks"]), lost=len(lost), tracks=tracks,
          history=route["signed"]["selection"], past_distribution_qualified=support["past_distribution_qualified"],
          final_fit=route["named_survivor_fit"], additional_position_solves=0, waveform_reads=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for command in ("launch", "audit", "audit-ownership"):
        sub.add_parser(command).add_argument("root", type=Path)
    replay = sub.add_parser("worker")
    replay.add_argument("job", type=Path)
    replay.add_argument("mode", choices=ORDER)
    replay.add_argument("output", type=Path)
    values = vars(parser.parse_args())
    {"launch": launch, "worker": invoke, "audit": audit, "audit-ownership": audit_ownership}[values.pop("action")](**values)
