"""Bind a selective trailing-verifier packet before one saved North publication."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from .aperture_trial import RELEASE, read, write
from .mixed_aperture_receiver import PILOT_SHA, NativePath, StereoSchedule, verified
from .north_factor_swap import rebound
from .public_short_prefetch import MANIFEST_SHA, RECORDING


HERE = Path(__file__).resolve().parent
PACKET_DIR = Path("/dev/shm/leo-eight-ms-north/12ms")
ORIGINAL_PACKET = "2b4e1282f8205a5c90cef2ab6acb7c666d445592963634e93911160205403427"
INVENTORY = "sha256:985dfe1e0423b1106f5e205b9ccf1aec7f9d1e156d9262da19852521dd703d4b"
AUTHORITY_PIN = "a48a25c9ca2f3575eb33834c78660cfec99028445dce666a032d57ac52d488c5"
OLD_UNIT = "b99ee95b414d09836b815693a128fa701e13c5b4b3f4dc432682106f32a979dc"
OLD_RAW = "16ee7ed27cad9fac9403f57342e277a3551a76afee651e0e8e7c3f30f6f4971d"
NATIVE_HELPER = "66db212623a2e7e6f079baa02f1480535f46d6143edc714fbfa62e1e85b2249a"
MEASURED_FREEZE_SOURCE = "9395c728b26d74f8a5a325cc7460e1a866519af496521d9d2900e26ec21bc5a7"
GATE = 0.025


def digest(contents):
    return sha256(contents).hexdigest()


def selection(mode, positive, causal, scores):
    if mode == "full" or not positive:
        if scores is not None:
            raise ValueError("A full anchor or empty lane was sent to trailing verification")
        return positive, positive
    if scores is None:
        raise ValueError("A short hypothesis is missing its measured tail score")
    passes = scores[0]-scores[1] >= GATE
    return causal or passes, passes


def residency(chunks, query):
    from .short_prefetch_residency import resident
    from .warm_six_prefetch import page_state

    pages = page_state(RECORDING, chunks, query)
    if len(pages) != 19 or any(not resident(state) for pair in pages for state in pair.values()):
        raise ValueError("The complete North source is no longer resident")
    return pages


def original():
    from leo.storage.fast_scan import FastScanStore
    from .anchor_exposure import packet
    from .full_short_raw import RECIPE_SHA

    doc = packet(PACKET_DIR, ORIGINAL_PACKET)
    source = doc["source"]
    manifest = json.loads(verified(RECORDING / "manifest.json", MANIFEST_SHA))
    session, inventory, body = FastScanStore(RECORDING.parent).inventory(RECORDING, verify_windows=False)
    entry, = body["segments"]
    binding = json.loads(verified(PACKET_DIR.parent / "binding.json", AUTHORITY_PIN))
    if (session != source["session_id"] or inventory != source["input_manifest_sha256"] or inventory != INVENTORY
            or Path(entry["path"]) != RECORDING or entry["manifest_digest"] != "sha256:"+MANIFEST_SHA
            or binding["request"]["raw_authority"] != source["raw_recording_authority_digest"]
            or doc["provenance"]["detector_sha256"] != "sha256:"+RECIPE_SHA or not source["qualified"]
            or len(source["probes"]) != 2400 or body["window_count"] != 1200 or manifest["window_count"] != 1200):
        raise ValueError("The original research packet and complete signed capture differ")
    return doc, entry, manifest


def bind_lane(item, row, lane):
    a, t = item.acquisition, item.target
    u = (row["visit_index"], row["receiver_id"], row["valid_start_counter"], row["edge"], row["channel"], row["actual_rf_hz"])
    v = (a["global_visit"], lane, a["sample_start"], t["edge"], t["channel"], a["actual_if_center_hz"]+t["lnb_lo_hz"])
    if u != v or len(row["candidates"]) > 1 or any(not k["passed_fractional_margin_gate"] for k in row["candidates"]):
        raise ValueError("The original released signed factor is not on the supplied native acquisition")


def freeze(root):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.scanner import ScannerIqStore
    from tools.pipeline_eval.variants.carrier_continuation import Continuation
    from .causal_short_receiver import FILTER_SHA, identity
    from .full_short_raw import RECIPE_SHA
    from .mixed_aperture_trial import encoded
    from .tail_confirm import (CACHE_LIBRARY, CACHE_SHA, GATE as ORIGINAL_GATE, HOLDOUT, PAYLOAD,
                               ResidentTmpfsReads, Tail, build, check_machine, clock, input_bytes, load_query, since)

    machine = check_machine()
    root.mkdir()
    original_doc, inventory, manifest = original()
    verified(HOLDOUT, NATIVE_HELPER)
    if GATE != ORIGINAL_GATE:
        raise ValueError("The original trailing decision threshold changed")
    identity(RECIPE_SHA)
    verified(CACHE_LIBRARY, CACHE_SHA)
    query = load_query(CACHE_LIBRARY)
    resident_reader = ResidentTmpfsReads(RECORDING, query)
    before = residency(manifest["chunks"], query)
    binary, build_pin = build(root / "native", PAYLOAD / "receiver.so")
    tail = Tail(binary)
    probes = original_doc["source"]["probes"]
    source = FastSegmentSource(inventory)
    schedule, continuation = StereoSchedule(full_coverage=True), Continuation()
    policies, outcomes, times = {arm: [] for arm in ("selective", "all")}, [], Counter()
    initial_io = input_bytes()
    with ExitStack() as stack:
        native = {}
        for edge, pin in PILOT_SHA.items():
            asset = np.frombuffer(verified(RELEASE / "assets" / f"{edge}.f32", pin), dtype="<f4")
            native[edge] = NativePath(PAYLOAD / "receiver.so", asset, "full")
            stack.callback(native[edge].close)
        stack.enter_context(patch.dict(ScannerIqStore._read_regular.__globals__, {"os": resident_reader}))
        traversal_start = clock()
        for item, pair in zip(source.windows(), zip(probes[::2], probes[1::2], strict=True), strict=True):
            edge = item.target["edge"]
            _, mode = schedule.visit(edge, item.target, item.acquisition)
            for lane, row in enumerate(pair):
                bind_lane(item, row, lane)
                positive = bool(row["candidates"])
                history_start = clock()
                _, selected, votes = continuation.select(row)
                add(times, "history", since(history_start))
                scores, ticks = None, None
                if positive and mode == "short_primary":
                    hypothesis, = encoded(row)
                    start = clock()
                    scores = tail.score(native[edge], item.samples, lane, hypothesis)
                    ticks = since(start)
                    add(times, "all", ticks)
                    if selected is None:
                        add(times, "selective", ticks)
                kept = selection(mode, positive, selected is not None, scores)
                for arm, retain in zip(policies, kept, strict=True):
                    policies[arm].append(row if retain or not positive else dict(row, candidates=[]))
                outcomes.append(dict(visit=row["visit_index"], lane=lane, mode=mode, positive=positive,
                                     original=encoded(row), exact_rolled=scores, tail_ns=ticks, votes=votes,
                                     causal=selected is not None, selective=kept[0], all=kept[1], iq_sha256=item.iq_sha256))
        add(times, "traversal", since(traversal_start))
    storage_bytes = input_bytes()-initial_io
    if storage_bytes:
        raise ValueError("The resident audit incurred process storage input")
    after = residency(manifest["chunks"], query)
    recipes = {arm: [f"disjoint trailing pilot {arm} v1", "sha256:"+ORIGINAL_PACKET,
                     FILTER_SHA, NATIVE_HELPER, GATE] for arm in policies}
    packets = {arm: rebound(original_doc, rows, recipes[arm]) for arm, rows in policies.items()}
    hashes = {arm: canonical_digest(doc) for arm, doc in packets.items()}
    report = dict(candidate="selective", packets=hashes, recipe=recipes, original_packet=ORIGINAL_PACKET,
                  authority=original_doc["source"]["raw_recording_authority_digest"], inventory=INVENTORY,
                  source_sha256=digest(Path(__file__).read_bytes()), machine=machine, build=build_pin,
                  io=dict(process_storage_input_bytes=storage_bytes, authenticated_reads=resident_reader.calls,
                          authenticated_bytes=resident_reader.logical_bytes, original_compressed=sum(c["compressed_bytes"] for c in manifest["chunks"])),
                  pages=[before, after], elapsed_ns=dict(times), lanes=outcomes, counts=tally(outcomes))
    write(root / "selective-packet.json", packets["selective"])
    write(root / "frozen.json", report)


def add(total, stage, ticks):
    for unit, value in zip(("cpu", "wall"), ticks, strict=True):
        total[f"{stage}_{unit}"] += value


def tally(outcomes):
    result = {}
    for label, lane in (("both", None), ("0", 0), ("1", 1)):
        counts = Counter()
        for row in outcomes:
            if lane is not None and row["lane"] != lane:
                continue
            arm = row["mode"]
            counts[arm+"_opportunities"] += 1
            if not row["positive"]:
                continue
            counts[arm+"_positive"] += 1
            for variant in ("causal", "selective", "all"):
                counts[arm+"_"+variant] += row[variant]
            if arm == "short_primary":
                counts["causal_omitted"] += not row["causal"]
                counts["causal_omitted_rescued"] += not row["causal"] and row["selective"]
                counts["causal_kept_lost_by_all"] += row["causal"] and not row["all"]
        result[label] = dict(counts)
    return result


def prepared_inputs(root):
    from leo.contracts.digests import canonical_digest

    packet_path = root / "selective-packet.json"
    proof, chosen = read(root / "frozen.json"), read(packet_path)
    if (proof["candidate"] != "selective" or canonical_digest(chosen) != proof["packets"]["selective"]
            or chosen["source"]["input_manifest_sha256"] != INVENTORY or chosen["source"]["raw_recording_authority_digest"] != proof["authority"]
            or proof["source_sha256"] not in (MEASURED_FREEZE_SOURCE, digest(Path(__file__).read_bytes()))):
        raise ValueError("The frozen research packet changed")
    return packet_path, proof, chosen


def worker(root, geographic, tracks):
    from .dense_geographic_trial import host
    from .full_short_physical import environment
    from .full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from .north_combined import assignments
    from .weak_combined_raw import measure

    host()
    path, proof, chosen = prepared_inputs(root)
    verified(geographic, GEOGRAPHIC_SHA)
    verified(tracks, TRACK_SCORES_SHA)
    pair, _ = assignments()
    if Path(pair["recording"]) != RECORDING:
        raise ValueError("Changed containing publication assignment")
    command = [RELEASE / "venv/bin/python", "-BPs", HERE / "north_factor_swap.py", "worker", path,
               proof["packets"]["selective"], chosen["provenance"]["detector_sha256"].removeprefix("sha256:"),
               root / "containing", pair["recording"], pair["archive"]["root"], pair["region"], geographic, tracks]
    measure(command, environment(root), root, "containing")


def score(root, output):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from .joint_publication import artifacts
    from .mixture_score import section
    from .north_combined import assignments

    _, proof, chosen = prepared_inputs(root)
    pair, omissions = assignments()
    baseline = json.loads(verified(HERE / "measurements/eight-ms-north.json", OLD_RAW))
    sealed_unit = json.loads(gzip.decompress(verified(HERE / "measurements/discovery-margin-12ms.json.gz", OLD_UNIT)))
    unit, stock = sealed_unit["north"]["comparison"]["unit"], baseline["runs"]["v3"]
    if (unit["native_sha256"] != "sha256:"+ORIGINAL_PACKET or unit["terminal"] != baseline["runs"]["12ms"]["terminal_sha256"]
            or unit["arms"] != baseline["runs"]["12ms"]["arms"] or stock["arms"] != pair["runs"]["baseline"]["arms"]):
        raise ValueError("The stored comparators differ from the original signed publication")
    directory = root / "containing"
    publication = read(directory / "joint-research-receipt.json")
    receipt = publication["receipt"]
    evidence = json.loads(json.dumps(artifacts(directory, receipt)))
    public_packet, = (directory / "fast-scan-automatic-work").glob("*/detections.json")
    terminal = read(directory / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json")
    if (canonical_digest(terminal) != receipt["terminal_sha256"] or receipt["region"] != pair["runs"]["candidate"]["receipt"]["region"]
            or evidence != publication["evidence"] or publication["saved_handoff_manifest"] != INVENTORY
            or not proof["packets"]["selective"] == canonical_digest(read(public_packet)) == terminal["native_sha256"] == publication["saved_digest"]
            or canonical_digest(chosen) != terminal["native_sha256"]):
        raise ValueError("Terminal, grid, images or supplied region do not match the frozen replay")
    grid = None
    if receipt["decision"] == "complete":
        grid = FastStandardAnalysisStore(directory).position_grid(receipt["run_id"])
        if not grid["complete"] or len(evidence["images"]) != 8:
            raise ValueError("Incomplete grid or standard images")
    result = dict(decision=receipt["decision"], native=terminal["native_sha256"], terminal=receipt["terminal_sha256"],
                  region=receipt["region"], arms=terminal["arms"], path_grid_images=evidence,
                  grid_points=grid["evaluated_points"] if grid else None, route=publication["route_details"],
                  selected_roles=publication["selected_roles"], geography=publication["early_regional"],
                  process=read(root / "containing-clock.json"), solve=publication["solve"],
                  run_id=receipt["run_id"], graph=receipt["graph_path"], selected_rows=publication["selected_rows"],
                  publication_elapsed_s=publication["publication_elapsed_s"],
                  publication_cpu_s=publication["publication_cpu_s"],
                  relative_to_v3=section(terminal["arms"], baseline["survey"], stock["arms"]),
                  relative_to_unit=section(terminal["arms"], baseline["survey"], unit["arms"]))
    near = omissions["results"]["north-mirror-outside"]
    write(output, dict(protocol=proof, candidate=result, controls=dict(unit=unit, v3=stock, raw12=baseline["runs"]["12ms"],
                                                                       old_near=near), scoring_reference=OLD_RAW))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for label, arguments in (("freeze", ("root",)), ("worker", ("root", "geographic", "tracks")), ("score", ("root", "output"))):
        command = commands.add_parser(label)
        for argument in arguments:
            command.add_argument(argument, type=lambda value: Path(value).resolve())
    arguments = vars(parser.parse_args())
    globals()[arguments.pop("command")](**arguments)
