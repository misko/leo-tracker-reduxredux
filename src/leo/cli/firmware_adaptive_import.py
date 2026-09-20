"""Import sealed v0.52 RX0 archives into the immutable adaptive IQ store."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Literal, cast

import numpy as np
import zstandard as zstd

from leo.contracts.digests import sha256_digest
from leo.contracts.radio import RadioSettingsV1, ReceiverGainV1
from leo.contracts.states import GainMode
from leo.scanner.adaptive_hop import (
    AdaptiveHopDecisionV1,
    AdaptiveHopEventV1,
    AdaptiveHopPolicyV1,
)
from leo.scanner.host_adaptive import (
    HostAdaptiveHopPlanV2,
    HostAdaptiveHopPlanV3,
    HostAdaptiveHopReceiptV2,
    HostAdaptiveHopReceiptV4,
    HostAdaptiveHopReceiptV5,
    HostAdaptiveHopTerminalV2,
    HostDecisionConfigurationV1,
    HostDecisionConfigurationV2,
    HostDecisionRecordV1,
    HostDecisionRecordV2,
)
from leo.scanner.host_adaptive_ports import HostAdaptiveHopVisitBlock
from leo.scanner.models import scheduled_low_band_targets
from leo.scanner.persistent_hop import (
    PersistentHopProfileV1,
    PersistentHopRestorationReceiptV1,
    persistent_hop_wire_session_id,
)
from leo.scanner.single_rx import (
    SingleRxHopTimingV2,
    SingleRxHopTimingV3,
    SingleRxMultiratePersistentHopPlanV3,
    SingleRxPersistentHopPlanV2,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.errors import BundleNotFoundError

SERIAL = "104000bac4950008230026001b440a003a"
URI = "ip:192.168.1.17"


class UnsupportedFirmwareArchiveError(ValueError):
    """A sealed older archive cannot be represented by the canonical pilot contract."""


def _load(path: Path) -> tuple[dict, bytes]:
    payload = path.read_bytes()
    document = json.loads(payload)
    if document.get("schema") != "org.leo.firmware-adaptive-iq/v1":
        raise ValueError("unsupported firmware adaptive archive")
    if document.get("physical_receiver") != 0 or document["evidence"].get("radio_serial") != SERIAL:
        raise ValueError("firmware archive is not the pinned radio RX0 source")
    return document, payload


def _decision_configuration(
    rate: int, digest: str
) -> HostDecisionConfigurationV1 | HostDecisionConfigurationV2:
    detector_digest = f"sha256:{digest}"
    if rate == 10_000_000:
        return HostDecisionConfigurationV1(detector_manifest_sha256=detector_digest)
    if rate not in (15_000_000, 20_000_000):
        raise ValueError("firmware adaptive source rate is unsupported")
    wide_rate = cast(Literal[15_000_000, 20_000_000], rate)
    if wide_rate == 15_000_000:
        factor: Literal[6, 8] = 6
        taps: Literal[201, 257] = 201
        delay: Literal[100, 128] = 100
    else:
        factor, taps, delay = 8, 257, 128
    return HostDecisionConfigurationV2(
        detector_manifest_sha256=detector_digest,
        source_rate_hz=wide_rate,
        decimation_factor=factor,
        filter_taps=taps,
        group_delay_source_samples=delay,
    )


def _settings(value: dict) -> RadioSettingsV1:
    mode = GainMode.MANUAL if value["gain_modes"][0] == "manual" else GainMode.SLOW_ATTACK
    return RadioSettingsV1(
        center_frequency_hz=int(value["center_frequency_hz"]),
        sample_rate_hz=int(value["sample_rate_hz"]),
        bandwidth_hz=int(value["bandwidth_hz"]),
        receiver_ids=(0,),
        gain_mode=mode,
        gains=(
            (ReceiverGainV1(receiver_id=0, gain_db=float(value["gain_db"][0])),)
            if mode is GainMode.MANUAL
            else ()
        ),
    )


def _plan(document: dict) -> HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3:
    setup = document["setup"]
    rate = int(setup["source_rate_hz"])
    profiles = tuple(
        PersistentHopProfileV1(target_index=index, fastlock_profile_index=index, target=target)
        for index, target in enumerate(scheduled_low_band_targets(bandwidth_hz=5_000_000))
    )
    policy = AdaptiveHopPolicyV1(mode="adaptive", generation=int(setup["generation"]))
    decision = _decision_configuration(rate, setup["analysis_digest"])
    if rate == 10_000_000:
        geometry = SingleRxPersistentHopPlanV2(
            receiver_ids=(0,),
            gain_db=40.0,
            transition_guard_samples=rate // 1000,
            samples_per_block=1_000_000,
            kernel_buffers=16,
            profiles=profiles,
        )
        return HostAdaptiveHopPlanV2(
            geometry=geometry,
            classification_receiver=0,
            policy=policy,
            decision=cast(HostDecisionConfigurationV1, decision),
        )
    wide_rate = cast(Literal[15_000_000, 20_000_000], rate)
    wide_geometry = SingleRxMultiratePersistentHopPlanV3(
        sample_rate_hz=wide_rate,
        bandwidth_hz=wide_rate,
        receiver_ids=(0,),
        gain_db=40.0,
        transition_guard_samples=wide_rate // 1000,
        samples_per_block=1_000_000,
        kernel_buffers=16,
        profiles=profiles,
    )
    return HostAdaptiveHopPlanV3(
        geometry=wide_geometry,
        classification_receiver=0,
        policy=policy,
        decision=cast(HostDecisionConfigurationV2, decision),
    )


def _events(
    document: dict, plan: HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3
) -> tuple[AdaptiveHopEventV1, ...]:
    by_frequency = {
        target.if_center_hz: index
        for index, target in enumerate(scheduled_low_band_targets(bandwidth_hz=5_000_000))
    }
    events: list[AdaptiveHopEventV1] = []
    previous_end: int | None = None
    source_first = max(
        0,
        int(document["visits"][-1]["record"]["valid_end"])
        - plan.geometry.sample_rate_hz * int(document["setup"]["duration_ms"]) // 1000,
    )
    for ordinal, entry in enumerate(document["visits"]):
        record = entry["record"]
        frequency = int(record["frequency_hz"])
        target_index = min(by_frequency, key=lambda value: abs(value - frequency))
        if abs(target_index - frequency) > 10:
            raise UnsupportedFirmwareArchiveError(
                f"visit {ordinal} is not centred on a canonical pilot ({frequency} Hz)"
            )
        canonical_index = by_frequency[target_index]
        valid_start = int(record["valid_start"])
        invalid_start = source_first if previous_end is None else previous_end
        transition_after = valid_start - plan.geometry.transition_guard_samples
        transition_before = max(
            invalid_start, min(int(record["transition_before"]), transition_after)
        )
        event = AdaptiveHopEventV1(
            visit_index=ordinal,
            event_sequence=ordinal,
            device_event_id=ordinal + 1,
            target_index=canonical_index,
            from_profile_index=events[-1].target_index if events else None,
            fastlock_slot=canonical_index,
            target=plan.geometry.profiles[canonical_index].target,
            actual_lo_frequency_hz=frequency,
            actual_if_offset_hz=target_index - frequency,
            invalid_start_counter=invalid_start,
            transition_before_counter=transition_before,
            transition_after_counter=transition_after,
            valid_start_counter=valid_start,
            decision=AdaptiveHopDecisionV1(
                mode="adaptive",
                generation=plan.policy.generation,
                decision_counter=invalid_start,
                basis_visit=ordinal - 1 if ordinal else None,
                proposed_target=canonical_index,
                reason="warmup" if ordinal < len(plan.geometry.profiles) else "weighted",
                active_mask=0,
                quiet_mask=0,
                consecutive_misses=0,
                cooldown_remaining_samples=0,
            ),
        )
        events.append(event)
        previous_end = valid_start + plan.geometry.valid_visit_samples
    return tuple(events)


def _receipt(document: dict, archive_digest: str):
    plan = _plan(document)
    events = _events(document, plan)
    retained = tuple(index for index, entry in enumerate(document["visits"]) if entry["iq"])
    session_id = document["session_id"]
    first, final = (
        events[0].invalid_start_counter,
        events[-1].valid_start_counter + plan.geometry.valid_visit_samples,
    )
    invalid = sum(event.valid_start_counter - event.invalid_start_counter for event in events)
    valid = len(retained) * plan.geometry.valid_visit_samples
    denominator = final - first
    original = _settings(document["evidence"]["preparation"]["original"])
    restored = _settings(document["evidence"]["restoration"]["observed"])
    terminal = HostAdaptiveHopTerminalV2(
        state="completed",
        reason="complete",
        session_id=persistent_hop_wire_session_id(session_id),
        visits_started=len(events),
        events_emitted=len(events),
        next_event_sequence=len(events),
        last_block_sequence=max(0, len(events) - 1),
        last_block_end_counter=(
            events[retained[-1]].valid_start_counter + plan.geometry.valid_visit_samples
            if retained
            else first
        ),
        first_counter=first,
        final_counter=final,
        restore_before_counter=final,
        restore_after_counter=max(final, int(document["terminal"]["restore_after"])),
        restored_lo_frequency_hz=restored.center_frequency_hz,
        active_profile_index=events[-1].target_index,
        restored_profile_index=None,
        startup_invalid_start_counter=first,
        startup_invalid_end_counter_exclusive=events[0].valid_start_counter,
    )
    imported_at = time.monotonic_ns()
    failure = f"firmware-v0.52 source archive {archive_digest}; online host GLRT was not run"
    records = []
    for source_index in retained:
        event = events[source_index]
        common = dict(
            session_id=terminal.session_id,
            generation=plan.policy.generation,
            stream_generation=int(document["setup"]["session"]),
            visit_index=event.visit_index,
            event_sequence=event.event_sequence,
            receiver_id=0,
            target_index=event.target_index,
            valid_start_counter=event.valid_start_counter,
            valid_end_counter_exclusive=event.valid_start_counter
            + plan.geometry.valid_visit_samples,
            configuration_sha256=plan.decision.configuration_sha256,
            submitted_monotonic_ns=imported_at,
            started_monotonic_ns=imported_at,
            completed_monotonic_ns=imported_at,
            feedback_monotonic_ns=imported_at,
            feedback_completed_monotonic_ns=imported_at,
            numerics=None,
            health="detector_failure",
            failure=failure,
            feedback_outcome="unknown",
            feedback_disposition="not_submitted",
            feedback_error="firmware feedback is preserved in the source archive",
        )
        records.append(
            HostDecisionRecordV1.model_validate(common)
            if plan.geometry.sample_rate_hz == 10_000_000
            else HostDecisionRecordV2.model_validate(
                {**common, "source_rate_hz": plan.geometry.sample_rate_hz}
            )
        )
    common_receipt = dict(
        session_id=session_id,
        radio_id="pluto-003a",
        radio_serial=SERIAL,
        radio_uri=URI,
        plan=plan,
        stream_generation=int(document["setup"]["session"]),
        source_span_attested=True,
        kernel_buffers_requested=16,
        kernel_buffers_readback=16,
        terminal=terminal,
        events=events,
        complete_visit_count=len(retained),
        valid_sample_count=valid,
        transition_invalid_sample_count=invalid,
        unclassified_sample_count=denominator - valid - invalid,
        unreceived_tail_sample_count=0,
        duty_denominator_sample_count=denominator,
        valid_duty_ppm=valid * 1_000_000 // denominator,
        duty_target_met=valid * 1_000_000 // denominator >= plan.geometry.minimum_valid_duty_ppm,
        restoration=PersistentHopRestorationReceiptV1(
            status="restored",
            original_settings=original,
            restored_settings=restored,
            receive_buffer_closed=True,
            fastlock_inactive=True,
        ),
        host_decisions=tuple(records),
    )
    missing = (len(events) - len(retained)) * plan.geometry.valid_visit_samples
    if plan.geometry.sample_rate_hz == 10_000_000 and len(retained) == len(events):
        return HostAdaptiveHopReceiptV2(**common_receipt)
    if plan.geometry.sample_rate_hz == 10_000_000:
        return HostAdaptiveHopReceiptV5(
            **common_receipt,
            retained_visit_indices=retained,
            transport_missing_sample_count=missing,
        )
    return HostAdaptiveHopReceiptV4(
        **common_receipt,
        retained_visit_indices=retained,
        transport_missing_sample_count=missing,
    )


def _timing(document: dict, receipt):
    if "counter_utc_timing" in document["evidence"]:
        # Only acquisition/import needs PPU; sealed recording readers do not.
        from pluto_plus.counter_utc import CounterUtcEvidence

        from leo.contracts.digests import canonical_digest
        from leo.scanner.counter_utc import CounterUtcTimingV4

        raw = CounterUtcEvidence.model_validate(document["evidence"]["counter_utc_timing"])
        if (raw.session, raw.generation) != (
            document["setup"]["session"],
            document["setup"]["generation"],
        ):
            raise ValueError("counter UTC evidence belongs to another capture")
        expected_serial = document["evidence"].get("radio_serial")
        if expected_serial is not None and raw.radio_serial != expected_serial:
            raise ValueError("counter UTC radio identity differs from capture")
        first, last = receipt.terminal.first_counter, receipt.terminal.final_counter
        rate = receipt.plan.geometry.sample_rate_hz
        qualified, reason, bound = raw.qualification(first, last, rate)
        try:
            earliest, latest = raw.interval(first)
            estimate = (earliest + latest) // 2
            display_width = latest - earliest
        except ValueError:
            # Retain an explicitly unqualified display time from the original
            # transaction. Never silently fall back to its relaxed qualification.
            legacy = document["evidence"].get("utc_timing", {})
            before = legacy.get("begin_before_realtime_ns")
            after = legacy.get("begin_after_realtime_ns")
            if before is None or after is None:
                raise ValueError(
                    "unqualified counter timing lacks a display clock bracket"
                ) from None
            estimate = (before + after) // 2
            display_width = after - before
        payload = raw.model_dump(mode="json")
        return CounterUtcTimingV4(
            session_id=receipt.session_id,
            session_start_device_sample_counter=first,
            final_device_sample_counter=last,
            sample_rate_hz=rate,
            first_sample_estimate_utc_ns=estimate,
            maximum_error_ns=bound,
            display_bracket_width_ns=display_width,
            qualification_limit_ns=raw.policy.maximum_error_ns,
            failure_reasons=() if qualified else (reason,),
            evidence=payload,
            evidence_sha256=canonical_digest(payload),
        )
    value = document["evidence"].get("utc_timing")
    if not value:
        return None
    model = (
        SingleRxHopTimingV2
        if receipt.plan.geometry.sample_rate_hz == 10_000_000
        else SingleRxHopTimingV3
    )
    return model.from_host_bracket(
        session_id=receipt.session_id,
        session_start_device_sample_counter=receipt.terminal.first_counter,
        sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
        **value,
    )


def import_archive(archive: Path, bulk_root: Path) -> str:
    document, manifest_payload = _load(archive / "manifest.json")
    archive_digest = sha256_digest(manifest_payload)
    receipt = _receipt(document, archive_digest)
    store = AdaptiveHopIqStore(bulk_root)
    try:
        try:
            return store.inspect(receipt.session_id).session_id
        except BundleNotFoundError:
            pass
        writer = store.begin(receipt.session_id, receipt.plan)
        try:
            retained = getattr(
                receipt, "retained_visit_indices", range(receipt.complete_visit_count)
            )
            for source_index, visit in zip(retained, receipt.visits, strict=True):
                entry = document["visits"][source_index]
                iq = entry["iq"]
                assert iq is not None
                compressed = (archive / iq["relative_path"]).read_bytes()
                if sha256_digest(compressed) != iq["compressed_sha256"]:
                    raise ValueError("firmware archive compressed IQ digest mismatch")
                raw = zstd.ZstdDecompressor().decompress(
                    compressed, max_output_size=iq["uncompressed_bytes"]
                )
                if sha256_digest(raw) != iq["uncompressed_sha256"]:
                    raise ValueError("firmware archive IQ digest mismatch")
                pairs = np.frombuffer(raw, dtype="<i2").reshape(-1, 2)
                samples = pairs[:, 0].astype(np.float32) + 1j * pairs[:, 1].astype(np.float32)
                writer.append(HostAdaptiveHopVisitBlock(samples[:, None], (0,), visit))
            writer.finish(receipt, timing=_timing(document, receipt))
        finally:
            writer.abort()
    finally:
        store.close()
    return receipt.session_id


def import_pending(spool_root: Path, bulk_root: Path) -> tuple[tuple[str, ...], tuple[dict, ...]]:
    imported, unsupported = [], []
    for manifest in sorted(spool_root.glob("scan-fw-*/manifest.json")):
        try:
            imported.append(import_archive(manifest.parent, bulk_root))
        except UnsupportedFirmwareArchiveError as error:
            unsupported.append({"session_id": manifest.parent.name, "reason": str(error)})
    return tuple(imported), tuple(unsupported)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spool-root", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, required=True)
    args = parser.parse_args()
    imported, unsupported = import_pending(args.spool_root, args.bulk_root)
    print(json.dumps({"imported": imported, "unsupported": unsupported}, sort_keys=True))


if __name__ == "__main__":
    main()
