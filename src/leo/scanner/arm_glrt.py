"""Port and validation boundary for the opt-in saved-input ARM GLRT backend."""

from __future__ import annotations

import json
from typing import Protocol

from leo.contracts.arm_glrt import (
    ArmGlrtConfigurationV1,
    ArmGlrtInputBindingV1,
    ArmGlrtNativeOutputV1,
    ArmGlrtResultV1,
)
from leo.contracts.digests import sha256_digest


class ArmGlrtExecutionFailure(RuntimeError):
    """Native execution or its output failed; this is never a no-candidate result."""


class ArmGlrtExecutor(Protocol):
    def execute(self) -> bytes: ...


def validate_native_output(
    payload: bytes,
    *,
    configuration: ArmGlrtConfigurationV1,
    input_binding: ArmGlrtInputBindingV1,
    native_binary_sha256: str,
    exact_template_sha256: str,
    control_template_sha256: str,
) -> ArmGlrtResultV1:
    """Turn one complete C document into distinct ARM evidence.

    The caller supplies hash-bound inputs.  It must surface subprocess failures
    as ``ArmGlrtExecutionFailure`` and must not call this function with partial
    output.
    """
    try:
        document = json.loads(payload)
        # The C executable owns one dwell per invocation.  Candidate ranks and
        # the explicit dwell coordinate are added at this narrow port rather
        # than being implied by an older tracking product.
        for row in document["rows"]:
            if row.get("dwell_index", 0) != 0:
                raise ValueError("native ARM GLRT row names an unexpected dwell")
            row["dwell_index"] = 0
            for rank, candidate in enumerate(row["candidates"]):
                if candidate.get("candidate_rank", rank) != rank:
                    raise ValueError("native ARM GLRT candidate rank is not ordered")
                candidate["candidate_rank"] = rank
        native = ArmGlrtNativeOutputV1.model_validate(document)
    except Exception as error:
        raise ArmGlrtExecutionFailure(f"invalid native ARM GLRT output: {error}") from error
    actual = (
        native.algorithm_id,
        native.sample_rate_hz,
        native.dwell_ms,
        native.probe_ms,
        native.probe_stride_ms,
    )
    expected = (
        configuration.algorithm_id,
        configuration.rate_hz,
        configuration.dwell_ms,
        configuration.probe_ms,
        configuration.probe_stride_ms,
    )
    if actual != expected:
        raise ArmGlrtExecutionFailure("native ARM GLRT configuration identity disagrees")
    if native.receiver_count != len(input_binding.receiver_ids):
        raise ArmGlrtExecutionFailure("native ARM GLRT receiver count disagrees with input binding")
    if native.input_complex_times != configuration.rate_hz * configuration.dwell_ms // 1_000:
        raise ArmGlrtExecutionFailure("native ARM GLRT input length disagrees with configuration")
    try:
        return ArmGlrtResultV1(
            configuration=configuration,
            input_binding=input_binding,
            native_binary_sha256=native_binary_sha256,
            exact_template_sha256=exact_template_sha256,
            control_template_sha256=control_template_sha256,
            native_output_sha256=sha256_digest(payload),
            rows=native.rows,
            timings=native.timings_ms,
        )
    except Exception as error:
        raise ArmGlrtExecutionFailure(
            f"native ARM GLRT output inventory rejected: {error}"
        ) from error
