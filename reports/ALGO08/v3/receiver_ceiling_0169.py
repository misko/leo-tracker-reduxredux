"""Price the released and full-short receivers on one signed DS30-0169 member."""

import argparse
from collections import Counter
from contextlib import contextmanager
import ctypes as ct
from dataclasses import asdict
from hashlib import sha256
from importlib import import_module
import json
from math import remainder
import os
from pathlib import Path
import resource
import stat
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from . import sparse_cold_input as cold
from .centered_primary import ORIGINAL
from .full_short_cold import ORDERS, SHORT_SHA, freeze, recipe
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, MixedApertureDetector
from .scout_readout_trial import check_machine, factor_bytes


CASE = "DS30-0169"
BULK = Path("/srv/bulk")
BINDING_PIN = "117c9dad50c3fb217bd0b661e999bca714bd4c75967e1b7c3a79a2e309204aba"
SESSION = "fast-be9e6e39a10a89a298054d08ea51db53"
INVENTORY_PIN = "be9e6e39a10a89a298054d08ea51db53b5aec7667ecf9a725373582ac092972d"
INVENTORY = (Path("/tmp/ds30-v2-stage-all-6cdbac") / CASE / "candidate/fast-scan-inputs" / (SESSION + ".json"))
SOLVE_SCORE = Path("/dev/shm/leo-v3-family-endpoint-0169-score-01.json")
SOLVE_SCORE_PIN = "eeec8e7bce3a7ad0b38c42207b8370c26f4abca690f01f8f49b5080b6bcaf172"
PAYLOAD_PIN = "sha256:889c12fd0c940d4a95b47829e4d78947ab8207a023b1657b201e5f37074fe21d"
WINDOWS, COMPRESSED, DECODED, STAGE_CAP = 64, 78_852_856, 102_400_000, 82_000_000
RAW_COMPRESSED_MB, NAMED_HISTORICAL_S, COMBINED_SAVED_S = 5189.509, 73.673, 11.822
ACQUISITION_S = NAMED_HISTORICAL_S / 2 - COMBINED_SAVED_S
RATE_MB_S = RAW_COMPRESSED_MB / ACQUISITION_S


def first_member(model):
    if not model.chunks:
        raise ValueError("Expected the frozen first member")
    chunk = model.chunks[0]
    if (model.receiver_ids != (0, 1) or model.sample_rate_hz != 10_000_000
            or (chunk.chunk_index, chunk.first_sequence, chunk.window_count) != (0, 0, WINDOWS)
            or (chunk.compressed_bytes, chunk.uncompressed_bytes) != (COMPRESSED, DECODED)
            or chunk.payload_relative_path != "iq-000000.ci16.zst" or chunk.compressed_sha256 != PAYLOAD_PIN
            or chunk.compressed_bytes > STAGE_CAP):
        raise ValueError("Unexpected frozen member or stereo geometry")
    for name in (chunk.index_relative_path, chunk.payload_relative_path):
        cold.source_member_name(name)
    return chunk


def scope_inventory(binding, inventory):
    original = inventory["segments"][0]
    pin = binding["case"]["recording"]["segments"][0]
    manifest = Path(original["path"]) / "manifest.json"
    if (binding["case"]["id"] != CASE or binding["case"]["session_id"] != SESSION
            or manifest != BULK / pin["path"] or original["manifest_digest"] != "sha256:" + pin["sha256"]
            or cold.SOURCE_DIR not in manifest.parents or manifest.resolve(strict=True) != manifest):
        raise ValueError("Original signed inventory and recording binding disagree")
    return original, manifest


def snapshot(path, size, query):
    from tools.pipeline_eval.qualification.cache_residency import cache_snapshot

    return cache_snapshot([(path.parent, path.name, size)], os.sysconf("SC_PAGE_SIZE"), query)


