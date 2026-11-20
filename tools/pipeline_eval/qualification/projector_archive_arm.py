"""Run the standalone orbital projection kernel on full archived grids under Arm QEMU."""

import argparse
import json
import platform
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

from tools.pipeline_eval.__main__ import (
    DEFAULT_OUT,
    local_output,
    public_cases,
    references,
    save_json,
)
from tools.pipeline_eval.qualification import projector_audit
from tools.pipeline_eval.qualification.full_v5_check import BULK, PRODUCERS, _sha
from tools.pipeline_eval.qualification.projector_arm import DEFAULT_CC
from tools.pipeline_eval.variants import orbit_projector, v5_lean

HARNESS = Path(__file__).with_suffix(".c")
HEADER = struct.Struct("<8s4Q8d")
RF_HZ = 11.5e9
LIMITS = (1e-5, 1e-8, 1e-5)
FLAGS = ("-std=c11", "-O3", "-ffp-contract=off", "-fno-math-errno", "-static", "-fstack-usage")
TARGETS = {
    "x86-64": ("cc", ("-march=x86-64",), (), 62),
    "cortex-a9": (
        str(DEFAULT_CC),
        ("-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard"),
        ("qemu-arm", "-cpu", "cortex-a9"),
        40,
    ),
    "aarch64": ("aarch64-linux-gnu-gcc", ("-march=armv8-a",), ("qemu-aarch64",), 183),
}


def write_fixture(path, stencil, center):
    from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

    satellites, knots, _ = stencil.positions.shape
    groups, _, times = stencil.index.shape
    observer = geodetic_to_ecef_km(*center, 0.0)
    up = ecef_to_enu_matrix(*center)[2]
    with path.open("xb") as stream:
        stream.write(
            HEADER.pack(
                b"LEOPROJ1", satellites, knots, times, groups, stencil.step, RF_HZ, *observer, *up
            )
        )
        for array in (
            stencil.positions,
            stencil.velocities,
            stencil.index,
            stencil.fraction,
            stencil.rotation,
        ):
            dtype = "<i8" if np.issubdtype(array.dtype, np.integer) else "<f8"
            np.asarray(array, dtype=dtype, order="C").tofile(stream)
    return satellites, times


def _prepare(request_path, result_path, directory):
    from leo.analysis.research import phase_linear_geometry as reference

    original, job, bank, times = projector_audit.archived_roof_grid(request_path)
    if not Path(reference.__file__).is_relative_to(v5_lean.SOURCE):
        raise ValueError("reference projection must use the frozen original runtime")
    center = job["screen_center"]
    stencil = orbit_projector.prepare(bank, times)
    case_shape = write_fixture(directory / "stencil.bin", stencil, center)
    ref = reference.prepare_phase_geometry(bank, times)
    outputs = reference.phase_linear_frequency(ref, *center)
    with (directory / "reference.bin").open("xb") as stream:
        for array in outputs:
            np.asarray(array, dtype="<f8", order="C").tofile(stream)
    data = dict(
        shape=case_shape,
        knots=stencil.positions.shape[1],
        nominal_rf_hz=RF_HZ,
        phase_s=0.0,
        derivative_step_s=stencil.step,
        screen_center=center,
        session_id=job["identity"]["session_id"],
        native_sha256=job["native_input"]["sha256"],
        reference_sha256=_sha(Path(reference.__file__)),
        frozen_source_sha256=v5_lean.SOURCE_SHA256,
        compact_prepared_bytes=stencil.bytes,
        reference_prepared_bytes=projector_audit.nbytes(ref),
        output_bytes=sum(a.nbytes for a in outputs),
        compact_prepared_arrays=5,
        reference_prepared_arrays=8,
        output_arrays=len(outputs),
    )
    save_json(directory / "fixture.json", data)
    original.write(
        result_path, dict(status="ok", boundary="Archived reference projection", metrics={})
    )


