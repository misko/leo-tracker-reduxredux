#!/usr/bin/env python3
"""Frozen whole-dwell RX1 comparison through the read-only saved-IQ port."""

from __future__ import annotations

import argparse
import hashlib
import json
import signal
import time
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.research.arm_presence import fresh_glrt
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from tools.evaluate_native_presence_budgets import associated
from tools.native_presence import ROOT, build_dwell_presence
from tools.presence_decision_challenge import passing
from tools.presence_dwell import NativeDwell, unpack
from tools.presence_fftw import fftw_options
from tools.presence_structured_challenge import variant_flags
from tools.qualify_native_presence import digest, write_json
from tools.qualify_scanner_glrt_sdk import _decision

PROTOCOL = ROOT / "config/analysis/arm-presence-dwell-rf-holdout-v1.json"


def validate(protocol):
    fixed = dict(
        schema="org.leo.research.presence-dwell-rf-holdout/v1",
        sweeps=[20, 21, 22, 23, 140, 260],
        receiver=1,
        dwell_ms=120,
        screen_bins=512,
        maximum_confirmations=1,
        seeded=False,
        variant="amplitude-diverse-symbol-supported",
        detector_protocol="config/analysis/arm-presence-native-tone-ci16-v1.json",
        policy={"minimum_exact_score": 0.175, "minimum_margin": 0.025},
        reference_candidates=8,
        reference_margin=0.025,
        reference_offsets_ms=[0, 20, 40, 60, 80, 100],
        association={"maximum_cfo_difference_hz": 8000, "maximum_circular_epoch_difference_us": 2},
        live_rf=False,
    )
    # Canonical JSON distinguishes bool/int and float/int in reviewed settings.
    if any(
        json.dumps(protocol.get(k), sort_keys=True) != json.dumps(v, sort_keys=True)
        for k, v in fixed.items()
    ):
        raise ValueError("unreviewed whole-dwell holdout parameters")
    sessions = protocol.get("sessions")
    if (
        not isinstance(sessions, list)
        or len(sessions) != 4
        or any(set(s) != {"session_id", "rate_hz"} for s in sessions)
        or len({s["session_id"] for s in sessions}) != 4
        or sorted(s["rate_hz"] for s in sessions) != [2500000, 2500000, 5000000, 5000000]
    ):
        raise ValueError("four distinct rate-balanced sessions required")
    return [s * 8 + t for s in protocol["sweeps"] for t in range(8)]


def compare(result, reference, rate, protocol):
    """Reference association is evidence agreement, never an RF absence label."""
    if len(reference) != 6:
        raise ValueError("six reference windows required")
    selected = result["rank"]["order"][0]
    if (
        type(selected) is not int
        or not 0 <= selected < 6
        or result["confirmation_count"] != 1
        or result["confirmation_window_mask"] != 1 << selected
    ):
        raise ValueError("one original ranked confirmation required")
    confirmation = result["confirmations"][0]
    candidates = confirmation["candidates"][: confirmation["candidate_count"]]
    accepted = passing(candidates, protocol["policy"])
    positive = [
        [c for c in group if c["margin"] >= protocol["reference_margin"]] for group in reference
    ]
    # _decision is the same research expectation used to verify SDK observations.
    outcome = _decision({"expected": {"candidates": candidates}}, True)[3]
    matched = any(
        associated(c, ref, rate, protocol["association"])
        for c in accepted
        for ref in positive[selected]
    )
    return dict(
        selected_window=selected,
        outcome=outcome,
        detected=bool(accepted),
        reference_any=any(positive),
        reference_selected=bool(positive[selected]),
        matched_selected=matched,
        reference_windows=[i for i, group in enumerate(positive) if group],
        evaluated_miss_on_reference=outcome == 2 and any(positive),
        unknown_on_reference=outcome == 0 and any(positive),
        unassociated_flag=bool(accepted) and not matched,
    )


