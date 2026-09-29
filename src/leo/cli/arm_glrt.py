"""Run the opt-in ARM GLRT executable against an explicit saved CI16 file."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from pathlib import Path

from leo.contracts.arm_glrt import ArmGlrtConfigurationV1, ArmGlrtInputBindingV1
from leo.contracts.digests import sha256_digest
from leo.scanner.arm_glrt import ArmGlrtExecutionFailure, validate_native_output


def _digest(path: Path) -> str:
    return sha256_digest(path.read_bytes())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-binary", type=Path, required=True)
    parser.add_argument("--input-ci16", type=Path, required=True)
    parser.add_argument("--exact-template", type=Path, required=True)
    parser.add_argument("--control-template", type=Path, required=True)
    parser.add_argument("--input-binding", type=Path, required=True)
    parser.add_argument("--rate-hz", type=int, required=True)
    parser.add_argument("--dwell-ms", type=int, choices=(120, 240, 360), default=120)
    parser.add_argument("--probe-stride-ms", type=int, choices=(10, 20, 120), default=10)
    parser.add_argument("--timeout-s", type=float, default=300.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def run(arguments: argparse.Namespace) -> dict[str, object]:
    if not math.isfinite(arguments.timeout_s) or arguments.timeout_s <= 0:
        raise ValueError("ARM GLRT timeout must be positive and finite")
    binding = ArmGlrtInputBindingV1.model_validate_json(arguments.input_binding.read_bytes())
    before = {
        "input": _digest(arguments.input_ci16),
        "binary": _digest(arguments.native_binary),
        "exact": _digest(arguments.exact_template),
        "control": _digest(arguments.control_template),
    }
    actual_input = before["input"]
    if binding.ci16_sha256 != actual_input:
        raise ValueError("CI16 input digest disagrees with the supplied input binding")
    configuration = ArmGlrtConfigurationV1(
        rate_hz=arguments.rate_hz,
        dwell_ms=arguments.dwell_ms,
        probe_stride_ms=arguments.probe_stride_ms,
    )
    command = [
        str(arguments.native_binary),
        "--rate-hz", str(configuration.rate_hz),
        "--exact-template", str(arguments.exact_template),
        "--control-template", str(arguments.control_template),
        "--input-ci16", str(arguments.input_ci16),
        "--dwell-ms", str(configuration.dwell_ms),
        "--probe-stride-ms", str(configuration.probe_stride_ms),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=arguments.timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ArmGlrtExecutionFailure(f"ARM GLRT execution failed: {error}") from error
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[:2_048]
        raise ArmGlrtExecutionFailure(
            f"ARM GLRT executable exited {completed.returncode}: {detail}"
        )
    result = validate_native_output(
        completed.stdout,
        configuration=configuration,
        input_binding=binding,
        native_binary_sha256=_digest(arguments.native_binary),
        exact_template_sha256=_digest(arguments.exact_template),
        control_template_sha256=_digest(arguments.control_template),
    )
    after = {
        "input": _digest(arguments.input_ci16),
        "binary": _digest(arguments.native_binary),
        "exact": _digest(arguments.exact_template),
        "control": _digest(arguments.control_template),
    }
    if before != after:
        raise ArmGlrtExecutionFailure("ARM GLRT executable changed a hash-bound input during run")
    if result.native_binary_sha256 != before["binary"]:
        raise ArmGlrtExecutionFailure("ARM GLRT binary identity changed during run")
    return result.model_dump(mode="json")


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.output.exists():
        raise SystemExit("ARM GLRT output already exists; refusing to overwrite it")
    try:
        result = run(arguments)
    except (OSError, ValueError, ArmGlrtExecutionFailure) as error:
        raise SystemExit(f"ARM GLRT failed; no result was produced: {error}") from error
    payload = json.dumps(result, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    temporary = arguments.output.with_name(f".{arguments.output.name}.{os.getpid()}.partial")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(descriptor, "w") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, arguments.output)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(payload, end="")
    return 0


if __name__ == "__main__":
    main()
