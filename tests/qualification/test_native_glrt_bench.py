from __future__ import annotations

import array
import cmath
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from leo.qualification.arm_glrt_release import BENCHMARK, CLI, build

ROOT = Path(__file__).resolve().parents[2]


def _fftw_prefix(tmp_path: Path, compiler: Path) -> Path:
    configured = os.environ.get("LEO_FFTW_PREFIX")
    if configured:
        return Path(configured)
    prefix = tmp_path / "fftw"
    (prefix / "include").mkdir(parents=True)
    (prefix / "lib").mkdir()
    header = Path("/usr/include/fftw3.h")
    archive = Path(
        subprocess.run(
            [os.fspath(compiler), "-print-file-name=libfftw3f.a"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
    )
    assert header.is_file() and archive.is_file(), "host FFTW development files required"
    (prefix / "include/fftw3.h").symlink_to(header)
    (prefix / "lib/libfftw3f.a").symlink_to(archive)
    return prefix


def _template(path: Path, count: int, phase: float) -> None:
    values = array.array("d")
    for index in range(count):
        value = cmath.exp(1j * (phase + 0.013 * index + 0.0000007 * index * index))
        values.extend((value.real, value.imag))
    path.write_bytes(values.tobytes())


@pytest.mark.fftw
@pytest.mark.parametrize(
    ("full_prep", "disable_fine_plan_reuse"),
    ((False, False), (False, True), (True, False)),
)
def test_benchmark_reuses_context_and_matches_saved_input_cli(
    tmp_path: Path, full_prep: bool, disable_fine_plan_reuse: bool
) -> None:
    compiler_name, archiver_name = shutil.which("gcc"), shutil.which("gcc-ar")
    assert compiler_name and archiver_name, "gcc and gcc-ar are required"
    compiler, archiver = Path(compiler_name), Path(archiver_name)
    output = tmp_path / "build"
    build(
        source_root=ROOT / "src/leo/analysis/native_glrt",
        output_dir=output,
        work_dir=tmp_path / "work",
        compiler=compiler,
        archiver=archiver,
        fftw_prefix=_fftw_prefix(tmp_path, compiler),
        target="host",
        with_benchmark=True,
        full_prep=full_prep,
        disable_fine_plan_reuse=disable_fine_plan_reuse,
        diagnostic_wrap=True,
    )
    rate, dwell, stride = 2_500_000, 120, 120
    exact, control, samples = tmp_path / "exact", tmp_path / "control", tmp_path / "ci16"
    _template(exact, (rate + 375) // 750, 0.2)
    _template(control, (rate + 375) // 750, 1.1)
    values = array.array("h")
    frame = (rate + 375) // 750
    for index in range(rate * dwell // 1000):
        template_index = index % frame
        value = cmath.exp(
            1j * (0.2 + 0.013 * template_index + 0.0000007 * template_index**2)
        )
        iq = (round(20000 * value.real), round(20000 * value.imag))
        values.extend((*iq, *iq))
    samples.write_bytes(values.tobytes())
    manifest = tmp_path / "manifest.tsv"
    manifest.write_text(
        "".join(
            f"{sequence}\t{rate}\t{dwell}\t{stride}\t{exact}\t{control}\t{samples}\n"
            for sequence in range(2)
        )
    )
    thermal = tmp_path / "thermal"
    thermal.write_text("2790\n")
    completed = subprocess.run(
        [os.fspath(output / BENCHMARK), "--manifest", os.fspath(manifest),
         "--thermal-path", os.fspath(thermal), "--thermal-offset", "-2219",
         "--thermal-scale", "123.040771484"],
        text=True,
        capture_output=True,
        check=True,
    )
    documents = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [document.get("kind") or document["result"]["kind"] for document in documents] == [
        "setup", "call", "call", "summary"
    ]
    calls = [document["result"] for document in documents[1:3]]
    assert documents[0]["unique_inputs"] == 1
    assert documents[0]["preloaded_bytes"] == samples.stat().st_size
    assert documents[0]["thermal_path"] == os.fspath(thermal)
    assert documents[0]["thermal_scale"] == pytest.approx(123.040771484)
    assert [call["sequence"] for call in calls] == [0, 1]
    expected_prepared = rate * dwell // 1000 if full_prep else rate // 50
    assert all(call["profile"]["prepared_complex_times"] == expected_prepared for call in calls)
    assert all(len(call["rows"]) == 2 for call in calls)
    assert all(document["result"]["thermal_available_before"] for document in documents[1:3])
    assert all(document["result"]["thermal_millidegrees_before"] == 70256
               for document in documents[1:3])
    diagnostics = [call["diagnostic_inclusive_with_wrapper_overhead"] for call in calls]
    assert all(item is not None for item in diagnostics)
    if not full_prep:
        expected_plans = 2 if disable_fine_plan_reuse else 0
        assert all(item["fftf_plan_calls"] == expected_plans for item in diagnostics)
    native = subprocess.run(
        [os.fspath(output / CLI), "--rate-hz", str(rate), "--dwell-ms", str(dwell),
         "--probe-stride-ms", str(stride), "--exact-template", os.fspath(exact),
         "--control-template", os.fspath(control), "--input-ci16", os.fspath(samples)],
        text=True,
        capture_output=True,
        check=True,
    )
    native_rows = json.loads(native.stdout)["rows"]
    for bench_row, native_row in zip(calls[0]["rows"], native_rows, strict=True):
        assert bench_row["candidates"] == native_row["candidates"]

    unprofiled = subprocess.run(
        [os.fspath(output / BENCHMARK), "--manifest", os.fspath(manifest), "--no-profile"],
        text=True,
        capture_output=True,
        check=True,
    )
    unprofiled_documents = [json.loads(line) for line in unprofiled.stdout.splitlines()]
    assert unprofiled_documents[0]["profile_enabled"] is False
    assert all(document["result"]["profile_enabled"] is False
               for document in unprofiled_documents[1:3])
