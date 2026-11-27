"""Adapt immutable v6 receipts into native IQ chunks and interior evidence."""

from __future__ import annotations

import dataclasses
import json
import time

import numpy as np

from leo.acquisition.ppu_quality import signed12_ci16_quality
from leo.scanner.position_scan import PositionScanConfiguration
from leo.scanner.short_window import (
    CounterAuthority,
    ShortWindowAcquisition,
    ValidityAuthority,
    classify_window,
)
from leo.scanner.short_window_recording import acquisition_metadata, json_metadata


def position_window(item, configuration: PositionScanConfiguration):
    record = item.record
    target = configuration.targets[record.target]
    if (
        record.target != record.visit % 24
        or record.sweep != record.visit // 24
        or record.profile != record.target % 8
        or record.frequency_hz != target.if_center_hz
        or len(item.iq) != (record.valid_end - record.valid_start) * 8
    ):
        raise ValueError("position provider lost logical target or native IQ geometry")
    complete = record.result.name == "COMPLETE"
    if complete and (
        record.valid_end - record.valid_start != 200_000
        or record.valid_start < max(record.selection_counter, record.transition_after) + 200_000
        or abs(record.verified_frequency_hz - target.if_center_hz) > 2
    ):
        raise ValueError("position COMPLETE window lacks verified tuning or guard")
    samples = np.frombuffer(item.iq, dtype="<i2").reshape(-1, 2, 2)
    flags, quality = signed12_ci16_quality(samples)
    if not complete:
        flags += (f"provider_{record.result.name.lower()}",)
    if record.missing_samples_before:
        flags += ("provider_missing_samples",)
    receipt = dataclasses.asdict(record)
    receipt["plan_digest"] = record.plan_digest.hex()
    receipt.update(quality)
    acquisition = ShortWindowAcquisition(
        samples=samples,
        sample_rate_hz=10_000_000,
        requested_if_center_hz=target.if_center_hz,
        actual_if_center_hz=record.verified_frequency_hz or None,
        generation=record.generation,
        sample_start=record.valid_start,
        counter_authority=CounterAuthority.HARDWARE,
        validity_authority=ValidityAuthority.PROVIDER_ATTESTED
        if complete
        else ValidityAuthority.UNKNOWN,
        quality_flags=flags,
        host_final_sample_monotonic_ns=time.monotonic_ns(),
        tune_ms=(record.transition_after - record.transition_before) / 10_000,
        listen_ms=len(samples) / 10_000,
        discarded_samples=record.valid_start - record.transition_before,
        retune_receipt=json.dumps(receipt, sort_keys=True, separators=(",", ":")),
        validity_includes_guard=True,
    )
    powers = tuple(
        json_metadata(dataclasses.asdict(power))
        for power in classify_window(acquisition, configuration.power_configuration())
    )
    metadata = acquisition_metadata(acquisition)
    metadata.update(
        device_session=record.session,
        global_visit=record.visit,
        sweep=record.sweep,
        target_index=record.target,
        physical_slot=record.profile,
        slot_generation=record.slot_generation,
        plan_digest=record.plan_digest.hex(),
        axis="XYZ"[record.target % 3],
        analysis_path="interior-position",
        policy_id=configuration.policy_id,
        relay_state="unknown",
    )
    return dict(
        sequence=record.visit,
        target_id=target.target_id,
        samples=samples,
        acquisition=metadata,
        powers=powers,
    )
