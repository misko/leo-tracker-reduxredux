"""Verify the exact original input and rate through the immutable detection file."""

import gzip
import json

from original_dense_intake import HERE, ORDERS, read, sha, write


SCOPE = HERE / "measurements/zstd-wide-huffman-0008-scope.json.gz"
SCOPE_PIN = "sha256:d0f18a12ed2e149e01902f1713bf95954ed5dd949fd208fe4da45b99b7711791"
ARCHIVED_NATIVE = HERE / "measurements/dense-8ms-anchors.json.gz"
ARCHIVED_NATIVE_PIN = "sha256:d9dd79237e5b35c8e541517752134de79a834be50df2fb808f54ed6c20a35781"
TARGET = 283.1


def rates(size, seconds, process, receiver):
    if any(time <= 0 for time in (seconds, process, receiver)) or not receiver <= seconds <= process:
        raise ValueError("Intake clocks must preserve the original ordered boundaries")
    megabytes = size / 1e6
    return {"through_detections": megabytes / seconds, "through_child_exit": megabytes / process,
            "inner_receiver": megabytes / receiver, "required_seconds_at_target": megabytes / TARGET}


def score(root):
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest

    binding = read(root / "binding.json")
    if sha(SCOPE) != SCOPE_PIN or sha(ARCHIVED_NATIVE) != ARCHIVED_NATIVE_PIN:
        raise ValueError("The independent original 64-window digest witness changed")
    original = json.loads(gzip.decompress(SCOPE.read_bytes()))
    previous_receiver = json.loads(gzip.decompress(ARCHIVED_NATIVE.read_bytes()))["packets"]["mixed8"]
    iq = original["window_iq_sha256"]
    replay = read(root / "resume.json") if (root / "resume.json").exists() else None
    if replay is not None and any(sha(root / name) != pin for name, pin in replay["rejected"].items()):
        raise ValueError("The pre-waveform attempt evidence changed")
    results, evidence, values = [], {mode: set() for mode in ORDERS[0]}, []
    positive = {}
    for index, order in enumerate(ORDERS, 1):
        pair = {}
        for mode in order:
            work = root / f"{index}-{mode}"
            observer = read(work / "worker.json")
            log = read(work.with_suffix(".clock.json"))
            clock = log["process"]
            path = work / observer["native"]
            native = read(path)
            proof = native["provenance"]
            digest = canonical_digest(native)
            bind_native(native, binding["session"], binding["digest"], proof["detector_sha256"][7:])
            hashes = observer["stock_iq"] if mode == "named" else observer["first_use_iq"]
            probes = native["source"]["probes"]
            if (clock["exit_code"] or log["before"] != log["after"] or hashes != iq
                    or digest != sha(path) or native["source"]["raw_recording_authority_digest"] != canonical_digest([binding["digest"], iq])
                    or (proof["window_count"], proof["processed_windows"], proof["invalid_capture"], len(probes)) != (64, 64, 0, 128)
                    or len(native["delivery_clocks"]) != 64 or not clock["started_unix_ns"] <= path.stat().st_mtime_ns <= observer["detector_published_unix_ns"]):
                raise ValueError("The actual scope changed the signed original sample data, opportunities or publication boundary")
            values.append(dict(probes=[dict(p, candidates=[]) for p in probes], delivery_clocks=native["delivery_clocks"],
                               anchor=native["clock_anchor"], end=native["last_sample_counter"]))
            elapsed = (observer["detector_published_unix_ns"]-clock["started_unix_ns"]) / 1e9
            rate = rates(binding["input_bytes"], elapsed, clock["elapsed_s"], observer["receiver_acquire"]["elapsed_s"])
            sealed = dict(detector=proof["detector_sha256"], native=digest, ordered_probes=canonical_digest(probes),
                          raw_authority=native["source"]["raw_recording_authority_digest"],
                          selected=sum(bool(p["candidates"]) for p in probes), visits=proof["window_count"])
            evidence[mode].add((sealed["native"], sealed["detector"]))
            positive[mode] = {(p["visit_index"], p["receiver_id"]) for p in probes if p["candidates"]}
            map_book = None
            if mode == "first_use":
                bundle = work / "legacy-first-maps"
                custody = read(bundle / "custody.json")
                member, = custody["members"]
                path_map = bundle / member["map"]
                if (custody != observer["first_use"]["verified_plan"] or sha(path_map) != member["map_sha256"]
                        or sha(bundle / "custody.json") != observer["first_use_bundle_sha256"]
                        or custody["raw_authority"] != sealed["raw_authority"] or member["map_kind"] != "exception"
                        or observer["first_use"]["authority_mode"] != "verified-first-use"
                        or probes != previous_receiver["probes"]):
                    raise ValueError("The original first-use reader did not durably publish its independently verified exception map")
                held = read(work.with_name(work.name + "-held-anchor-route.json"))
                map_book = dict(custody=custody, map_bytes=path_map.stat().st_size, held_selector=held,
                                preparation=observer["first_use"], publication_clock=observer["first_use_bundle_publication"])
            pair[mode] = dict(through_detections_s=elapsed, inner_receiver=observer["receiver_acquire"], throughput_MB_s=rate,
                              source=sealed, process=clock, launch=log, maps=map_book)
        results.append(pair)
    if any(value != values[0] for value in values) or any(len(pins) != 1 for pins in evidence.values()) or evidence["named"] == evidence["first_use"]:
        raise ValueError("The repeated signed receiver arms must be reproducible and retain matching original opportunities")
    write(root / "result.json", dict(qualified=True, case="DS30-0008", binding=binding, independent_original_scope=SCOPE_PIN,
        actual_original_members=1, position_solve=False, source_resident=True, replay=replay, pairs=results,
        original_opportunity_digest=canonical_digest(values[0]), target_MB_s=TARGET,
        previous_20_8_probe_parity=ARCHIVED_NATIVE_PIN, common_positive_lanes=len(positive["named"] & positive["first_use"]),
        dense_original_members_1_and_2_local=False, previous_framed_24_visit_fixture_excluded=True))