def _build(target, directory):
    cc, tune, emulation, machine = TARGETS[target]
    executable = directory / "projector"
    subprocess.run(
        [cc, *FLAGS, *tune, HARNESS, orbit_projector.KERNEL, "-lm", "-o", executable],
        cwd=directory,
        check=True,
    )
    with executable.open("rb") as stream:
        identity = stream.read(20)
    if (
        identity[:4] != b"\x7fELF"
        or identity[5] != 1
        or int.from_bytes(identity[18:20], "little") != machine
    ):
        raise ValueError(f"{target} executable has a different object architecture")
    stack = next(directory.glob("*orbit_projector.su"))
    own = next(line for line in stack.read_text().splitlines() if "project_orbit_grid\t" in line)
    kernel_stack, stack_kind = own.split("\t")[1:]
    if stack_kind != "static":
        raise ValueError(f"{target} compiler did not report a fixed kernel stack usage")
    version = subprocess.check_output([cc, "--version"], text=True).splitlines()[0]
    environment = dict(
        flags=(*FLAGS, *tune),
        compiler=version,
        executable_sha256=_sha(executable),
        elf_machine=machine,
        kernel_stack_bytes=int(kernel_stack),
        execution="QEMU user-mode on x86-64" if emulation else "native x86-64",
    )
    if emulation:
        environment["emulator"] = subprocess.check_output(
            [emulation[0], "--version"], text=True
        ).splitlines()[0]
    return [*emulation, executable], environment


def _run(command, directory, fixture, expected):
    output = directory / "raw.bin"
    with fixture.open("rb") as stdin, output.open("xb") as stdout:
        result = subprocess.run(
            command, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE, check=True, timeout=60
        )
    memory = json.loads(result.stderr)
    if (
        memory
        != dict(
            input_array_bytes=expected["compact_prepared_bytes"],
            output_array_bytes=expected["output_bytes"],
            array_allocations=1,
        )
        or output.stat().st_size != expected["output_bytes"]
    ):
        raise ValueError("standalone projection disagrees with the sealed fixture layout")
    return output, memory


def _errors(filename, expected, shape):
    actual = np.memmap(filename, dtype="<f8", mode="r", shape=(3, *shape))
    degrees = np.rad2deg(np.arcsin(np.clip(actual[1], -1.0, 1.0)))
    return projector_audit.maximum_error(expected, (actual[0], degrees, actual[2]))


def audit(case_id, directory):
    if platform.machine() != "x86_64":
        raise ValueError("this qualification requires the native x86-64 control")
    panel, refs = references("smoke", [case_id])
    (case,) = public_cases(panel, refs, DEFAULT_OUT / "inputs")
    directory.mkdir(parents=True, exist_ok=False)
    prepared = v5_lean.run_bound_worker(
        case, directory / "prepare", Path(__file__), worker_args=(str(directory),)
    )
    if prepared["status"] != "ok":
        raise ValueError(prepared["reason"])
    expected = json.loads((directory / "fixture.json").read_bytes())
    fixture = directory / "stencil.bin"
    reference = directory / "reference.bin"
    if fixture.stat().st_size != HEADER.size + expected["compact_prepared_bytes"]:
        raise ValueError("fixture size differs from the archived stencil arrays")
    ref = np.memmap(reference, dtype="<f8", mode="r", shape=(3, *expected["shape"]))
    metrics = {}
    for target in TARGETS:
        folder = directory / target
        folder.mkdir()
        command, environment = _build(target, folder)
        output, memory = _run(command, folder, fixture, expected)
        errors = _errors(output, ref, expected["shape"])
        digest = _sha(output)
        identical = target == "x86-64" or digest == metrics["x86-64"]["raw_sha256"]
        metrics[target] = dict(
            environment,
            **memory,
            raw_sha256=digest,
            byte_equal_to_x86_c=identical,
            maximum_absolute_error=errors,
        )
        print(case_id, target, identical, errors, flush=True)
    return dict(
        case=case_id,
        **expected,
        fixture_sha256=_sha(fixture),
        reference_output_sha256=_sha(reference),
        harness_sha256=_sha(HARNESS),
        kernel_sha256=_sha(orbit_projector.KERNEL),
        maximum_absolute_error_limits=LIMITS,
        targets=metrics,
        passed=all(
            row["byte_equal_to_x86_c"]
            and all(
                error <= limit
                for error, limit in zip(row["maximum_absolute_error"], LIMITS, strict=True)
            )
            for row in metrics.values()
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(PRODUCERS), required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    directory = local_output(args.work)
    if directory.is_relative_to(BULK / "leo"):
        parser.error("choose an output outside the recording archive")
    result = audit(args.case, directory)
    save_json(args.out, result)
    if not result["passed"]:
        parser.error("portable projection failed the numerical agreement gate")


if __name__ == "__main__":
    if len(sys.argv) == 4 and not sys.argv[1].startswith("--"):
        _prepare(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
    else:
        main()
