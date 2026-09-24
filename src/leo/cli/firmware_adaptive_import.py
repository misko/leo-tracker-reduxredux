"""Import sealed v0.52 RX0 archives into the immutable adaptive IQ store."""

from __future__ import annotations

import argparse
import json
import time
from importlib.resources import files
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
    AdaptiveHopEventV2,
    AdaptiveHopEventV3,
    AdaptiveHopPlanV2,
    AdaptiveHopPlanV3,
    AdaptiveHopPlanV4,
    AdaptiveHopPlanV5,
    AdaptiveHopPlanV6,
    AdaptiveHopPolicyV1,
    AdaptiveHopPolicyV2,
    AdaptiveHopReceiptV4,
    AdaptiveHopReceiptV5,
    AdaptiveHopReceiptV6,
    AdaptiveHopTerminalV1,
    AdaptiveHopTerminalV2,
)
from leo.scanner.adaptive_hop_ports import AdaptiveHopVisitBlock
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
    Feature103DualRxPlanV3,
    Feature103DualRxTimingV3,
    Feature104DualRxPlanV4,
    Feature104DualRxTimingV4,
    PersistentHopProfileV1,
    PersistentHopRestorationReceiptV1,
    VariableDualRxPlanV5,
    persistent_hop_wire_session_id,
)
from leo.scanner.single_rx import (
    SingleRxHopTimingV2,
    SingleRxHopTimingV3,
    SingleRxMultiratePersistentHopPlanV3,
    SingleRxPersistentHopPlanV2,
)
from leo.station.geometry import AdaptiveReceiverGeometryBindingV1, StationReceiverGeometryV1
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.errors import BundleNotFoundError

SERIAL = "104000bac4950008230026001b440a003a"
URI = "ip:192.168.1.17"
DUAL_SERIAL = "10400056f695001322002d0010ad1719f2"
DUAL_URI = "ip:192.168.1.21"
DUAL_GEOMETRY_RESOURCE = "gauss-r21-lt3d-001a-20260920-v1.json"


class UnsupportedFirmwareArchiveError(ValueError):
    """A sealed older archive cannot be represented by the canonical pilot contract."""


def _load(path: Path) -> tuple[dict, bytes]:
    payload = path.read_bytes()
    document = json.loads(payload)
    if document.get("schema") != "org.leo.firmware-adaptive-iq/v1":
        raise ValueError("unsupported firmware adaptive archive")
    legacy = (
        document.get("physical_receiver") == 0
        and document["evidence"].get("radio_serial") == SERIAL
    )
    dual = (
        document.get("physical_receivers") == [0, 1]
        and document.get("classifier_physical_receiver") == 1
        and document.get("sample_layout") == "sample_rx_iq_interleaved"
        and document["evidence"].get("radio_serial") == DUAL_SERIAL
        and document.get("setup", {}).get("rx_mask") == 3
        and document.get("setup", {}).get("source_rate_hz") in (2_500_000, 10_000_000, 15_000_000)
    )
    if not (legacy or dual):
        raise ValueError("firmware archive is not the pinned radio RX0 source")
    if document.get("setup", {}).get("protocol_version") == 3 and (
        not dual
        or any(
            entry.get("record", {}).get("protocol_version") != 3
            for entry in document.get("visits", [])
        )
    ):
        raise ValueError("protocol-three archive lacks protocol-three visit records")
    return document, payload


def _is_dual(document: dict) -> bool:
    return document.get("physical_receivers") == [0, 1]


def _is_protocol_three(document: dict) -> bool:
    return _is_dual(document) and document.get("setup", {}).get("protocol_version") == 3


def _dual_geometry_binding() -> AdaptiveReceiverGeometryBindingV1:
    geometry = StationReceiverGeometryV1.model_validate_json(
        files("leo.station").joinpath(DUAL_GEOMETRY_RESOURCE).read_bytes()
    )
    return AdaptiveReceiverGeometryBindingV1.create(
        geometry,
        radio_id="radio_pluto_19f2",
        radio_serial=DUAL_SERIAL,
    )


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


def _settings(value: dict, receiver_ids: tuple[int, ...] = (0,)) -> RadioSettingsV1:
    mode = GainMode.MANUAL if value["gain_modes"][0] == "manual" else GainMode.SLOW_ATTACK
    return RadioSettingsV1(
        center_frequency_hz=int(value["center_frequency_hz"]),
        sample_rate_hz=int(value["sample_rate_hz"]),
        bandwidth_hz=int(value["bandwidth_hz"]),
        receiver_ids=receiver_ids,
        gain_mode=mode,
        gains=(
            tuple(
                ReceiverGainV1(receiver_id=receiver_id, gain_db=float(value["gain_db"][index]))
                for index, receiver_id in enumerate(receiver_ids)
            )
            if mode is GainMode.MANUAL
            else ()
        ),
    )


