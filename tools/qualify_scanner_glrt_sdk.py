"""Build and verify modeled saved-IQ acquisition-SDK replay; never opens RF."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

from leo.contracts.scanner_glrt_frame import DETECTOR_FAILED, DRAIN, FINAL, decode_frame
from tools.native_presence import ROOT, build_scanner_glrt_port
from tools.qualify_native_presence import digest, write_json
from tools.qualify_presence_dwell_worker import _counter, safe_output

BASE = 2**53 + 217
BLOCK = 131072
LEGACY = b"sdk-replay-opaque-legacy"
POSITIVE_PROFILE = "positive-feedback-v1"
PROTECTION_PROFILE = "capture-protection-v1"
COOPERATIVE_PROFILE = "cooperative-skips-v1"
MINIMUM_EXACT_SCORE = 0.175
MINIMUM_MARGIN = 0.025
LIMITATION = (
    "Modeled 121ms cycles with saved RX1 valid IQ, synthetic RX0 and 1ms transition padding; "
    "not original block arrivals, real IIO/IRQ/network load, detection qualification or live duty. "
    "Frame delivery includes waiting for a later carrier; "
    "it is not the per-block callback deadline."
)
FEEDBACK_LIMITATION = (
    " Independent acquisition-owner observation copies are verified; no scheduler thread, "
    "bounded SPSC handoff, adaptive choices, or counterfactual IQ are exercised. "
    "SDK callback costs exclude research JSON logging and source-IQ filling."
)


def build(
    output: Path,
    *,
    compiler="cc",
    cflags=(),
    sdk_library: Path | None = None,
    runtime_rpath: Path | None = None,
    libiio_source: Path | None = None,
):
    """An optional prebuilt SDK is linked unchanged, not rebuilt or copied.

    The literal runtime path supports packaged target tests without a loader
    environment override. Neither option authorizes remote staging or RF.
    """
    if runtime_rpath is not None and (
        not runtime_rpath.is_absolute()
        or ".." in runtime_rpath.parts
        or any(c in str(runtime_rpath) for c in ":,\n\r")
    ):
        raise ValueError("SDK runtime RPATH must be one literal absolute directory")
    if sdk_library is not None:
        sdk_library = sdk_library.resolve(strict=True)
        if not sdk_library.is_file() or sdk_library.name != "libleo-scanner-glrt.so":
            raise ValueError("prebuilt SDK must be libleo-scanner-glrt.so")
    shadow_sources = []
    shadow_flags = []
    if libiio_source is not None:
        libiio_source = libiio_source.resolve(strict=True)
        shadow_sources = [
            ROOT / "tools/scanner_glrt_shadow_replay.c",
            *(
                libiio_source / "iiod" / name
                for name in (
                    "spf-hop-adaptive-policy.c",
                    "spf-hop-scheduler.c",
                    "spf-hop-protocol.c",
                    "spf-hop-adaptive-protocol.c",
                )
            ),
        ]
        if not all(p.is_file() for p in shadow_sources):
            raise ValueError("complete explicit libiio scheduler sources required")
        shadow_flags = [
            "-DLEO_REPLAY_THREADED_SHADOW=1",
            f"-I{libiio_source / 'iiod'}",
            f"-I{ROOT / 'src/leo/scanner/native_presence'}",
        ]
    safe_output(output)
    output.mkdir(parents=True, exist_ok=False)
    sdk = sdk_library or build_scanner_glrt_port(
        output / "libleo-scanner-glrt.so", compiler=compiler, cflags=cflags
    )
    entry = ROOT / "tools/scanner_glrt_sdk_replay.c"
    binary = output / "sdk-replay"
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        raise FileNotFoundError(compiler)
    sources = [
        entry,
        Path(__file__),
        ROOT / "src/leo/scanner/native_presence/scanner_glrt.h",
        ROOT / "src/leo/scanner/native_presence/adaptive_scan.h",
        ROOT / "src/leo/scanner/native_presence/frame_codec.h",
    ]
    if libiio_source is not None:
        sources += (
            shadow_sources
            + [ROOT / "tools/scanner_glrt_shadow_replay.h"]
            + [
                libiio_source / "iiod" / name
                for name in (
                    "spf-hop-adaptive-policy.h",
                    "spf-hop-scheduler.h",
                    "spf-hop-session.h",
                    "spf-hop-protocol.h",
                    "spf-hop-adaptive-protocol.h",
                )
            ]
        )

    def source_key(path):
        return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)

    hashes = {source_key(p): digest(p) for p in sources}
    sdk_hash = digest(sdk)
    command = [
        compiler_path,
        "-std=c11",
        "-O3",
        "-Wall",
        "-Wextra",
        "-Werror",
        *cflags,
        *shadow_flags,
        str(entry),
        *map(str, shadow_sources),
        f"-L{sdk.parent}",
        "-lleo-scanner-glrt",
        (
            f"-Wl,--disable-new-dtags,-rpath,{runtime_rpath}"
            if runtime_rpath is not None
            else "-Wl,-rpath,$ORIGIN"
        ),
        "-pthread",
        "-lm",
        "-o",
        str(binary),
    ]
    subprocess.run(command, check=True)
    if hashes != {source_key(p): digest(p) for p in sources} or sdk_hash != digest(sdk):
        raise RuntimeError("replay build inputs changed")
    write_json(
        binary.with_name(binary.name + ".build.json"),
        dict(
            schema="org.leo.research.sdk-replay-build/v1",
            command=command,
            sources_sha256=hashes,
            dependencies_sha256={str(sdk.resolve()): sdk_hash},
            compiler_sha256=digest(Path(compiler_path).resolve()),
            binary_sha256=digest(binary),
        ),
    )
    return binary


def quantiles(values):
    if not values:
        return None
    return dict(
        zip(
            ("p50", "p95", "p99", "max"),
            np.quantile(values, [0.5, 0.95, 0.99, 1]).tolist(),
            strict=True,
        )
    )


def _decision(source, positive_feedback):
    """Independent expected wire choice and scheduling outcome from frozen numerics.

    A completed miss is not a no-signal wire verdict. An incomplete fractional
    candidate keeps feedback unknown unless another candidate actually passes.
    """
    all_candidates = source["expected"]["candidates"]
    complete = [c for c in all_candidates if c["fractional_complete"]]

    def passes(candidate):
        return (
            positive_feedback
            and candidate["exact_score"] >= MINIMUM_EXACT_SCORE
            and candidate["margin"] >= MINIMUM_MARGIN
        )

    best = max(complete, key=lambda c: (passes(c), c["margin"]), default=None)
    if not positive_feedback:
        return best, "unavailable", "unqualified_classifier", None
    if best is not None and passes(best):
        return best, "starlink", "complete", 1
    outcome = 2 if len(complete) == len(all_candidates) else 0
    return best, "unavailable", "incomplete_search", outcome


def _verify_observations(
    rows,
    groups,
    records,
    jobs,
    blocks,
    rate,
    period,
    dwell,
    guard,
    arrivals,
    unavailable,
    intentional_skips=frozenset(),
):
    observations, finals = groups["observation"], groups["observation-final"]
    if len(observations) != jobs or len(finals) != 1 or rows[-1].get("observations") != jobs:
        raise ValueError("feedback terminal inventory differs")
    positions = {id(row): i for i, row in enumerate(rows)}
    frame_by_block = {r["block"]: r for r in groups["frame"] if r["block"] < blocks}
    latencies, outcomes, per_block = [], [0, 0, 0], {}
    previous_time = 0.0
    for i, row in enumerate(observations):
        source = records[i % len(records)]
        start = BASE + i * period + guard
        _, _, _, outcome = _decision(source, True)
        skipped = i in unavailable
        if skipped:
            outcome = 0
        expected = dict(
            kind="observation",
            session="71",
            generation="9",
            visit=str(i),
            start=str(start),
            end=str(start + dwell),
            rate_hz=rate,
            rx=1,
            target=source["channel"] - 1 + 4 * int(source["edge"] == "upper"),
            outcome=outcome,
            healthy=int(not skipped or i in intentional_skips),
        )
        if any(type(row.get(k)) is not type(v) or row[k] != v for k, v in expected.items()):
            raise ValueError("feedback source binding or outcome differs")
        block, elapsed = row.get("block"), row.get("elapsed_ms")
        ready_block = max(groups["visit"][i]["block"], (i * period + guard + dwell - 1) // BLOCK)
        if skipped:
            ready_block = groups["visit"][i]["block"]
        if (
            type(block) is not int
            or not ready_block <= block <= blocks
            or type(elapsed) not in (float, int)
            or not math.isfinite(elapsed)
            or not max(previous_time, arrivals[ready_block]) <= elapsed <= rows[-1]["elapsed_ms"]
        ):
            raise ValueError("feedback predates input or has invalid clock")
        phase = "drain" if block == blocks else ("after-frame" if block % 2 else "before-frame")
        if row.get("phase") != phase:
            raise ValueError("feedback poll phase differs")
        if block < blocks:
            carrier = frame_by_block[block]
            before = phase == "before-frame"
            if (
                (positions[id(row)] < positions[id(carrier)]) != before
                or (before and elapsed > carrier["elapsed_ms"])
                or (not before and elapsed < carrier["elapsed_ms"])
                or elapsed < arrivals[block]
            ):
                raise ValueError("feedback consumer order or carrier clock differs")
            per_block[block] = per_block.get(block, 0) + 1
            if per_block[block] > 8:
                raise ValueError("unbounded feedback polling")
        elif elapsed < rows[0]["duration_ms"]:
            raise ValueError("feedback drain predates finish")
        previous_time = elapsed
        latencies.append(elapsed - arrivals[ready_block])
        outcomes[outcome] += 1
    final = finals[0]
    if (
        type(final.get("count")) is not int
        or final["count"] != jobs
        or type(final.get("block")) is not int
        or final["block"] != blocks
        or type(final.get("elapsed_ms")) not in (float, int)
        or not math.isfinite(final["elapsed_ms"])
        or not max(previous_time, rows[0]["duration_ms"])
        <= final["elapsed_ms"]
        <= rows[-1]["elapsed_ms"]
        or positions[id(final)] < positions[id(observations[-1])]
    ):
        raise ValueError("invalid feedback terminal receipt")
    return dict(
        observations=len(observations),
        observation_outcomes=dict(
            zip(("unknown", "detected", "not_detected"), outcomes, strict=True)
        ),
        ready_callback_to_observation_ms=quantiles(latencies),
        observation_cpu_ms=quantiles([r["observation_cpu_ms"] for r in groups["block"]]),
        observation_wall_ms=quantiles([r["observation_wall_ms"] for r in groups["block"]]),
    )


def _verify_protection(groups, terminal, decoded, blocks, rate, failed, pressure_smoke):
    monotonic = (
        "peak_occupied_slots",
        "backlog_skips",
        "pressure_skips",
        "history_blocks_skipped",
        "pressure_entries",
        "resumptions",
        "watchdog_trips",
        "clock_faults",
        "disabled",
    )
    fields = (*monotonic, "enabled", "suspended", "occupied_slots")
    previous = dict.fromkeys(monotonic, 0)
    suspended = recovery = entries = resumes = history = 0
    for index, row in enumerate([*groups["block"], terminal]):
        stats = row.get("protection_stats")
        if not isinstance(stats, dict) or set(stats) != set(fields):
            raise ValueError("protection diagnostics missing or different")
        if any(type(stats[k]) is not int or stats[k] < 0 for k in fields):
            raise ValueError("invalid protection diagnostic type")
        if any(stats[k] < previous[k] for k in monotonic):
            raise ValueError("protection counters regressed")
        if (
            stats["enabled"] != 1
            or stats["disabled"] > 1
            or stats["suspended"] > 1
            or stats["occupied_slots"] > 2
            or stats["peak_occupied_slots"] > 2
            or stats["resumptions"] > stats["pressure_entries"]
            or stats["pressure_entries"] > blocks
            or stats["history_blocks_skipped"] > blocks
            or stats["watchdog_trips"] + stats["clock_faults"] > 1
        ):
            raise ValueError("protection bound violated")
        if index < blocks and not stats["disabled"]:
            previous_block = groups["block"][index - 1] if index else None
            busy = (pressure_smoke and 4 <= index < 24) or (
                previous_block is not None
                and previous_block["callback_wall_ms"] >= previous_block["samples"] * 800 / rate
            )
            if busy:
                entries += not suspended
                suspended, recovery = 1, 0
            elif suspended:
                recovery += 1
                if recovery == 4:
                    suspended, recovery = 0, 0
                    resumes += 1
            history += suspended
            if (
                stats["suspended"],
                stats["pressure_entries"],
                stats["resumptions"],
                stats["history_blocks_skipped"],
            ) != (suspended, entries, resumes, history):
                raise ValueError("pressure behavior differs from independent block model")
        previous = {k: stats[k] for k in monotonic}
    counts = {}
    for r in decoded:
        if not r.search_window_mask:
            counts[r.reason] = counts.get(r.reason, 0) + 1
    if (
        stats["backlog_skips"] != counts.get("worker_busy", 0)
        or stats["pressure_skips"] != counts.get("incomplete_search", 0)
        or stats["disabled"] != int(failed)
    ):
        raise ValueError("protection counters disagree with wire inventory")
    return dict(
        protection_stats=stats,
        unavailable_checks=sum(counts.values()),
        unavailable_reasons=counts,
        computed_results=len(decoded) - sum(counts.values()),
        all_checks_computed=not counts,
    )


def _verify_cooperative_skips(groups, decoded, arrivals, blocks, period, dwell, guard):
    """Bind the SDK's decision-site diagnostic to its wire and block receipts.

    Do not decide health from a wire reason alone. Pressure increments must land
    during suspension, after visit registration and before the full input could
    have been submitted. Backlog increments attest the explicit admission gate;
    exact occupancy/age boundaries are additionally tested at the native port.
    """
    observations = groups["observation"]
    if len(observations) != len(decoded):
        raise ValueError("cooperative diagnostic inventory differs")
    causes = {1: [], 2: []}
    for i, (row, record) in enumerate(zip(observations, decoded, strict=True)):
        cause = row.get("skip_cause")
        if type(cause) is not int or cause not in (0, 1, 2):
            raise ValueError("invalid cooperative skip diagnostic")
        expected = (
            0
            if record.search_window_mask
            else {
                "incomplete_search": 1,
                "worker_busy": 2,
                "worker_failed": 0,
                "invalid_input": 0,
            }.get(record.reason)
        )
        if expected != cause:
            raise ValueError("cooperative skip cause disagrees with wire evidence")
        if cause:
            causes[cause].append(i)
    for cause, field in ((1, "pressure_skips"), (2, "backlog_skips")):
        consumed = 0
        for block in range(blocks):
            stats = groups["block"][block]["protection_stats"]
            count = stats[field]
            if not consumed <= count <= len(causes[cause]):
                raise ValueError("cooperative skip counter has no matching visit")
            if count > consumed and (stats["disabled"] or (cause == 1 and not stats["suspended"])):
                raise ValueError("cooperative skip occurred outside owner admission state")
            for visit in causes[cause][consumed:count]:
                registration = groups["visit"][visit]["block"]
                ready = max(registration, (visit * period + guard + dwell - 1) // BLOCK)
                observation = observations[visit]
                if not registration <= block <= ready or not (
                    type(observation.get("block")) is int
                    and observation["block"] >= block
                    and type(observation.get("elapsed_ms")) in (float, int)
                    and observation["elapsed_ms"] >= arrivals[block]
                ):
                    raise ValueError("cooperative skip is not causal for its registered input")
            consumed = count
        if consumed != len(causes[cause]):
            raise ValueError("cooperative skip lacks a block admission receipt")
    return frozenset(causes[1] + causes[2])


def verify(
    raw,
    manifest,
    duration,
    *,
    delay_blocks,
    jitter_ms,
    enabled,
    algorithm_sha256="12" * 32,
    configuration_sha256="34" * 32,
    positive_feedback=False,
    capture_protection=False,
    pressure_smoke=False,
    cooperative_skips=False,
):
    for identity in (algorithm_sha256, configuration_sha256):
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[0-9a-f]{64}", identity)
            or int(identity, 16) == 0
        ):
            raise ValueError("expected replay identity must be nonzero lowercase SHA-256")
    if (
        type(duration) is not int
        or not 242 <= duration <= 300000
        or type(delay_blocks) is not int
        or delay_blocks not in (0, 2)
        or type(jitter_ms) is not int
        or jitter_ms not in (0, 40)
        or type(enabled) is not bool
        or type(positive_feedback) is not bool
        or type(capture_protection) is not bool
        or type(pressure_smoke) is not bool
        or type(cooperative_skips) is not bool
        or (positive_feedback and not enabled)
        or (capture_protection and not positive_feedback)
        or (pressure_smoke and not capture_protection)
        or (cooperative_skips and not capture_protection)
    ):
        raise ValueError("unreviewed replay parameters")
    rows = [json.loads(line) for line in raw.splitlines()]
    if len(rows) < 3 or rows[0].get("kind") != "protocol" or rows[-1].get("kind") != "summary":
        raise ValueError("bounded replay envelope missing")
    protocol, terminal = rows[0], rows[-1]
    rate, records = manifest["rate_hz"], manifest["records"]
    if rate not in (2500000, 5000000) or not 1 <= len(records) <= 48:
        raise ValueError("unqualified saved workload")
    jobs, period, dwell, guard = (
        duration // 121,
        rate * 121 // 1000,
        rate * 120 // 1000,
        rate // 1000,
    )
    expected_protocol = dict(
        kind="protocol",
        schema=(
            "leo-sdk-modeled-positive-feedback-replay-v1"
            if positive_feedback
            else "leo-sdk-modeled-replay-v1"
        ),
        rate_hz=rate,
        duration_ms=duration,
        block_samples=BLOCK,
        jobs=jobs,
        inputs=len(records),
        delay_blocks=delay_blocks,
        jitter_ms=jitter_ms,
        enabled=int(enabled),
        base=str(BASE),
        guard_samples=guard,
        synthetic_rx0_and_transition_padding=True,
        original_arrivals=False,
        live_rf=False,
    )
    if positive_feedback:
        expected_protocol.update(
            positive_profile=POSITIVE_PROFILE,
            minimum_exact_score=MINIMUM_EXACT_SCORE,
            minimum_margin=MINIMUM_MARGIN,
            observations_per_poll=8,
            adaptive_scheduling=False,
        )
    if capture_protection:
        expected_protocol["schema"] = "leo-sdk-protected-positive-feedback-replay-v1"
        expected_protection = dict(
            profile=PROTECTION_PROFILE,
            max_occupied_slots=2,
            admission_age_ms=250,
            worker_timeout_ms=500,
            recovery_blocks=4,
            callback_budget_percent=80,
            pressure_smoke=pressure_smoke,
        )
        actual = protocol.get("capture_protection")
        if (
            not isinstance(actual, dict)
            or set(actual) != set(expected_protection)
            or any(
                type(actual[k]) is not type(v) or actual[k] != v
                for k, v in expected_protection.items()
            )
        ):
            raise ValueError("capture protection profile differs")
    elif "capture_protection" in protocol:
        raise ValueError("unexpected capture protection profile")
    if cooperative_skips:
        expected_protocol["schema"] = "leo-sdk-cooperative-positive-feedback-replay-v1"
        expected_protocol["cooperative_skips_profile"] = COOPERATIVE_PROFILE
    elif "cooperative_skips_profile" in protocol:
        raise ValueError("unexpected cooperative skip profile")
    if any(
        type(protocol.get(k)) is not type(v) or protocol[k] != v
        for k, v in expected_protocol.items()
    ):
        raise ValueError("replay protocol differs")
    if not math.isfinite(protocol["setup_ms"]) or protocol["setup_ms"] < 0:
        raise ValueError("invalid setup clock")
    blocks = (jobs * period + BLOCK - 1) // BLOCK
    if (
        terminal["jobs"] != jobs
        or terminal["blocks"] != blocks
        or not duration <= terminal["elapsed_ms"] <= duration + 5000
    ):
        raise ValueError("incomplete or incorrectly paced replay")
    kinds = ("visit", "block", "frame")
    if positive_feedback:
        kinds += ("observation", "observation-final")
    groups = {kind: [r for r in rows[1:-1] if r["kind"] == kind] for kind in kinds}
    if (
        sum(map(len, groups.values())) != len(rows) - 2
        or len(groups["visit"]) != jobs
        or len(groups["block"]) != blocks
    ):
        raise ValueError("replay event inventory differs")
    arrivals, visits = {}, {}
    for i, row in enumerate(groups["block"]):
        samples = min(BLOCK, jobs * period - i * BLOCK)
        nominal = (i * BLOCK + samples) * 1000 / rate
        requested = nominal + (jitter_ms if i % 4 == 0 else 0)
        if (
            row["block"] != i
            or _counter(row["first"]) != BASE + i * BLOCK
            or row["samples"] != samples
            or not math.isclose(row["nominal_ms"], nominal, abs_tol=1e-7)
            or not math.isclose(row["requested_ms"], requested, abs_tol=1e-7)
        ):
            raise ValueError("modeled block geometry differs")
        for key in ("arrival_ms", "fill_ms", "callback_cpu_ms", "callback_wall_ms"):
            if type(row[key]) not in (float, int) or not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError("invalid callback clock")
        if row["arrival_ms"] + 0.01 < requested or (i and row["arrival_ms"] < arrivals[i - 1]):
            raise ValueError("block arrived before its model schedule")
        if positive_feedback:
            for unit in ("cpu", "wall"):
                cost = row.get(f"observation_{unit}_ms")
                if (
                    type(cost) not in (float, int)
                    or not math.isfinite(cost)
                    or not 0 <= cost <= row[f"callback_{unit}_ms"] + 1e-7
                ):
                    raise ValueError("invalid feedback callback cost")
        arrivals[i] = row["arrival_ms"]
    for i, row in enumerate(groups["visit"]):
        meta = records[i % len(records)]
        start = BASE + i * period + guard
        event_block = (i * period + guard) // BLOCK + delay_blocks
        if (
            row["visit"] != i
            or row["source_index"] != i % len(records)
            or _counter(row["source_visit"]) != meta["visit"]
            or _counter(row["source_counter"]) != _counter(meta["counter"])
            or _counter(row["start"]) != start
            or _counter(row["end"]) != start + dwell
            or row["block"] != event_block
        ):
            raise ValueError("saved-source or modeled visit binding differs")
        visits[i] = row
    unavailable, detector_failed = set(), False
    if not enabled:
        if groups["frame"]:
            raise ValueError("disabled replay emitted classifier data")
        decoded = []
        latencies = []
    else:
        decoded, latencies = [], []
        if len(groups["frame"]) < blocks + 1:
            raise ValueError("carrier or final frame missing")
        for frame_index, row in enumerate(groups["frame"]):
            frame = decode_frame(bytes.fromhex(row["hex"]))
            flag = bool(frame.flags & DETECTOR_FAILED)
            if detector_failed and not flag:
                raise ValueError("detector failure flag regressed")
            detector_failed = detector_failed or flag
            draining = frame_index >= blocks
            if (
                frame.session != 71
                or frame.generation != 9
                or frame.frame_sequence != frame_index
                or frame.algorithm_sha256 != algorithm_sha256
                or frame.configuration_sha256 != configuration_sha256
                or frame.dropped_results
                or frame.result_sequence_limit > jobs
                or (frame_index == len(groups["frame"]) - 1 and frame.result_sequence_limit != jobs)
                or (frame.flags & ~DETECTOR_FAILED if capture_protection else frame.flags)
                != (
                    (DRAIN | FINAL)
                    if frame_index == len(groups["frame"]) - 1
                    else (DRAIN if draining else 0)
                )
                or frame.legacy_metadata != (b"" if draining else LEGACY)
                or row["block"] != (blocks if draining else frame_index)
            ):
                raise ValueError("SDK metadata/frame lifecycle differs")
            if (
                not math.isfinite(row["elapsed_ms"])
                or row["elapsed_ms"] < 0
                or (not draining and row["elapsed_ms"] < arrivals[frame_index])
            ):
                raise ValueError("invalid frame clock")
            for record in frame.results:
                i = len(decoded)
                if i >= jobs:
                    raise ValueError("extra SDK result")
                source = records[i % len(records)]
                candidate, verdict, reason, _ = _decision(source, positive_feedback)
                skipped = capture_protection and record.search_window_mask == 0
                if skipped:
                    if record.verdict != "unavailable" or record.reason not in (
                        "worker_busy",
                        "incomplete_search",
                        "worker_failed",
                        "invalid_input",
                    ):
                        raise ValueError("unqualified unavailable result")
                    unavailable.add(i)
                    candidate, verdict, reason = None, "unavailable", record.reason
                start = BASE + i * period + guard
                if (
                    record.sequence != i
                    or record.visit != i
                    or record.valid_start != start
                    or record.valid_end != start + dwell
                    or record.rate_hz != rate
                    or record.rx != 1
                    or record.channel != source["channel"]
                    or record.edge != source["edge"]
                    or record.verdict != verdict
                    or record.reason != reason
                    or record.search_window_mask != (0 if skipped else 63)
                    or record.search_start != start
                    or record.search_end != (start if skipped else start + dwell)
                ):
                    raise ValueError("SDK result lost, busy, failed, incomplete or misbound")
                expected = dict(
                    exact_score=0.0,
                    control_score=0.0,
                    margin=0.0,
                    cfo_hz=0.0,
                    fractional_offset_samples=0.0,
                    epoch_sample_counter=0,
                    confirmation_start=start,
                    confirmation_end=start,
                )
                if candidate is not None:
                    window = source["expected"]["rank"]["order"][0]
                    beginning = start + window * (rate // 50)
                    expected.update(
                        {
                            k: candidate[k]
                            for k in (
                                "exact_score",
                                "control_score",
                                "margin",
                                "fractional_offset_samples",
                            )
                        }
                    )
                    expected.update(
                        cfo_hz=candidate["tracking_cfo_hz"],
                        epoch_sample_counter=beginning + candidate["epoch"],
                        confirmation_start=beginning,
                        confirmation_end=beginning + rate // 50,
                    )
                if skipped:
                    expected.update(cpu_ms=0.0, wall_ms=0.0)
                for key, value in expected.items():
                    actual = getattr(record, key)
                    if (isinstance(value, int) and actual != value) or (
                        isinstance(value, float)
                        and not math.isclose(actual, value, rel_tol=1e-9, abs_tol=1e-10)
                    ):
                        raise ValueError(f"SDK numerical mismatch: {key}")
                ready_block = max(visits[i]["block"], (i * period + guard + dwell - 1) // BLOCK)
                if skipped:
                    ready_block = visits[i]["block"]
                latency = row["elapsed_ms"] - arrivals[ready_block]
                if latency < 0:
                    raise ValueError("result predates available samples/metadata")
                decoded.append(record)
                latencies.append(latency)
        if len(decoded) != jobs:
            raise ValueError("terminal result inventory incomplete")
    protection = (
        _verify_protection(groups, terminal, decoded, blocks, rate, detector_failed, pressure_smoke)
        if capture_protection
        else {}
    )
    intentional_skips = (
        _verify_cooperative_skips(groups, decoded, arrivals, blocks, period, dwell, guard)
        if cooperative_skips
        else frozenset()
    )
    feedback = (
        _verify_observations(
            rows,
            groups,
            records,
            jobs,
            blocks,
            rate,
            period,
            dwell,
            guard,
            arrivals,
            unavailable,
            intentional_skips,
        )
        if positive_feedback
        else {}
    )
    measured = [r for r in decoded if r.search_window_mask]
    return dict(
        schema=(
            "org.leo.research.sdk-cooperative-feedback-replay-verification/v1"
            if cooperative_skips
            else "org.leo.research.sdk-protected-feedback-replay-verification/v1"
            if capture_protection
            else "org.leo.research.sdk-positive-feedback-replay-verification/v1"
            if positive_feedback
            else "org.leo.research.sdk-replay-verification/v1"
        ),
        verified=True,
        jobs=jobs,
        results=len(decoded),
        blocks=blocks,
        duration_ms=duration,
        rate_hz=rate,
        delay_blocks=delay_blocks,
        jitter_ms=jitter_ms,
        enabled=enabled,
        algorithm_sha256=algorithm_sha256,
        configuration_sha256=configuration_sha256,
        nominal_block_period_ms=BLOCK * 1000 / rate,
        callback_cpu_ms=quantiles([r["callback_cpu_ms"] for r in groups["block"]]),
        callback_wall_ms=quantiles([r["callback_wall_ms"] for r in groups["block"]]),
        source_fill_ms=quantiles([r["fill_ms"] for r in groups["block"]]),
        arrival_lateness_ms=quantiles(
            [max(0.0, r["arrival_ms"] - r["requested_ms"]) for r in groups["block"]]
        ),
        ready_callback_to_frame_ms=quantiles(latencies),
        worker_cpu_ms=quantiles([r.cpu_ms for r in measured]),
        worker_wall_ms=quantiles([r.wall_ms for r in measured]),
        callback_over_nominal_period=sum(
            r["callback_wall_ms"] > BLOCK * 1000 / rate for r in groups["block"]
        ),
        limitations=LIMITATION + (FEEDBACK_LIMITATION if positive_feedback else ""),
        **feedback,
        **protection,
        **({"cooperative_skipped_visits": sorted(intentional_skips)} if cooperative_skips else {}),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("duration", type=int)
    parser.add_argument("--delay-blocks", type=int, choices=(0, 2), default=0)
    parser.add_argument("--jitter-ms", type=int, choices=(0, 40), default=0)
    parser.add_argument("--disabled", action="store_true")
    parser.add_argument("--algorithm-sha256", default="12" * 32)
    parser.add_argument("--configuration-sha256", default="34" * 32)
    parser.add_argument("--positive-feedback", action="store_true")
    parser.add_argument("--capture-protection", action="store_true")
    parser.add_argument("--pressure-smoke", action="store_true")
    parser.add_argument("--cooperative-skips", action="store_true")
    args = parser.parse_args()
    safe_output(args.output)
    checked = verify(
        args.raw.read_text(),
        json.loads(args.manifest.read_text()),
        args.duration,
        delay_blocks=args.delay_blocks,
        jitter_ms=args.jitter_ms,
        enabled=not args.disabled,
        algorithm_sha256=args.algorithm_sha256,
        configuration_sha256=args.configuration_sha256,
        positive_feedback=args.positive_feedback,
        capture_protection=args.capture_protection,
        pressure_smoke=args.pressure_smoke,
        cooperative_skips=args.cooperative_skips,
    )
    write_json(
        args.output,
        dict(checked, raw_sha256=digest(args.raw), manifest_sha256=digest(args.manifest)),
    )
    print(json.dumps(checked, indent=2))


if __name__ == "__main__":
    main()