def copy_one(source, destination, size, digest):
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as raw, destination.open("xb") as target:
        info = os.fstat(raw.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != size:
            raise ValueError("Copy source differs from the frozen bounded file")
        return cold.copy_bounded(raw, target, limit=size, exact_size=size, expected_hash=digest)


def stage(root, query):
    from leo.contracts.digests import canonical_digest
    from leo.contracts.multirate_window_recording import ShortWindowManifestV2

    binding = json.loads(cold.verified(cold.BINDING.with_name(CASE + ".json"), BINDING_PIN))
    inventory = json.loads(cold.verified(INVENTORY, INVENTORY_PIN))
    if canonical_digest(inventory) != "sha256:" + INVENTORY_PIN:
        raise ValueError("Canonical inventory differs")
    entry, manifest = scope_inventory(binding, inventory)
    content = cold.verified(manifest, entry["manifest_digest"])
    chunk = first_member(ShortWindowManifestV2.model_validate_json(content))
    segment = root / manifest.parent.name
    segment.mkdir()
    (segment / "manifest.json").write_bytes(content)
    copy_one(manifest.with_name(chunk.index_relative_path), segment / chunk.index_relative_path,
             chunk.index_bytes, chunk.index_sha256)
    payload = manifest.with_name(chunk.payload_relative_path)
    observations = snapshot(payload, chunk.compressed_bytes, query)
    before = resource.getrusage(resource.RUSAGE_SELF)
    cpu, wall = process_time_ns(), perf_counter_ns()
    count = copy_one(payload, segment / chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256)
    clocks = dict(cpu_ns=process_time_ns()-cpu, wall_ns=perf_counter_ns()-wall)
    after = resource.getrusage(resource.RUSAGE_SELF)
    staged = dict(source=str(payload), member=chunk.model_dump(mode="json"), staged_bytes=count,
                  original_before=observations, original_after=snapshot(payload, chunk.compressed_bytes, query),
                  process_input_blocks=after.ru_inblock-before.ru_inblock, **clocks)
    freeze(root / "scope.json", dict(entry=dict(entry, path=str(segment)), member=staged["member"]))
    return segment / chunk.payload_relative_path, staged


def acquire(root, arm):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    from tools import algo08_scan
    from tools.pipeline_eval.qualification import blind_compact_run as blind
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes

    scope = json.loads((root / "scope.json").read_bytes())
    spec = json.loads(cold.verified(cold.PAYLOAD / "spec.json", cold.SPEC_SHA))
    for name, pin in cold.RUNTIME.items():
        cold.verified(Path(import_module(name).__file__), pin)
    short = ORIGINAL / "short-primary.so"
    cold.verified(short, SHORT_SHA)
    cold.verified(cold.PAYLOAD / "receiver.so", INSTALLED_SHA)
    cold.verified(root / "assets/lower.f32", PILOT_SHA["lower"])
    hasher = cold.PAYLOAD / "paired-sha256.so"
    cold.verified(hasher, spec["paired_sha256"]["sha256"])
    if not PairedSha256(hasher).hardware:
        raise ValueError("The comparison requires the release paired SHA-256 path")
    buffer = cold.frozen_function(spec, "receiver_ingress.py", "compressed_input_buffer")
    lookahead = cold.frozen_function(spec, "receiver_member_lookahead.py", "compressed_member_lookahead")

    mix = MixedApertureDetector(short, SHORT_SHA, full_coverage=True) if arm == "full-short" else None
    detector_pin = canonical_digest(recipe(INSTALLED_SHA))[7:] if mix else INSTALLED_SHA
    original_detector = mix.detector if mix else algo08_scan.detector
    ledger, iq, native_cpu, native_wall, members = {}, [], Counter(), Counter(), []
    active = None

    class Bounded(FastSegmentSource):
        def __init__(self, entry):
            super().__init__(entry, stop_sequence=WINDOWS)
            if first_member(self.reader.manifest).model_dump(mode="json") != scope["member"]:
                raise ValueError("Staged member differs from the frozen manifest")

        def windows(self):
            for window in super().windows():
                iq.append(window.iq_sha256)
                yield window

    class TimedNative(blind.Native):
        def __init__(self, path, asset):
            super().__init__(path, asset)
            self.attach("cancellation_factors", "full", 2)
            self.attach("cancellation_primary_factors", "short_primary", 1)

        def attach(self, symbol, mode, maximum):
            fn = getattr(self.lib, symbol, None)
            if fn is None:
                return
            fn.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(blind.Factor)]
            fn.restype = ct.c_int

            def call(ctx, data, lane, lo, hi, out):
                begin = process_time_ns(), perf_counter_ns()
                count = fn(ctx, data, lane, lo, hi, out)
                native_cpu[mode] += process_time_ns()-begin[0]
                native_wall[mode] += perf_counter_ns()-begin[1]
                key = (active, lane)
                if active is None or key in ledger or not 0 <= count <= maximum:
                    raise ValueError("Invalid signed lane result or repeated native call")
                ledger[key] = dict(mode=mode, factors=[tuple(getattr(out[i], f) for f, _ in blind.Factor._fields_)
                                                      for i in range(count)])
                return count

            setattr(self.lib, symbol, call)

    @contextmanager
    def observed(*args, **kwargs):
        with original_detector(*args, **kwargs) as receive:
            def visit(window):
                nonlocal active
                active = window.acquisition["global_visit"]
                try:
                    return receive(window)
                finally:
                    active = None

            yield visit

    original_member = ShortWindowReader._member

    def member(reader, name, size, digest):
        if name not in (scope["member"]["index_relative_path"], scope["member"]["payload_relative_path"]):
            raise ValueError("Read attempted outside the frozen index and compressed member")
        contents = original_member(reader, name, size, digest)
        members.append([name, size, digest])
        return contents

    start = process_time_ns(), perf_counter_ns()
    with (buffer(), lookahead() as hints, paired_decoded_hashes(hasher),
          patch.object(ShortWindowReader, "_member", member), patch.object(blind, "Native", TimedNative),
          patch.object(algo08_scan, "FastSegmentSource", Bounded), patch.object(algo08_scan, "detector", observed),
          patch.dict(algo08_scan.PINS, {"cancellation-factors.so": detector_pin})):
        packet = algo08_scan.acquire(SESSION, "sha256:" + INVENTORY_PIN,
                                     dict(segments=[scope["entry"]], window_count=WINDOWS), root / "assets")
    cpu, wall = process_time_ns()-start[0], perf_counter_ns()-start[1]
    source, provenance = packet["source"], packet["provenance"]
    probes = source["probes"]
    keys = [(p["visit_index"], p["receiver_id"]) for p in probes]
    raw = canonical_digest(["sha256:" + INVENTORY_PIN, iq])
    if (len(iq) != WINDOWS or len(members) != 2 or hints.attempts != 0 or keys != list(ledger)
            or len(keys) != 2 * provenance["processed_windows"]
            or provenance["processed_windows"] + provenance["invalid_capture"] != WINDOWS
            or source["raw_recording_authority_digest"] != raw
            or source["analysis_manifest_sha256"] != canonical_digest(["cancellation", raw, detector_pin, probes])):
        raise ValueError("Complete signed acquisition did not bind the expected one-member traversal")
    return dict(arm=arm, acquire_cpu_ns=cpu, acquire_wall_ns=wall, original_member_reads=members,
                advice=asdict(hints), native_cpu_ns=dict(native_cpu), native_wall_ns=dict(native_wall),
                native_schedule=mix.receipt() if mix else None, iq=iq, packet=packet,
                trace=[dict(visit=k[0], lane=k[1], **row) for k, row in ledger.items()])