def _plan(
    document: dict,
) -> (
    AdaptiveHopPlanV2
    | AdaptiveHopPlanV3
    | AdaptiveHopPlanV4
    | AdaptiveHopPlanV5
    | AdaptiveHopPlanV6
    | HostAdaptiveHopPlanV2
    | HostAdaptiveHopPlanV3
):
    setup = document["setup"]
    rate = int(setup["source_rate_hz"])
    target_bandwidth_hz = (
        (10_000_000 if rate == 15_000_000 else rate) if _is_dual(document) else 5_000_000
    )
    profiles = tuple(
        PersistentHopProfileV1(target_index=index, fastlock_profile_index=index, target=target)
        for index, target in enumerate(scheduled_low_band_targets(bandwidth_hz=target_bandwidth_hz))
    )
    if _is_dual(document):
        frequencies = {int(item["record"]["frequency_hz"]) for item in document["visits"]}
        lower = {profile.target.if_center_hz for profile in profiles[:4]}
        upper = {profile.target.if_center_hz for profile in profiles[4:]}
        allowed_mask: Literal[15, 240]
        if frequencies <= {value + offset for value in lower for offset in range(-10, 11)}:
            allowed_mask = 0x0F
        elif frequencies <= {value + offset for value in upper for offset in range(-10, 11)}:
            allowed_mask = 0xF0
        else:
            raise UnsupportedFirmwareArchiveError("dual archive mixes lower and upper edges")
        dual_policy = AdaptiveHopPolicyV2(
            mode="adaptive", generation=int(setup["generation"]), allowed_target_mask=allowed_mask
        )
        if rate not in (2_500_000, 10_000_000, 15_000_000):
            raise UnsupportedFirmwareArchiveError("dual firmware archive rate is unsupported")
        geometry_fields = dict(
            sample_rate_hz=rate,
            bandwidth_hz=rate,
            transition_guard_samples=0,
            kernel_buffers=16,
            samples_per_block=1_000_000,
            profiles=profiles,
        )
        if _is_protocol_three(document):
            if rate not in (2_500_000, 10_000_000):
                raise UnsupportedFirmwareArchiveError(
                    "protocol-three dual firmware rate is unsupported"
                )
            dwell_ms = int(setup["dwell_ms"])
            duration_ms = int(setup["duration_ms"])
            if duration_ms % 1_000:
                raise UnsupportedFirmwareArchiveError(
                    "protocol-three duration must be an integer number of seconds"
                )
            preparation = document["evidence"]["preparation"]["configured"]
            mode = (
                GainMode.MANUAL
                if preparation["gain_modes"][0] == "manual"
                else GainMode.SLOW_ATTACK
            )
            gain_db = float(preparation["gain_db"][0]) if mode is GainMode.MANUAL else None
            return AdaptiveHopPlanV6(
                geometry=VariableDualRxPlanV5.model_validate(
                    {
                        **geometry_fields,
                        "gain_mode": mode,
                        "gain_db": gain_db,
                        "active_valid_visit_ms": dwell_ms,
                        "nominal_duration_seconds": duration_ms // 1_000,
                    }
                ),
                policy=dual_policy,
                classification_receiver=1,
            )
        if rate == 15_000_000:
            return AdaptiveHopPlanV5(
                geometry=Feature104DualRxPlanV4.model_validate(geometry_fields),
                policy=dual_policy,
                classification_receiver=1,
            )
        return AdaptiveHopPlanV4(
            geometry=Feature103DualRxPlanV3.model_validate(geometry_fields),
            policy=dual_policy,
            classification_receiver=1,
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
    document: dict,
    plan: AdaptiveHopPlanV2
    | AdaptiveHopPlanV3
    | AdaptiveHopPlanV4
    | AdaptiveHopPlanV5
    | AdaptiveHopPlanV6
    | HostAdaptiveHopPlanV2
    | HostAdaptiveHopPlanV3,
) -> tuple[AdaptiveHopEventV1 | AdaptiveHopEventV2 | AdaptiveHopEventV3, ...]:
    by_frequency = {
        target.if_center_hz: index
        for index, target in enumerate(profile.target for profile in plan.geometry.profiles)
    }
    events: list[AdaptiveHopEventV1 | AdaptiveHopEventV2 | AdaptiveHopEventV3] = []
    event_model = (
        AdaptiveHopEventV3
        if isinstance(plan, AdaptiveHopPlanV6)
        else AdaptiveHopEventV2
        if isinstance(plan, (AdaptiveHopPlanV4, AdaptiveHopPlanV5))
        else AdaptiveHopEventV1
    )
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
        event_payload = dict(
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
            **(
                {"valid_end_counter_exclusive": int(record["valid_end"])}
                if isinstance(plan, AdaptiveHopPlanV6)
                else {}
            ),
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
        event = event_model.model_validate(event_payload)
        events.append(event)
        previous_end = int(record["valid_end"])
    return tuple(events)


def _event_end(
    event: AdaptiveHopEventV1 | AdaptiveHopEventV2 | AdaptiveHopEventV3,
    plan: AdaptiveHopPlanV4 | AdaptiveHopPlanV5 | AdaptiveHopPlanV6,
) -> int:
    if isinstance(event, AdaptiveHopEventV3):
        return event.valid_end_counter_exclusive
    return event.valid_start_counter + plan.geometry.valid_visit_samples


def _dual_receipt(document: dict):
    plan = _plan(document)
    if not isinstance(plan, (AdaptiveHopPlanV4, AdaptiveHopPlanV5, AdaptiveHopPlanV6)):
        raise TypeError("dual firmware archive produced a single-RX plan")
    events = _events(document, plan)
    if not events:
        raise UnsupportedFirmwareArchiveError("dual firmware archive has no visits")
    retained = tuple(index for index, entry in enumerate(document["visits"]) if entry["iq"])
    if isinstance(plan, AdaptiveHopPlanV4) and len(retained) != len(events):
        raise UnsupportedFirmwareArchiveError(
            "feature-103 sparse dual firmware archive is unsupported"
        )
    session_id = document["session_id"]
    first = events[0].invalid_start_counter
    final = _event_end(events[-1], plan)
    invalid = sum(event.valid_start_counter - event.invalid_start_counter for event in events)
    valid = sum(
        (
            _event_end(events[index], plan) - events[index].valid_start_counter
        )
        for index in retained
    )
    denominator = final - first
    original = _settings(document["evidence"]["preparation"]["original"], (0, 1))
    restored = _settings(document["evidence"]["restoration"]["observed"], (0, 1))
    terminal_model = (
        AdaptiveHopTerminalV2 if isinstance(plan, AdaptiveHopPlanV6) else AdaptiveHopTerminalV1
    )
    terminal = terminal_model(
        state="completed",
        reason="complete",
        session_id=persistent_hop_wire_session_id(session_id),
        visits_started=len(events),
        events_emitted=len(events),
        next_event_sequence=len(events),
        last_block_sequence=len(events) - 1,
        last_block_end_counter=final,
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
    common = dict(
        session_id=session_id,
        radio_id="radio_pluto_19f2",
        radio_serial=DUAL_SERIAL,
        radio_uri=DUAL_URI,
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
    )
    if isinstance(plan, AdaptiveHopPlanV6):
        missing = sum(
            _event_end(event, plan) - event.valid_start_counter
            for index, event in enumerate(events)
            if index not in retained
        )
        return AdaptiveHopReceiptV6(
            **common,
            retained_visit_indices=retained,
            transport_missing_sample_count=missing,
        )
    if isinstance(plan, AdaptiveHopPlanV5):
        return AdaptiveHopReceiptV5(
            **common,
            retained_visit_indices=retained,
            transport_missing_sample_count=(
                (len(events) - len(retained)) * plan.geometry.valid_visit_samples
            ),
        )
    return AdaptiveHopReceiptV4(**common)


def _receipt(document: dict, archive_digest: str):
    if _is_dual(document):
        return _dual_receipt(document)
    plan = cast(HostAdaptiveHopPlanV2 | HostAdaptiveHopPlanV3, _plan(document))
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
    value = document["evidence"].get("utc_timing")
    if not value:
        return None
    if isinstance(receipt, (AdaptiveHopReceiptV4, AdaptiveHopReceiptV5, AdaptiveHopReceiptV6)):
        if isinstance(receipt, AdaptiveHopReceiptV5):
            return Feature104DualRxTimingV4.from_host_bracket(
                session_id=receipt.session_id,
                session_start_device_sample_counter=receipt.terminal.first_counter,
                sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
                **value,
            )
        return Feature103DualRxTimingV3.from_host_bracket(
            session_id=receipt.session_id,
            session_start_device_sample_counter=receipt.terminal.first_counter,
            sample_rate_hz=receipt.plan.geometry.sample_rate_hz,
            **value,
        )
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
        writer = store.begin(
            receipt.session_id,
            receipt.plan,
            receiver_geometry=_dual_geometry_binding() if _is_dual(document) else None,
        )
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
                if _is_dual(document):
                    pairs = np.frombuffer(raw, dtype="<i2").reshape(-1, 2, 2)
                    dual_samples = np.ascontiguousarray(
                        pairs[:, :, 0].astype(np.float32) + 1j * pairs[:, :, 1].astype(np.float32),
                        dtype=np.complex64,
                    )
                    writer.append(AdaptiveHopVisitBlock(dual_samples, (0, 1), visit))
                else:
                    single_pairs = np.frombuffer(raw, dtype="<i2").reshape(-1, 2)
                    single_samples = single_pairs[:, 0].astype(np.float32) + 1j * single_pairs[
                        :, 1
                    ].astype(np.float32)
                    writer.append(HostAdaptiveHopVisitBlock(single_samples[:, None], (0,), visit))
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