def summarize(rows):
    groups = {}
    for rate in (2500000, 5000000):
        part = [r for r in rows if r["rate_hz"] == rate]
        metrics = {
            k: sum(r["comparison"][k] for r in part)
            for k in (
                "detected",
                "reference_any",
                "reference_selected",
                "matched_selected",
                "evaluated_miss_on_reference",
                "unknown_on_reference",
                "unassociated_flag",
            )
        }
        metrics["dwells"] = len(part)
        metrics["native_outcomes"] = {
            str(k): sum(r["comparison"]["outcome"] == k for r in part) for k in (0, 1, 2)
        }
        metrics["flag_recall_any_reference"] = (
            sum(r["comparison"]["detected"] and r["comparison"]["reference_any"] for r in part)
            / metrics["reference_any"]
            if metrics["reference_any"]
            else None
        )
        metrics["associated_selected_recall"] = (
            metrics["matched_selected"] / metrics["reference_selected"]
            if metrics["reference_selected"]
            else None
        )
        metrics["desktop_native_wall_ms"] = {
            k: float(np.quantile([r["native"]["total_wall_ms"] for r in part], q)) if part else None
            for k, q in (("p50", 0.5), ("p99", 0.99), ("max", 1.0))
        }
        groups[str(rate)] = metrics
    # Count descriptive miss bursts only across genuinely adjacent visits to
    # each target. Unread sweeps, unknowns and positives break the sequence.
    history, bursts = {}, []
    for row in rows:
        key = row["session_id"], row["channel"], row["edge"]
        previous = history.get(key, [])
        if not previous or row["visit"] != previous[-1]["visit"] + 8:
            previous = []
        previous = [*previous, row][-3:] if row["comparison"]["outcome"] == 2 else []
        if len(previous) == 3:
            bursts.append(
                dict(
                    session_id=key[0],
                    channel=key[1],
                    edge=key[2],
                    visits=[r["visit"] for r in previous],
                    reference_supported_visits=sum(
                        r["comparison"]["reference_any"] for r in previous
                    ),
                )
            )
        history[key] = previous
    return dict(
        groups=groups,
        consecutive_three_miss_bursts=bursts,
        scope="Reference-relative RF evidence, not operational FAR, true absence "
        "or adaptive RF benefit",
    )