def comparable(packet):
    return (packet["clock_anchor"], packet["delivery_clocks"],
            packet["source"]["raw_recording_authority_digest"], packet["provenance"]["excluded_windows"],
            [dict(p, candidates=[]) for p in packet["source"]["probes"]])


def selected(probe):
    fields = ("candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
              "fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score")
    return [tuple(row[k] for k in fields) for row in probe["candidates"]]


def factor_delta(reference, candidate):
    from .receiver_polyphase_trial import match_factors

    matched = match_factors(reference, candidate)
    left, right = map(set, zip(*matched)) if matched else (set(), set())
    order = [j for _, j in matched]
    return dict(common=[list(pair) for pair in matched], same_rank=sum(reference[i][0] == candidate[j][0]
                                                                     for i, j in matched),
                exact=sum(factor_bytes([reference[i]]) == factor_bytes([candidate[j]]) for i, j in matched),
                order_changed=any(a > b for a, b in zip(order, order[1:])),
                missing=[i for i in range(len(reference)) if i not in left],
                new=[j for j in range(len(candidate)) if j not in right])


def compare(stock, mixed):
    if stock["iq"] != mixed["iq"] or comparable(stock["packet"]) != comparable(mixed["packet"]):
        raise ValueError("Arms disagree on signed visit authority, order or exclusions")
    by_mode = {"full": Counter(), "short_primary": Counter()}
    evidence = []
    for a, b, ap, bp in zip(stock["trace"], mixed["trace"], stock["packet"]["source"]["probes"],
                            mixed["packet"]["source"]["probes"], strict=True):
        key = (ap["visit_index"], ap["receiver_id"])
        if any((row["visit"], row["lane"]) != key for row in (a, b)) or a["mode"] != "full":
            raise ValueError("Native factor trace is not aligned with signed lane order")
        if b["mode"] == "full" and factor_bytes(a["factors"]) != factor_bytes(b["factors"]):
            raise ValueError("A scheduled anchor altered full native factor bytes")
        changes = {}
        for kind, lhs, rhs in (("native", a["factors"], b["factors"]), ("selected", selected(ap), selected(bp))):
            delta = factor_delta(lhs, rhs)
            for name, value in delta.items():
                by_mode[b["mode"]][kind + "_" + name] += len(value) if isinstance(value, list) else value
            changes[kind] = dict(stock=lhs, mixed=rhs, **delta)
        by_mode[b["mode"]]["lanes"] += 1
        evidence.append(dict(visit=key[0], lane=key[1], mixed_mode=b["mode"], **changes))
    return dict(by_mode=by_mode, lanes=evidence)


