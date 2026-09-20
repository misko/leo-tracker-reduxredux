"""Sealed counter/UTC projection, readable without radio or PPU dependencies.

The importer evaluates raw observations through the acquisition contract. This
record retains that evidence and its digest, the policy decision, and a single
conservative uncertainty for the complete nominal sample-clock projection.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.digests import canonical_digest
from leo.scanner.models import ScannerModel

Count = Annotated[int, Field(strict=True, ge=0)]
Positive = Annotated[int, Field(strict=True, gt=0)]


class CounterUtcTimingV4(ScannerModel):
    schema_version: Literal[4] = 4
    algorithm_version: Literal["bounded-device-counter-utc-v1"] = "bounded-device-counter-utc-v1"
    session_id: str
    session_start_device_sample_counter: Count
    final_device_sample_counter: Count
    sample_rate_hz: Literal[10_000_000, 15_000_000, 20_000_000, 30_000_000]
    first_sample_estimate_utc_ns: Positive
    display_bracket_width_ns: Count
    maximum_error_ns: Count | None
    qualification_limit_ns: Literal[100_000_000] = 100_000_000
    failure_reasons: tuple[str, ...]
    evidence: dict[str, Any]
    evidence_sha256: str

    @model_validator(mode="after")
    def _sealed_projection(self) -> Self:
        if self.final_device_sample_counter < self.session_start_device_sample_counter:
            raise ValueError("counter UTC capture interval regressed")
        if self.evidence_sha256 != canonical_digest(self.evidence):
            raise ValueError("counter UTC evidence digest mismatch")
        if (
            self.evidence.get("schema_version") != 1
            or self.evidence.get("kind") != "adaptive-counter-utc"
        ):
            raise ValueError("unsupported counter UTC evidence")
        if self.maximum_error_ns is None and not self.failure_reasons:
            raise ValueError("unknown UTC error requires an explicit failure reason")
        if self.qualified:
            policy = self.evidence.get("policy", {})
            if not policy.get("calibration_reference") or not self.evidence.get("anchors"):
                raise ValueError("qualified UTC requires calibrated raw observations")
            if policy.get("maximum_error_ns") != self.qualification_limit_ns:
                raise ValueError("UTC qualification limit differs from recorded policy")
            identity = None
            previous = None
            offsets: list[int] = []
            lower, upper = [], []
            previous_anchor = None
            ppm = policy.get("maximum_rate_error_ppm")
            delay = policy.get("maximum_acquisition_delay_ns")
            if (
                type(ppm) is not int
                or not 0 <= ppm < 1_000_000
                or type(delay) is not int
                or delay < 0
            ):
                raise ValueError("qualified UTC lacks hardware error bounds")
            if self.evidence.get("errors"):
                raise ValueError("qualified UTC contains collection errors")
            for anchor in self.evidence["anchors"]:
                observation = anchor["observation"]
                if (
                    observation["session"],
                    observation["generation"],
                    observation["sample_rate_hz"],
                ) != (self.evidence["session"], self.evidence["generation"], self.sample_rate_hz):
                    raise ValueError("counter UTC observation identity mismatch")
                current = observation["boot_id"], observation["epoch"]
                if identity is not None and identity != current:
                    raise ValueError("counter UTC epoch changed")
                identity = current
                if (policy.get("calibration_radio_serial"), policy.get("calibration_boot_id")) != (
                    self.evidence.get("radio_serial"),
                    observation["boot_id"],
                ):
                    raise ValueError("UTC calibration does not bind this radio boot")
                if previous is not None and observation["counter"] <= previous:
                    raise ValueError("counter UTC observations regressed")
                previous = observation["counter"]
                if any(
                    anchor[c]["utc_error_bound_ns"] is None for c in ("clock_before", "clock_after")
                ):
                    raise ValueError("qualified UTC lacks a host UTC bound")
                send, receive = anchor["send_monotonic_ns"], anchor["receive_monotonic_ns"]
                if receive < send or receive - send > policy["maximum_query_width_ns"]:
                    raise ValueError("UTC query interval exceeds policy")
                if previous_anchor is not None:
                    if (
                        receive - previous_anchor["send_monotonic_ns"]
                        > policy["maximum_anchor_gap_ns"]
                    ):
                        raise ValueError("UTC anchor gap exceeds policy")
                    if observation["request"] <= previous_anchor["observation"]["request"]:
                        raise ValueError("UTC request identity regressed")
                previous_anchor = anchor
                clocks = [anchor[c] for c in ("clock_before", "clock_after")]
                offsets.extend(
                    c["realtime_ns"] - (c["monotonic_before_ns"] + c["monotonic_after_ns"]) // 2
                    for c in clocks
                )
                age = observation["maximum_snapshot_age_ns"]
                if age == (1 << 64) - 1:
                    age = policy.get("maximum_snapshot_age_ns")
                if type(age) is not int or age < 0:
                    raise ValueError("qualified UTC lacks snapshot age bound")
                delta = self.session_start_device_sample_counter - observation["counter"]
                durations = [
                    Fraction(delta * 10**15, self.sample_rate_hz * (1_000_000 + s * ppm))
                    for s in (-1, 1)
                ]
                lower.append(
                    send
                    + min(
                        c["realtime_ns"] - c["monotonic_after_ns"] - c["utc_error_bound_ns"]
                        for c in clocks
                    )
                    - age
                    + min(durations).__floor__()
                    - delay
                )
                upper.append(
                    receive
                    + max(
                        c["realtime_ns"] - c["monotonic_before_ns"] + c["utc_error_bound_ns"]
                        for c in clocks
                    )
                    + max(durations).__ceil__()
                    + delay
                )
            if max(offsets) - min(offsets) > policy["maximum_clock_step_ns"]:
                raise ValueError("UTC host clock stepped")
            earliest, latest = max(lower), min(upper)
            if earliest > latest or self.first_sample_estimate_utc_ns != (earliest + latest) // 2:
                raise ValueError("UTC estimate disagrees with raw counter observations")
            span = self.final_device_sample_counter - self.session_start_device_sample_counter
            drift = Fraction(span * 10**9 * ppm, self.sample_rate_hz * (1_000_000 - ppm)).__ceil__()
            if self.maximum_error_ns != (latest - earliest + 1) // 2 + drift:
                raise ValueError("whole-capture UTC bound disagrees with raw evidence")
        return self

    @property
    def qualified(self) -> bool:
        return (
            not self.failure_reasons
            and self.maximum_error_ns is not None
            and self.maximum_error_ns <= self.qualification_limit_ns
        )

    @property
    def reason(self) -> str:
        return "; ".join(self.failure_reasons) or "whole-capture counter/UTC bound qualified"

    @property
    def first_sample_bracket_width_ns(self) -> int:
        # Unknown absolute UTC error is never turned into a numeric guarantee.
        # Legacy displays may still show the measured host transaction width.
        return (
            2 * self.maximum_error_ns
            if self.maximum_error_ns is not None
            else self.display_bracket_width_ns
        )

    @property
    def first_sample_earliest_utc_ns(self) -> int:
        return self.first_sample_estimate_utc_ns - self.first_sample_bracket_width_ns // 2

    @property
    def first_sample_latest_utc_ns(self) -> int:
        return self.first_sample_estimate_utc_ns + self.first_sample_bracket_width_ns // 2

    @property
    def maximum_realtime_monotonic_offset_spread_ns(self) -> int:
        offsets = [
            clock["realtime_ns"] - (clock["monotonic_before_ns"] + clock["monotonic_after_ns"]) // 2
            for anchor in self.evidence["anchors"]
            for clock in (anchor["clock_before"], anchor["clock_after"])
        ]
        return max(offsets) - min(offsets) if offsets else 0
