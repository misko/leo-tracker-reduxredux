"""Bind the rank-four certified native prefix to the original saved owner books."""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter, process_time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
from prefix_transfer_0419 import ARMS, checked, factor_contrast, lane_key, lane_rows, metadata, observation_id, read, signed_member, verified_owner_rows, write


BASE = Path("/dev/shm/leo-v3-combined-0163-blind02")
STAGE = Path("/tmp/leo-v3-0163-first-idle-stage01")
CASE = "DS30-0163"
PINS = {
    "result.json": "76121104353dfad92fe5f325a57bf0f8bcc10adc915a44093a3182970eb9c40e",
    "prediction-seal.json": "4bbdf56939b61b106603a2687865f2fd981ce31a475ef285e0627d6e94856541",
    "admission.json": "95c2507e2343d93243b9651d4263f875fff15e410aac32bf62236863c68843ea",
    "request.json": "654bb406870bd97ac6b1854f312b0dae54e8405d6fda81c2ee135c61e41fcae9",
    "job.json": "3b79aefb7f540ec55193a5e54b3ee57cb60f0a27a3371b64c2e5504be15be7d3",
    "routed/candidate/joint-research-receipt.json": "1c4031fb6cd37a4fe2b364c301d1b9f0b78495208b6c9793242d55bde61d3f47",
    "installed/candidate/joint-research-receipt.json": "64b8b80a9a16ed27b3d478c2a8075b9249e36d3f515907bfccdfc4a88314dc9d",
}
PROTOCOL = HERE / "0163-verified-window-transfer-protocol.md"
LABEL = "saved measured pre-held 20/8 prefix perturbation on original 20 ms continuation"
FONT = "3ec97e620a1fa0115bbbdaefd3ddd47382fd0aed525281d7f1fc88a8614f282a"
MODES = ("installed", "routed")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def clock(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def now():
    return process_time(), perf_counter()


def parse(path, pin):
    return json.loads(checked(path, pin))


def controls():
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest

    docs = {name: parse(BASE/name, pin) for name, pin in PINS.items()}
    book, scored, req, job = (docs[name+".json"] for name in ("admission", "result", "request", "job"))
    bound = job["binding"]
    full = parse(Path(req["native_file"]), req["native_sha256"])
    inv = parse(Path(bound["inventory"]), req["inventory"])
    if (req["case"] != CASE or scored["case"] != CASE or scored["prediction_seal_sha256"] != PINS["prediction-seal.json"]
            or scored["admission"] != book or inv["window_count"] != req["issued"]
            or full["source"]["raw_recording_authority_digest"] != req["raw_authority"]
            or full["provenance"]["processed_windows"] != req["admitted"]):
        raise ValueError("The original combined authority or complete saved input changed")
    detector = full["provenance"]["detector_sha256"]
    bind_native(full, req["session"], req["inventory"], detector[7:], expected="sha256:"+req["native_sha256"])
    lanes, exclusions = lane_rows(full, req["issued"])
    allowed = {observation_id(req["session"], row) for row in lanes.values() if row["candidates"]}
    rosters = {}
    for mode in MODES:
        run = scored["jobs"][mode]
        publication = run["publication"]
        witness = docs[f"{mode}/candidate/joint-research-receipt.json"]
        if (run["decision"] != "complete" or run["clock"]["exit_code"] or publication["selected_rows"] != witness["selected_rows"]
                or publication["terminal"]["native_sha256"] != "sha256:"+req["native_sha256"]
                or canonical_digest(publication["terminal"]) != witness["receipt"]["terminal_sha256"]
                or publication["science"]["raw_authority"] != req["raw_authority"] or len(publication["figures"]) != 8):
            raise ValueError("Expected the sealed published derived and installed owner evidence")
        rosters[mode] = verified_owner_rows(witness["selected_rows"], publication["science"]["owners"], allowed, canonical_digest)
    original = Path(inv["segments"][0]["path"])
    signed = signed_member(STAGE/original.name, inv)
    return docs, full, inv, lanes, exclusions, rosters, signed


def audit_prefix(full, lanes, exclusions, rosters, witness, applied, columns):
    """Use only pre-tail stereo lists and exact original issued/receiver keys."""
    limit = len(applied)
    if not 0 < limit <= len(witness["visits"]) or [row["sequence"] for row in applied] != list(range(limit)):
        raise ValueError("The admitted visits are not the complete contiguous original prefix")
    session = full["source"]["session_id"]
    for expected, actual in zip(witness["visits"], applied):
        if any(actual[k] != expected[k] for k in ("sequence", "sample_start", "sample_end", "iq_sha256", "channel", "actual_rf_hz", "edge", "clock")):
            raise ValueError("Certified visit identity or original effective RF changed")
        if actual["admitted"] != (actual["sequence"] not in exclusions):
            raise ValueError("Original signed valid support or quality exclusion was mismatched")
        if not actual["admitted"]:
            excluded = exclusions[actual["sequence"]]
            if any(excluded[k] != expected[k] for k in ("iq_sha256", "sample_start", "sample_end")):
                raise ValueError("Archived exclusion differs from the issued source support")
    original = [r for k, r in lanes.items() if k[0] < limit]
    installed, mixed = (columns[key] for key in ("installed", "mixed"))
    if len(installed) != len(original) or len(mixed) != len(original):
        raise ValueError("Need both native stereo rows at every admitted original visit")
    if map_pairs(columns["installed"]) != map_pairs(original) or map_pairs(columns["mixed"]) != map_pairs(original):
        raise ValueError("Producer visit order does not match the original native lanes")
    for row, typed in zip(mixed, installed, strict=True):
        if metadata(row) != metadata(typed):
            raise ValueError("The measured mixed candidate changed the original lane metadata")
    continuous = all(archived == fresh for archived, fresh in zip(original, installed, strict=True))
    changes, rows = {}, []
    prefix_ids = {observation_id(session, row) for row in original}
    for archived, fresh, measured in zip(original, installed, mixed, strict=True):
        id_ = observation_id(session, archived)
        if fresh != archived or fresh != measured:
            rows.append(dict(key=lane_key(archived), channel=archived["channel"], observation_id=id_,
                 archived=archived["candidates"], installed=fresh["candidates"], mixed=measured["candidates"],
                 corroborated=archived == fresh, contrast=factor_contrast(fresh["candidates"], measured["candidates"]),
                 published_owners={mode: {arm: rosters[mode][arm].get(id_) for arm in ARMS} for mode in MODES}))
        if fresh != measured and archived == fresh:
            changes[lane_key(archived)] = measured
    updated = [changes.get(k, r) for k, r in lanes.items()] if continuous else None
    counts = {mode: {arm: dict(total=len(rosters[mode][arm]), prefix=len(prefix_ids & rosters[mode][arm].keys()))
                     for arm in ARMS} for mode in MODES}
    return dict(issued=limit, admitted=sum(r["admitted"] for r in applied), exact_installed_parity=continuous,
            original_native_factors=sum(len(r["candidates"]) for r in original),
            mixed_native_factors=sum(len(r["candidates"]) for r in mixed),
            matched_changes=len(changes), rows=rows, owners=counts, original_suffix=full["provenance"]["window_count"]-limit), updated


def map_pairs(rows):
    return [lane_key(row) for row in rows]


def prepare(root, ledger, ledger_pin, driver_pin):
    from continued_cfo_trial import rebinding
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json

    started = now()
    if root.parent != Path("/tmp") or root.exists():
        raise ValueError("Need a fresh private /tmp saved scope")
    docs, full, inv, lanes, excluded, rosters, signed = controls()
    from verified_window_transfer_inputs import producer

    measured = producer(ledger, ledger_pin, driver_pin, docs["request.json"], inv, signed)
    audit, updated = audit_prefix(full, lanes, excluded, rosters, signed, measured["visits"], measured["native"])
    root.mkdir(mode=0o700)
    word = ("eligible" if updated is not None and audit["matched_changes"] else
            "original_prefix_parity_failed" if updated is None else "no_native_factor_changes")
    journal = dict(audit, disposition=word, protocol=digest(PROTOCOL), original_control=PINS,
                   producer=measured["binding"], digest=ledger_pin, setup=clock(started))
    if word == "eligible":
        source = full["source"]
        recipe = dict(kind="authentic_partial_window_prefix_splice", original_native=docs["request.json"]["native_sha256"],
                      original_detector=full["provenance"]["detector_sha256"], producer=measured["binding"],
                      protocol=journal["protocol"], prefix_issued=audit["issued"])
        packet = rebinding(full, updated, recipe)
        lane_rows(packet, full["provenance"]["window_count"])
        detector, native = canonical_digest(recipe), canonical_digest(packet)
        bind_native(packet, source["session_id"], source["input_manifest_sha256"], detector[7:], expected=native)
        path = root/"hybrid-native.json"
        immutable_json(path, packet)
        checked(path, native)
        journal.update(recipe=recipe, native_sha256=native, detector_sha256=detector, packet=str(path), setup=clock(started))
    write(root/"verified-prefix-overlap.json", journal)


def overlap_0419(path, ledger, ledger_pin, driver_pin):
    from prefix_transfer_0419 import archived
    from verified_window_transfer_inputs import producer

    docs, lanes, excluded, rosters, _ = archived()
    request, inv, full = (docs[k+".json"] for k in ("request", "inventory", "native"))
    stage = Path("/tmp/leo-v3-0419-first-idle-stage01")/Path(inv["segments"][0]["path"]).name
    signed = signed_member(stage, inv)
    measured = producer(ledger, ledger_pin, driver_pin, request, inv, signed)
    audit, _ = audit_prefix(full, lanes, excluded, rosters, signed, measured["visits"], measured["native"])
    write(path, dict(audit, case="DS30-0419", solver_runs=0, producer=measured["binding"]))


def launch(root, audit_pin):
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    import combined_successor_0289 as combined
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from exact_named_route import checked_catalogue
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from prefix_transfer_0008 import resident
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident as cache

    started = now()
    machine = host()
    verified = parse(root/"verified-prefix-overlap.json", audit_pin)
    if (verified["disposition"] != "eligible" or not verified["exact_installed_parity"] or not verified["matched_changes"]
            or verified["protocol"] != digest(PROTOCOL) or (root/"routed").exists()):
        raise ValueError("A one-shot hybrid requires the independently qualified native overlap")
    original = parse(BASE/"admission.json", PINS["admission.json"])
    bound = parse(BASE/"job.json", PINS["job.json"])["binding"]
    req = parse(BASE/"request.json", PINS["request.json"])
    sources, libraries = combined.source_pins(), combined.admitted_libraries()
    if (original["sources"] != sources or original["libraries"] != libraries or original["machine"] != machine
            or canonical_digest(verified["recipe"]) != verified["detector_sha256"]):
        raise ValueError("The exact combined solver or matching machine changed")
    _, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest, resident=resident)
    archive = cache([str(ref.path) for ref in refs])
    if archive["members"] != len(refs):
        raise ValueError("The original resident catalogue roster changed")
    for name in ("fonts", "tmp", "routed"):
        (root/name).mkdir()
    font = "fontlist-v3.11.0.json"
    (root/"fonts"/font).write_bytes(checked(BASE/"fonts"/font, FONT))
    native, packet = verified["native_sha256"], Path(verified["packet"])
    checked(packet, native)
    request = root/"request.json"
    write(request, dict(req, native_file=str(packet), native_sha256=native[7:]))
    packets = dict(bound["packets"])
    packets.pop(bound["request"])
    packets.pop(req["native_file"])
    packets.update({str(request): digest(request), str(packet): native[7:]})
    bound = dict(bound, request=str(request), packets=packets)
    job = root/"job.json"
    write(job, dict(binding=bound, original_archive=req["original_archive"]))
    job_pin = digest(job)
    with patch("exact_named_route.resident_path", resident):
        load_job(job, job_pin)
    write(root/"routed/binding.json", dict(input=bound))
    argv = ["/usr/bin/timeout", "--kill-after=2s", "115s", str(RELEASE/"venv/bin/python"), "-IB",
            __file__, "worker", str(root)]
    write(root/"admission.json", dict(case=CASE, sources=sources, libraries=libraries, machine=machine,
          job_sha256=job_pin, command=argv, setup=clock(started), archive=archive, original_control=PINS,
          producer_scope_sha256=audit_pin, detector=verified["detector_sha256"], wrapper=digest(Path(__file__)),
          protocol=digest(PROTOCOL), one_worker=True, waveforms=0))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    write(root/"routed/clock.json", measure(argv + ["--pin", digest(root/"admission.json")], env, root/"routed/candidate"))
    write(root/"prediction-seal.json", output_seal(root))