def owner_index(rows):
    index = {obs: dict(order=n, norad=norad, role=role) for n, (obs, norad, role) in enumerate(rows)}
    if len(index) != len(rows):
        raise ValueError("Sealed final owner identity is duplicated")
    return index


def audit_owners(root):
    from leo.analysis.localization_v3.tracks import winning_observations

    receipt = json.loads((root / "receipt.json").read_bytes())
    controls = {row["arm"]: json.loads(cold.verified(root / ("1-" + row["arm"] + ".json"), row["trace_sha256"]))
                for row in receipt["arms"] if row["pair"] == 1}
    prefix = controls["stock"]["packet"]
    score = json.loads(cold.verified(SOLVE_SCORE, SOLVE_SCORE_PIN))
    request, solve = score["request"], score["results"]["stock"]
    pin = request["native_sha256"]
    named = json.loads(cold.verified(Path(request["native_file"]), pin))
    source = named["source"]
    probes = [p for p in source["probes"] if p["visit_index"] < WINDOWS]
    exclusions = [e for e in named["provenance"]["excluded_windows"] if e["visit"] < WINDOWS]
    if (request["case"] != CASE or source["session_id"] != SESSION or prefix["source"]["session_id"] != SESSION
            or source["input_manifest_sha256"] != "sha256:" + INVENTORY_PIN
            or source["raw_recording_authority_digest"] != request["raw_authority"]
            or solve["terminal"]["native_sha256"] != "sha256:" + pin
            or named["provenance"]["detector_sha256"] != "sha256:" + INSTALLED_SHA
            or prefix["clock_anchor"] != named["clock_anchor"] or prefix["delivery_clocks"] != named["delivery_clocks"][:WINDOWS]
            or prefix["source"]["probes"] != probes or prefix["provenance"]["excluded_windows"] != exclusions):
        raise ValueError("Fresh stock prefix does not reproduce the sealed named full-recording detections")
    winners, _ = winning_observations(named)
    winners = {row["observation_id"]: row for row in winners}
    owners = {arm: owner_index(rows) for arm, rows in solve["selected_rows"].items()}
    if set(owners) != {"c0", "fitted_c"} or any(
            len(index) != score["owners"][arm]["stock"] or not index.keys() <= winners.keys()
            for arm, index in owners.items()):
        raise ValueError("Final owner rows do not bind to the sealed detector observations")
    evidence, counts, new_on_same_counter = [], {k: Counter() for k in owners}, 0
    deltas = compare(controls["stock"], controls["full-short"])["lanes"]
    for probe, delta in zip(probes, deltas, strict=True):
        change = delta["selected"]
        if not change["stock"]:
            continue
        prior, = change["stock"]
        counter, receiver = probe["valid_start_counter"], probe["receiver_id"]
        oid = "sha256:" + sha256(f"{SESSION}:{receiver}:{counter}".encode()).hexdigest()
        winner = winners[oid]
        if (winner["native_receiver_id"], winner["channel"], winner["actual_rf_hz"], winner["measured_cfo_hz"]) != (
                receiver, probe["channel"], probe["actual_rf_hz"], prior[3]):
            raise ValueError("Owner identity does not uniquely resolve to the genuine signed prefix observation")
        member = {arm: index.get(oid) for arm, index in owners.items()}
        matched = bool(change["common"])
        candidate = next(iter(change["mixed"]), None)
        new_on_same_counter += bool(candidate is not None and not matched)
        native_remnant = bool(factor_delta([prior], delta["native"]["mixed"])["common"])
        for arm, owner in member.items():
            counts[arm][("common" if matched else "missing") + ("_owned" if owner else "_unowned")] += 1
        evidence.append(dict(visit=probe["visit_index"], receiver=receiver, channel=probe["channel"],
                             valid_start_counter=counter, actual_rf_hz=probe["actual_rf_hz"], observation_id=oid,
                             stock=prior, mixed=candidate, matched=matched, exact=bool(change["exact"]),
                             cfo_difference_hz=None if candidate is None else candidate[3]-prior[3],
                             wrapped_epoch_difference_samples=None if candidate is None else
                             remainder(candidate[1]+candidate[2]-prior[1]-prior[2], 13_333),
                             retained_in_mixed_native=native_remnant, owners=member))
    return dict(score_sha256=SOLVE_SCORE_PIN, named_packet_sha256=pin, exact_prefix=True,
                owner_count={arm: len(index) for arm, index in owners.items()}, by_arm=counts,
                unpaired_new_on_named_counter=new_on_same_counter, rows=evidence)