def run(archive, output, prefix, protocol_path=PROTOCOL):
    archive, output = archive.resolve(), output.resolve()
    if output.is_relative_to(archive) or output.is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("output cannot be beneath archive storage")
    protocol = json.loads(protocol_path.read_text())
    indices = validate(protocol)
    store = PersistentHopAnalysisInputStore(PersistentHopIqStore.open_read_only(archive))
    sources = [store.source(s["session_id"]) for s in protocol["sessions"]]
    for spec, source in zip(protocol["sessions"], sources, strict=True):
        if (
            source.sample_rate_hz != spec["rate_hz"]
            or not source.receipt.qualified
            or source.plan.valid_visit_ms != 120
            or 1 not in source.receiver_ids
            or indices[-1] >= len(source.visits)
        ):
            raise ValueError("source metadata differs from frozen selection")
    output.mkdir(parents=True, exist_ok=False)
    detector_path = ROOT / protocol["detector_protocol"]
    detector = json.loads(detector_path.read_text())
    flags = (
        tuple(detector["common_flags"])
        + tuple(f"-DLEO_PRESENCE_{k}={v}" for k, v in detector["variants"][0]["defines"].items())
        + (
            "-DLEO_PRESENCE_DIFFERENTIAL_CI16=1",
            "-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1",
            "-DLEO_PRESENCE_BOUNDED_MAGNITUDE=1",
            "-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION=1",
        )
        + variant_flags(protocol["variant"])
    )
    options = fftw_options(prefix)
    library = build_dwell_presence(
        output / "native.so",
        cflags=flags + options["cflags"],
        ldflags=options["ldflags"],
        dependencies=options["dependencies"],
    )
    reference_sources = [
        *sorted((ROOT / "src/leo/analysis/starlink").glob("*.py")),
        *sorted((ROOT / "src/leo/analysis/starlink").glob("*.c")),
        *sorted((ROOT / "src/leo/analysis/starlink").glob("*.inc")),
        ROOT / "src/leo/analysis/research/arm_presence.py",
        Path(__file__),
        ROOT / "tools/qualify_scanner_glrt_sdk.py",
        ROOT / "tools/presence_dwell.py",
    ]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in reference_sources}
    build = json.loads(library.with_name("native.so.build.json").read_text())
    freeze = dict(
        protocol=protocol,
        protocol_sha256=digest(protocol_path),
        detector_protocol_sha256=digest(detector_path),
        library_sha256=digest(library),
        build=build,
        reference_sources_sha256=hashes,
        source_manifests={s.session_id: s.input_manifest_sha256 for s in sources},
        state="frozen_before_iq_read_or_scoring",
        new_rf=False,
    )
    write_json(output / "freeze.json", freeze)
    rows = []
    with ExitStack() as stack, (output / "results.jsonl").open("x") as stream:
        engines = {}
        for source in sources:
            rate = source.sample_rate_hz
            for index in indices:
                visit = source.read_visit(index)
                channel, edge = visit.span.target.channel, visit.span.target.edge
                if channel - 1 + 4 * int(edge == "upper") != index % 8:
                    raise ValueError("holdout requires original fixed-order targets")
                iq = np.ascontiguousarray(visit.samples_ci16[:, source.receiver_ids.index(1), :])
                raw = iq.astype("<i2", copy=False).tobytes()
                iq_hash = hashlib.sha256(raw).hexdigest()
                name = f"{source.session_id}-{index}.ci16"
                with (output / name).open("xb") as retained:
                    retained.write(raw)
                if (rate, edge) not in engines:
                    engines[rate, edge] = stack.enter_context(NativeDwell(library, rate, edge, 512))
                native = unpack(engines[rate, edge].run(iq, maximum=1, seeded=False))
                screens = unpack(engines[rate, edge].screens())
                started = time.monotonic()
                reference = []
                for offset in protocol["reference_offsets_ms"]:
                    window = iq[rate * offset // 1000 : rate * (offset + 20) // 1000]
                    values = window[:, 0].astype(np.float64) + 1j * window[:, 1]
                    reference.append(
                        [
                            asdict(c)
                            for c in fresh_glrt(
                                values,
                                rate,
                                edge=edge,
                                candidate_count=protocol["reference_candidates"],
                            )
                        ]
                    )
                if hashlib.sha256(iq.astype("<i2", copy=False).tobytes()).hexdigest() != iq_hash:
                    raise ValueError("detector mutated original IQ")
                row = dict(
                    session_id=source.session_id,
                    visit=index,
                    rate_hz=rate,
                    rx=1,
                    channel=channel,
                    edge=edge,
                    counter=str(visit.span.valid_device_sample_counter),
                    input_uri=source.input_uri,
                    manifest_sha256=source.input_manifest_sha256,
                    iq_file=name,
                    iq_sha256=iq_hash,
                    native=native,
                    screens=screens,
                    reference=reference,
                    reference_wall_s=time.monotonic() - started,
                    comparison=compare(native, reference, rate, protocol),
                )
                rows.append(row)
                stream.write(json.dumps(row, allow_nan=False) + "\n")
                stream.flush()
                if len(rows) % 8 == 0:
                    print(f"{len(rows)}/192 holdout dwells scored", flush=True)
    if hashes != {str(p.relative_to(ROOT)): digest(p) for p in reference_sources}:
        raise ValueError("reference sources changed during evaluation")
    for name, sha in build["sources_sha256"].items():
        if digest(ROOT / name) != sha:
            raise ValueError("native sources changed during evaluation")
    if (
        digest(protocol_path) != freeze["protocol_sha256"]
        or digest(detector_path) != freeze["detector_protocol_sha256"]
        or digest(library) != freeze["library_sha256"]
    ):
        raise ValueError("frozen input changed during evaluation")
    summary = summarize(rows)
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fftw-prefix", required=True, type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    args = parser.parse_args()
    signal.alarm(1200)  # Bounded desktop analysis; no RF, no multi-hour campaign.
    run(args.archive, args.output, args.fftw_prefix, args.protocol)