def worker(root, pin):
    import combined_successor_0289 as combined
    import exact_named_route as exact
    from history_risk_weak_physical import deny_original
    from prefix_transfer_0008 import resident
    import prospective_0316_solver as saved

    sys.addaudithook(deny_original)
    book = parse(root/"admission.json", pin)
    if book["wrapper"] != digest(Path(__file__)) or book["protocol"] != digest(PROTOCOL):
        raise ValueError("The input adapter changed")
    parse(root/"verified-prefix-overlap.json", book["producer_scope_sha256"])
    detector = book["detector"][7:]
    with (patch.object(exact, "resident_path", resident),
          patch.object(exact, "exact_ports", partial(exact.exact_ports, resident=resident)),
          patch.object(saved, "worker", partial(saved.worker, detector=detector, input_description=LABEL)),
          patch.multiple(combined, STAGED=root, JOB_SHA=book["job_sha256"])):
        combined.worker(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "overlap-0419", "launch", "worker", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--pin")
    parser.add_argument("--driver-sha256")
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare(args.root, args.ledger, args.pin, args.driver_sha256)
    elif args.operation == "overlap-0419":
        overlap_0419(args.root, args.ledger, args.pin, args.driver_sha256)
    elif args.operation == "launch":
        launch(args.root, args.pin)
    elif args.operation == "worker":
        worker(args.root, args.pin)
    else:
        from verified_window_transfer_score import score

        score(args.root)


if __name__ == "__main__":
    main()