def run(root):
    from tools.pipeline_eval.qualification.cache_residency import load_query

    machine = check_machine()
    root = root.resolve()
    if root.parent != Path("/dev/shm"):
        raise ValueError("A fresh tmpfs child directory is required")
    root.mkdir(mode=0o700)
    cold.verified(cold.CACHE_LIBRARY, cold.CACHE_SHA)
    query = load_query(cold.CACHE_LIBRARY)
    payload, staging = stage(root, query)
    assets = root / "assets"
    assets.mkdir()
    (assets / "cancellation-factors.so").symlink_to(cold.PAYLOAD / "receiver.so")
    (assets / "lower.f32").symlink_to(cold.RELEASE / "assets/lower.f32")
    arms, reference, evidence = [], {}, None
    for pair, order in enumerate(ORDERS, 1):
        for arm in order:
            output = root / f"{pair}-{arm}.json"
            resident = snapshot(payload, COMPRESSED, query)
            usage = resource.getrusage(resource.RUSAGE_CHILDREN)
            start = perf_counter_ns()
            completed = subprocess.run([sys.executable, "-BP", "-m", __spec__.name, "worker", str(root), arm,
                                        str(output)], check=False, timeout=25)
            elapsed = perf_counter_ns()-start
            end = resource.getrusage(resource.RUSAGE_CHILDREN)
            completed.check_returncode()
            result = json.loads(output.read_bytes())
            baseline = reference.setdefault(arm, result)
            if any(result[k] != baseline[k] for k in ("iq", "packet", "trace", "original_member_reads")):
                raise ValueError("One detector arm did not reproduce its signed packet after order reversal")
            arms.append(dict(pair=pair, trace_sha256=sha256(output.read_bytes()).hexdigest(), start_tmpfs=resident,
                             end_tmpfs=snapshot(payload, COMPRESSED, query), process_wall_ns=elapsed,
                             process_cpu_s=(end.ru_utime-usage.ru_utime)+(end.ru_stime-usage.ru_stime),
                             process_input_blocks=end.ru_inblock-usage.ru_inblock, status=completed.returncode,
                             compressed_mb_s=COMPRESSED * 1000 / result["acquire_wall_ns"],
                             staged_boundary_mb_s=COMPRESSED * 1000 / (staging["wall_ns"]+result["acquire_wall_ns"]),
                             **{k: v for k, v in result.items() if k not in ("trace", "packet", "iq")}))
        if evidence is None:
            evidence = compare(reference["stock"], reference["full-short"])
    packet = reference["stock"]["packet"]
    freeze(root / "receipt.json", dict(case=CASE, machine=machine, orders=ORDERS, staging=staging, arms=arms,
           inventory_sha256=INVENTORY_PIN, binding_sha256=BINDING_PIN, iq_sha256=reference["stock"]["iq"],
           raw_authority=packet["source"]["raw_recording_authority_digest"], admitted=packet["provenance"]["processed_windows"],
           excluded=packet["provenance"]["excluded_windows"], signed_comparison=evidence,
           budget=dict(compressed_mb=RAW_COMPRESSED_MB, named_historical_s=NAMED_HISTORICAL_S,
                       combined_saved_s=COMBINED_SAVED_S, allowed_acquire_s=ACQUISITION_S, target_mb_s=RATE_MB_S)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="action", required=True)
    sub.add_parser("run").add_argument("root", type=Path)
    sub.add_parser("audit-owners").add_argument("root", type=Path)
    worker = sub.add_parser("worker")
    worker.add_argument("root", type=Path)
    worker.add_argument("arm", choices=ORDERS[0])
    worker.add_argument("output", type=Path)
    args = cli.parse_args()
    if args.action == "run":
        run(args.root)
    elif args.action == "audit-owners":
        check_machine()
        freeze(args.root / "owner-audit.json", audit_owners(args.root))
    else:
        check_machine()
        freeze(args.output, acquire(args.root, args.arm))
