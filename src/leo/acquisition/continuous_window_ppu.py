"""Negotiated PPU v5 ordered IQ source; numerical analysis remains offline."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import secrets
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from leo.acquisition.ppu_quality import signed12_ci16_quality
from leo.scanner.continuous_window import (
    ContinuousWindow,
    ContinuousWindowConfiguration,
)
from leo.scanner.short_window import (
    CounterAuthority,
    ShortWindowAcquisition,
    ValidityAuthority,
)


class PpuContinuousWindowSource:
    def __init__(
        self,
        host: str,
        *,
        expected_serial: str,
        before_start_hook: Callable[[Any], None] | None = None,
        radio_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        if not expected_serial:
            raise ValueError("continuous scanning requires an explicit radio serial")
        self.uri = host if host.startswith("ip:") else f"ip:{host}"
        self.serial = expected_serial
        self.before_start_hook = before_start_hook
        self.radio_factory = radio_factory
        self.owner: Any = None
        self.configuration: ContinuousWindowConfiguration | None = None
        self._visits: Any = None
        self._previous_end: int | None = None
        self.receipt: Any = None
        self._begin_clock: dict | None = None
        self._timing_anchor_recorded = False

    def configure_once(self, configuration: ContinuousWindowConfiguration) -> None:
        if self.owner is not None:
            raise RuntimeError("continuous source can only be prepared once")
        from pluto_plus.continuous_scan import build_continuous_setup
        from pluto_plus.continuous_scan_radio import ContinuousRadioOwner

        setup = build_continuous_setup(
            session=secrets.randbits(63) or 1,
            generation=secrets.randbits(63) or 1,
            seed=secrets.randbits(32) or 1,
            frequencies_hz=tuple(target.if_center_hz for target in configuration.targets),
            rx_mask=3 if len(configuration.receiver_ids) == 2 else 1,
            transition_budget_ms=configuration.transition_budget_ms,
            analysis_digest=hashlib.sha256(b"leo-continuous-iq-offline-glrt-v1").digest(),
        )
        def before_start(preparation):
            if self.before_start_hook is not None:
                self.before_start_hook(preparation)
            self._begin_clock = {
                "realtime_ns": time.time_ns(), "monotonic_ns": time.monotonic_ns()
            }

        self.owner = ContinuousRadioOwner.start(
            self.uri,
            self.serial,
            setup,
            gain_db=configuration.gain_db,
            before_start_hook=before_start,
            radio_factory=self.radio_factory,
        )
        self.configuration = configuration
        self._visits = iter(self.owner.visits())

    @property
    def identity(self) -> tuple[int, int]:
        if self.owner is None:
            return 0, 0
        setup = self.owner.session.setup
        return setup.session, setup.generation

    def next_window(self) -> ContinuousWindow:
        if self.configuration is None:
            raise RuntimeError("continuous source has not been configured")
        item = next(self._visits)
        delivery_clock = {"realtime_ns": time.time_ns(), "monotonic_ns": time.monotonic_ns()}
        record = item.record
        target = self.configuration.targets[record.target]
        count = len(self.configuration.receiver_ids)
        if len(item.iq) % (count * 4):
            raise ValueError("continuous source returned a partial CI16 word")
        samples = np.frombuffer(item.iq, dtype="<i2").reshape(-1, count, 2)
        if len(samples) != record.valid_end - record.valid_start:
            raise ValueError("continuous IQ count disagrees with source counter interval")
        complete = record.result.name == "COMPLETE"
        flags = () if complete else (f"provider_{record.result.name.lower()}",)
        if record.missing_samples_before:
            flags += ("provider_missing_samples",)
        if complete and (len(samples) != 50_000 or record.valid_end - record.valid_start != 50_000):
            raise ValueError("continuous COMPLETE visit does not contain exact 20 ms IQ")
        minimum_guard = (
            self.configuration.transition_budget_ms * self.configuration.sample_rate_hz // 1000
        )
        observed_guard = record.valid_start - record.transition_after
        if complete and observed_guard < minimum_guard:
            raise ValueError(
                "continuous COMPLETE visit violates minimum post-recall guard: "
                f"{observed_guard} < {minimum_guard} samples"
            )
        quality_flags, quality_receipt = signed12_ci16_quality(samples)
        flags += quality_flags
        receipt = dataclasses.asdict(record)
        receipt["host_delivery_clock"] = delivery_clock
        if not self._timing_anchor_recorded and self._begin_clock is not None:
            # This valid sample occurred after START was requested and before
            # its IQ was delivered. Do not equate delivery time with sample time.
            receipt["utc_clock_bracket"] = {
                "sample_counter": record.valid_start,
                "before": self._begin_clock,
                "after": delivery_clock,
            }
            self._timing_anchor_recorded = True
        receipt.update(quality_receipt)
        receipt.update(
            guard_policy_id="minimum-post-recall-v1",
            minimum_post_recall_guard_samples=minimum_guard,
            observed_post_recall_guard_samples=observed_guard,
            post_recall_guard_satisfied=observed_guard >= minimum_guard,
        )
        acquisition = ShortWindowAcquisition(
            samples=samples,
            requested_if_center_hz=target.if_center_hz,
            actual_if_center_hz=record.frequency_hz,
            generation=record.generation,
            sample_start=record.valid_start,
            counter_authority=CounterAuthority.HARDWARE,
            validity_authority=ValidityAuthority.PROVIDER_ATTESTED
            if complete
            else ValidityAuthority.UNKNOWN,
            host_final_sample_monotonic_ns=time.monotonic_ns(),
            quality_flags=flags,
            tune_ms=(record.transition_after - record.transition_before) * 1000 / 2_500_000,
            listen_ms=len(samples) * 1000 / 2_500_000,
            discarded_samples=record.valid_start - record.transition_before,
            retune_receipt=json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            validity_includes_guard=True,
            contiguous_with_previous=self._previous_end == record.valid_start,
        )
        self._previous_end = record.valid_end
        return ContinuousWindow(
            target,
            acquisition,
            record.session,
            record.generation,
            record.visit,
            record.visit // 8,
            record.target,
        )

    def request_stop(self, *, forced: bool = False) -> Any:
        if self.owner is None:
            return None
        return self.owner.stop(forced=forced)

    def close(self) -> Any:
        if self.owner is not None:
            self.receipt = self.owner.close()
        return self.receipt

    def abort_read(self) -> None:
        if self.owner is not None:
            self.owner.abort_read()
