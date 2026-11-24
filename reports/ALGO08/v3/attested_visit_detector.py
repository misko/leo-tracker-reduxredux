"""Replay the two actual detector callbacks on detached, individually verified original visits."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
import stat
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SCHEMA = "leo.research.detached-original-prefix-visits.v1"
OUTPUT_SCHEMA = "leo.research.attested-original-visit-detectors.v1"
CURRENT = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so")
ATTESTED = Path("/tmp/leo-ds30-partial-window-attestation01")
RAW_ROOT = Path("/tmp")
RATE, WINDOW_BYTES = 10_000_000, 1_600_000
CASES = {
    "DS30-0163": {
        "held": Path("/dev/shm/leo-v3-ds30-0163-ready01"),
        "native": "f026bb3822ad7a946979a091c55b06d11d7c675e667c564f7d984e9f38fb2651",
        "inventory": "d30888ead13433a1194dec7286e2a71af3d4d78876733eadd8becc06c7121ddd",
        "stage": RAW_ROOT / "leo-v3-0163-first-idle-stage01",
        "start": RAW_ROOT / "leo-v3-0163-first-idle-result01.json",
        "start_pin": "e6dfabaf402fd84179fe69d5f971a906258dd3446456cacc018a6cccff57a6a9",
        "attestation": "f97a78dc990d406237a1c896c1c26d7ce04ce8162722a61b2d01c98ca8c5dd6e",
    },
    "DS30-0419": {
        "held": Path("/dev/shm/leo-v3-nomination-handoff-0419-local01"),
        "native": "50c4ca874573d6e7abb3590e0be9f8099fa87ce7529120d362666dd6a872a5e9",
        "inventory": "bc869c479a0e5c0d4fc4e7b1b19032d3e131c4f741c4910317e8cede3e133256",
        "stage": RAW_ROOT / "leo-v3-0419-first-idle-stage01",
        "start": RAW_ROOT / "leo-v3-0419-first-idle-result01.json",
        "start_pin": "1ce2f2e896c0dfba19cc750937cf9eac06664da036ea5a502be32f4c30113ffd",
        "attestation": "7c50973d2ccc1b16dd59c0019aafb90306b406a94f3f4144e306e339e71fb19c",
    },
}


def pinned(path, digest, root):
    if (not path.is_relative_to(root) or path.resolve(strict=True) != path
            or path.stat().st_dev != root.stat().st_dev or not stat.S_ISREG(path.stat().st_mode)):
        raise ValueError(f"Expected a direct enrolled local file at {path}")
    data = path.read_bytes()
    if pin(data) != "sha256:" + digest.removeprefix("sha256:"):
        raise ValueError(f"Committed file changed at {path}")
    return data


def pin(data):
    return "sha256:" + sha256(data).hexdigest()


def ordered_windows(attested, signed_rows, targets, record, row_type, np):
    position = 0
    windows = []
    choices = attested["windows"]
    if not 0 < len(choices) <= 64:
        raise ValueError("Expected an attested original chronological prefix")
    previous = None
    for visit, (entry, original) in enumerate(zip(choices, signed_rows[:len(choices)], strict=True)):
        row = row_type.model_validate(original)
        target = targets[row.target_id]
        acquisition = row.acquisition
        if (entry["signed_row"] != original or entry["sequence"] != visit or row.sequence != visit
                or acquisition["global_visit"] != visit or row.receiver_count != 2 or entry["receiver_ids"] != [0, 1]
                or entry["target"] != target or row.payload_offset_bytes != position
                or entry["decoded_offset_bytes"] != position or row.payload_bytes != row.sample_count * 8
                or entry["decoded_bytes"] != row.payload_bytes or entry["sha256"] != row.iq_sha256
                or acquisition["sample_end"] - acquisition["sample_start"] != row.sample_count
                or previous is not None and acquisition["sample_start"] < previous):
            raise ValueError(f"Original stereo input/order metadata differs at visit {visit}")
        payload = record[position:position + row.payload_bytes]
        if len(payload) != row.payload_bytes or pin(payload) != row.iq_sha256:
            raise ValueError(f"Original window digest differs at visit {visit}")
        samples = np.frombuffer(payload, dtype="<i2").reshape(row.sample_count, 2, 2)
        windows.append((row, target, samples))
        position += row.payload_bytes
        previous = acquisition["sample_end"]
    if position != len(record):
        raise ValueError("Detached input extends beyond the last complete attested visit")
    return windows


def archive(case, stock_pin):
    from empty_bootstrap import bind_native

    scope = CASES[case]
    root = scope["held"]
    named = json.loads(pinned(root / "native.json", scope["native"], Path("/dev/shm")))
    inventory = json.loads(pinned(root / "inventory.json", scope["inventory"], Path("/dev/shm")))
    if named["source"]["probe_ms"] != 20:
        raise ValueError("Expected the pinned original named 20 ms packet")
    bind_native(named, named["source"]["session_id"], "sha256:" + scope["inventory"], stock_pin,
                expected="sha256:" + scope["native"])
    return scope, named, inventory


def admit(case, attestation_pin, stock_pin):
    import numpy as np
    from leo.contracts.multirate_window_recording import ShortWindowIndexV2, ShortWindowManifestV2

    scope, named, inventory = archive(case, stock_pin)
    first = inventory["segments"][0]
    stage = scope["stage"] / Path(first["path"]).name
    copied = json.loads(pinned(scope["start"], scope["start_pin"], RAW_ROOT))
    copied_digests = copied["original_metadata_body_hashes"]
    if first["manifest_digest"] != copied_digests["manifest.json"] or copied["permit_analysis"] is not False:
        raise ValueError("The incomplete-source receipt differs from the original inventory")
    manifest_bytes = pinned(stage / "manifest.json", first["manifest_digest"], RAW_ROOT)
    manifest = ShortWindowManifestV2.model_validate_json(manifest_bytes)
    chunk = manifest.chunks[0]
    index_path = stage / chunk.index_relative_path
    original_index = pinned(index_path, chunk.index_sha256, RAW_ROOT)
    rows = [json.loads(line) for line in original_index.splitlines()]
    if (manifest.receiver_ids != (0, 1) or manifest.sample_rate_hz != RATE
            or (chunk.first_sequence, chunk.window_count, len(rows)) != (0, 64, 64)
            or chunk.index_sha256 != copied_digests[chunk.index_relative_path]):
        raise ValueError("The original index fails first-member stereo custody")
    prefix = ATTESTED / case
    if attestation_pin.removeprefix("sha256:") != scope["attestation"]:
        raise ValueError("Expected the independent frozen maximal original prefix")
    document = json.loads(pinned(prefix / "visits.json", attestation_pin, RAW_ROOT))
    if (document["schema"] != SCHEMA or document["case"] != case
            or document["original_session"] != named["source"]["session_id"]
            or document["original_inventory_sha256"] != named["source"]["input_manifest_sha256"]
            or document["original_raw_authority"] != named["source"]["raw_recording_authority_digest"]
            or document["manifest_sha256"] != first["manifest_digest"]
            or document["index_sha256"] != chunk.index_sha256
            or document["clock_anchor"] != named["clock_anchor"]
            or document["receiver_ids"] != [0, 1] or document["sample_rate_hz"] != RATE):
        raise ValueError("Attested visit authority differs from original held evidence")
    body = document["verified_file"]
    independent, primary = (document["decoders"][key] for key in ("independent", "primary"))
    matched = ("decoded_bytes", "decoded_sha256")
    stop = document["stop"]
    if (document["original_issued"] != chunk.window_count
            or document["original_encoded_bytes"] != chunk.compressed_bytes
            or document["original_encoded_sha256"] != chunk.compressed_sha256
            or document["encoded_prefix_bytes"] != copied["verified_partial_bytes"]
            or document["encoded_prefix_sha256"] != copied["verified_partial_sha256"]
            or any(document[key] is not False for key in ("complete_compressed_sha_verified",
                "frame_checksum_verified", "normal_acquisition_contract", "recording_acceptance"))
            or document["original_backing_payload_reads"] != 0
            or primary["frame_eof"] is not False
            or primary["encoded_bytes_supplied"] != document["encoded_prefix_bytes"]
            or any(independent[key] != primary[key] for key in matched)
            or (stop["reason"], stop["sequence"]) != ("incomplete_decoded_visit", len(document["windows"]))
            or stop["emitted_bytes"] != document["trailing_decoded_bytes"]
            or not 0 <= stop["emitted_bytes"] < stop["expected_bytes"]
            or primary["decoded_bytes"] != body["bytes"] + stop["emitted_bytes"]):
        raise ValueError("Detached attestation lacks matching bounded decoder or partial-source evidence")
    if (body["name"] != "verified.ci16" or type(body["bytes"]) is not int or not 0 < body["bytes"] <= 64*WINDOW_BYTES
            or (prefix / body["name"]).stat().st_size != body["bytes"]):
        raise ValueError("Detached payload extent is outside the frozen first member")
    record = memoryview(pinned(prefix / body["name"], body["sha256"], RAW_ROOT))
    if len(record) != body["bytes"]:
        raise ValueError("Detached byte extent changed while reading")
    targets = {t["target_id"]: t for t in manifest.configuration["targets"]}
    windows = ordered_windows(document, rows, targets, record, ShortWindowIndexV2, np)
    return document, named, first, chunk, windows, copied


def observation_id(session, lane):
    return pin(f'{session}:{lane["receiver_id"]}:{lane["valid_start_counter"]}'.encode())


def equal_original(left, right):
    from leo.contracts.digests import canonical_json_bytes

    return canonical_json_bytes(left) == canonical_json_bytes(right)


def duration(call, *args):
    cpu, wall = process_time_ns(), perf_counter_ns()
    value = call(*args)
    return value, dict(cpu_ns=process_time_ns()-cpu, elapsed_ns=perf_counter_ns()-wall)


def check_clock(row, named, previous):
    acquisition = row.acquisition
    timing = json.loads(acquisition["retune_receipt"])
    clock, bracket = timing["host_delivery_clock"], timing.get("utc_clock_bracket")
    if (clock != named["delivery_clocks"][row.sequence]
            or (row.sequence == 0 and bracket != named["clock_anchor"])
            or (row.sequence != 0 and bracket is not None)
            or (previous is not None and acquisition["generation"] != previous)
            or type(acquisition["generation"]) is not int):
        raise ValueError(f"Original capture anchor/clock differs at visit {row.sequence}")
    return clock, acquisition["generation"]


def replay(windows, named, spec, source_pins):
    from empty_bootstrap import RELEASE, checked
    from full_short_run import EIGHT_MS_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    import mixed_aperture_receiver as mixed
    from tools.pipeline_eval.qualification import blind_compact_run as stock

    recipe = checked_recipe(eight_ms=True)
    if (spec["schedule"] != "all" or spec.get("fractional_score_selection", False)
            or spec["detector_sha256"] != mixed.INSTALLED_SHA):
        raise ValueError("The named baseline differs from ordinary all-visit cancellation")
    short, full = CURRENT, Path(spec["detector"])
    checked(short, EIGHT_MS_SHA)
    checked(full, spec["detector_sha256"])
    edge = windows[0][1]["edge"]
    pilot = RELEASE / "assets" / (edge + ".f32")
    checked(pilot, mixed.PILOT_SHA[edge])
    probes = named["source"]["probes"]
    excluded = named["provenance"]["excluded_windows"]
    archived = {(row["visit_index"], row["receiver_id"]): row for row in probes
                if row["visit_index"] < len(windows)}
    rejects = {row["visit"]: row for row in excluded if row["visit"] < len(windows)}
    if len(archived) != sum(row["visit_index"] < len(windows) for row in probes):
        raise ValueError("Repeated original named visit/radio key")
    policy = FastScanPolicyV2()
    mixer = mixed.MixedApertureDetector(short, EIGHT_MS_SHA, full_coverage=True)
    full_context, short_context = stock.Native, mixed.NativePath
    original_rule = stock.Continuation
    events = {"named": [], "mixed": [], "history": []}

    class ObservedHistory(original_rule):
        def select(self, row):
            preferred, chosen, votes = super().select(row)
            events["history"].append(dict(probe_before_continuation=row, preferred=preferred,
                                           chosen=chosen, votes=votes))
            return preferred, chosen, votes

    class MeasuredFull(full_context):
        def __init__(self, path, asset):
            super().__init__(path, asset)
            callback = self.lib.cancellation_factors
            callback.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double,
                                 ct.POINTER(stock.Factor)]
            callback.restype = ct.c_int

            def timed(*args):
                count, spent = duration(callback, *args)
                events["named"].append(dict(receiver_id=args[2], aperture="full", **spent))
                return count

            self.lib.cancellation_factors = timed

    class MeasuredMixed(short_context):
        def __init__(self, path, asset, mode):
            super().__init__(path, asset, mode)
            self.mode = mode

        def run(self, samples, lane, center):
            factors, (cpu, wall) = super().run(samples, lane, center)
            events["mixed"].append(dict(receiver_id=lane, aperture=self.mode, cpu_ns=cpu, elapsed_ns=wall,
                                         raw_candidates=[stock.factor_candidate(
                                             rank, epoch, status="complete", offset=offset,
                                             cfo=hz, exact=exact, control=roll, margin=exact-roll)
                                             for rank, epoch, offset, hz, exact, roll in factors]))
            return factors, (cpu, wall)

    roles, ledger = Counter(), []
    generation, session = None, named["source"]["session_id"]
    with ExitStack() as handles:
        with patch.object(stock, "Native", MeasuredFull), patch.object(stock, "Continuation", ObservedHistory):
            named_receiver = handles.enter_context(stock.detector("cancellation", edge, binary=full, pilot=pilot))
        with patch.object(mixed, "NativePath", MeasuredMixed):
            mixed_receiver = handles.enter_context(mixer.detector("cancellation", edge, binary=full, pilot=pilot))
        receivers = {"named": named_receiver, "mixed": mixed_receiver}
        for row, target, samples in windows:
            visit, acquisition = row.sequence, row.acquisition
            if target["edge"] != edge:
                raise ValueError("The single original member changed pilot edge")
            delivery, generation = check_clock(row, named, generation)
            admitted = valid_window_support(acquisition, RATE, samples.shape, (0, 1), policy)
            entry = dict(visit_index=visit, iq_sha256=row.iq_sha256, target=target, acquisition=acquisition,
                         target_id=row.target_id, start_counter=acquisition["sample_start"],
                         end_counter=acquisition["sample_end"], samples=row.sample_count,
                         delivery_clock=delivery, admitted=admitted, lanes=[])
            if not admitted:
                rejected = dict(visit=visit, sample_start=entry["start_counter"], sample_end=entry["end_counter"],
                                iq_sha256=row.iq_sha256, reason="invalid sample support or retune quality")
                if not equal_original(rejects.pop(visit, None), rejected):
                    raise ValueError(f"The named archive disagrees on excluded visit {visit}")
                entry["exclusion"] = rejected
                ledger.append(entry)
                continue
            if samples.shape != (200_000, 2, 2) or samples.flags.writeable:
                raise ValueError("Detector input must be exactly one complete read-only original stereo visit")
            window = SimpleNamespace(acquisition=acquisition, target=target, samples=samples,
                                     sample_rate_hz=RATE, receiver_ids=(0, 1))
            order = ("named", "mixed") if visit % 2 == 0 else ("mixed", "named")
            for value in events.values():
                value.clear()
            measured = {mode: duration(receivers[mode], window) for mode in order}
            entry["callback_order"] = list(order)
            entry["callback_timing"] = {mode: clock for mode, (_, clock) in measured.items()}
            original, candidate = measured["named"][0], measured["mixed"][0]
            for lane, a, b, ac, bc, history in zip(
                    (0, 1), original, candidate, events["named"], events["mixed"], events["history"], strict=True):
                held = archived.pop((visit, lane), None)
                base = {key: val for key, val in a.items() if key != "candidates"}
                if (not equal_original(a, held) or base != {k: v for k, v in b.items() if k != "candidates"}
                        or lane != a["receiver_id"] or lane != ac["receiver_id"] or lane != bc["receiver_id"]):
                    raise ValueError(f"Full named exact set, alias-sensitive factor or metadata differs at {(visit, lane)}")
                entry["lanes"].append(dict(receiver_id=lane, observation_id=observation_id(session, a),
                    original_probe_metadata=base, named_20ms=a, mixed_20_8=b, named_continuation=history,
                    named_native=ac, mixed_native=bc, mixed_role=bc["aperture"]))
                roles[bc["aperture"]] += 1
            if entry["lanes"][0]["mixed_role"] != entry["lanes"][1]["mixed_role"]:
                raise ValueError("Both original antennas must receive the same scheduled aperture")
            ledger.append(entry)
    if archived or rejects or dict(roles) != mixer.receipt()["native_calls"]:
        raise ValueError("Visit replay did not preserve the complete original prefix scope")
    return ledger, dict(named=dict(detector_sha256="sha256:" + spec["detector_sha256"],
                 bound_sources=source_pins, selector="installed chronological continuation"),
            mixed=dict(pre_selector_recipe=recipe, pre_selector_recipe_sha256=canonical_digest(recipe),
                       detector_sha256="sha256:" + EIGHT_MS_SHA, native=mixer.receipt(),
                       selector="complete mixed chronological schedule, before held selector"),
            pilot_sha256="sha256:" + mixed.PILOT_SHA[edge], roles=dict(roles), named_archive_exact=True)


def run(case, output, attestation_pin):
    from dense_geographic_trial import host
    import empty_bootstrap as boot

    machine = host()
    _, specification, sources, _, _ = boot.load_runtime()
    doc, held, entry, member, windows, partial = admit(case, attestation_pin, specification["detector_sha256"])
    rows, detectors = replay(windows, held, specification, {name: pin(body) for name, body in sources.items()})
    from leo.contracts.digests import canonical_json_bytes

    original = dict(session_id=doc["original_session"], inventory_sha256=doc["original_inventory_sha256"],
                    raw_authority=doc["original_raw_authority"], native_sha256="sha256:" + CASES[case]["native"],
                    clock_anchor=doc["clock_anchor"], first_segment=entry, first_member=member.model_dump(mode="json"))
    scope = dict(attestation_sha256="sha256:" + attestation_pin.removeprefix("sha256:"),
                 verified_file=doc["verified_file"], preserved_compressed_prefix_bytes=partial["verified_partial_bytes"],
                 preserved_compressed_prefix_sha256=partial["verified_partial_sha256"],
                 complete_original_frame=False, complete_original_member_encoded_sha_verified=False,
                 complete_original_member_decoded_sha_verified=False, complete_original_frame_checksum_verified=False,
                 original_recording_qualified=False, original_raw_reads=0)
    totals = {mode: {clock: sum(row.get("callback_timing", {}).get(mode, {}).get(clock, 0) for row in rows)
                     for clock in ("cpu_ns", "elapsed_ns")} for mode in ("named", "mixed")}
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence = canonical_json_bytes(dict(schema=OUTPUT_SCHEMA, case=case, original=original, scope=scope,
        detector=detectors, visits=rows, machine=machine, summed_callback_timing=totals, original_waveform_bytes_read=0,
        driver_sha256=pin(Path(__file__).read_bytes())))
    with output.open("xb") as f:
        f.write(evidence)
    with output.with_suffix(".sha256").open("x") as f:
        f.write(pin(evidence) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=CASES)
    cli.add_argument("output", type=Path)
    cli.add_argument("--attestation-sha256", required=True)
    args = cli.parse_args()
    run(args.case, args.output, args.attestation_sha256)
