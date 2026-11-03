from __future__ import annotations

import ctypes
import json
import math
import os
import subprocess
import tarfile
from array import array
from pathlib import Path

import pytest

from tools.native_adaptive_ds9_export import (
    _one_to_one_candidate_matches,
    compare_deployed_wrapper_strict,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "native/adaptive/detector"
ARCHIVE = ROOT / "reports/2026_09_30_arm_ds9_native_comparison/local/inputs.tar"
RAW = "607957d70258c2ae53439f9b149821eea15ee95d1863ee5bb845412a2cc3fdc8.ci16"
FALLBACK_RAW = "d302949a8ce74cc8ef27d24acffe89266847a34c9795e895d086c7fd703443fd.ci16"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("native-detector")
    prefix = root / "fftw"
    (prefix / "include").mkdir(parents=True)
    (prefix / "lib").mkdir()
    (prefix / "include/fftw3.h").symlink_to("/usr/include/fftw3.h")
    (prefix / "lib/libfftw3f.a").symlink_to("/usr/lib/x86_64-linux-gnu/libfftw3f.a")
    output = root / "output"
    subprocess.run(
        [
            "python3",
            os.fspath(SOURCE / "build.py"),
            "--output-dir",
            os.fspath(output),
            "--work-dir",
            os.fspath(root / "work"),
            "--compiler",
            "/usr/bin/gcc",
            "--archiver",
            "/usr/bin/gcc-ar",
            "--fftw-prefix",
            os.fspath(prefix),
            "--target",
            "host",
        ],
        check=True,
    )
    fixture = root / "fixture"
    fixture.mkdir()
    with tarfile.open(ARCHIVE) as archive:
        for member in ("lower-exact.c128", "lower-control.c128", RAW, FALLBACK_RAW):
            archive.extract(member, fixture, filter="data")
    return output, fixture


@pytest.fixture(scope="module")
def research_built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("native-detector-research")
    prefix = root / "fftw"
    (prefix / "include").mkdir(parents=True)
    (prefix / "lib").mkdir()
    (prefix / "include/fftw3.h").symlink_to("/usr/include/fftw3.h")
    (prefix / "lib/libfftw3f.a").symlink_to("/usr/lib/x86_64-linux-gnu/libfftw3f.a")
    output = root / "output"
    subprocess.run(
        [
            "python3",
            os.fspath(SOURCE / "build.py"),
            "--output-dir",
            os.fspath(output),
            "--work-dir",
            os.fspath(root / "work"),
            "--compiler",
            "/usr/bin/gcc",
            "--archiver",
            "/usr/bin/gcc-ar",
            "--fftw-prefix",
            os.fspath(prefix),
            "--target",
            "host",
            "--enable-server-reference",
        ],
        check=True,
    )
    fixture = root / "fixture"
    fixture.mkdir()
    with tarfile.open(ARCHIVE) as archive:
        for member in ("lower-exact.c128", "lower-control.c128", RAW, FALLBACK_RAW):
            archive.extract(member, fixture, filter="data")
    return output, fixture


def command(output: Path, fixture: Path) -> list[str]:
    return [
        os.fspath(output / "leo-native-adaptive-detector"),
        "--rate-hz",
        "2500000",
        "--exact-template",
        os.fspath(fixture / "lower-exact.c128"),
        "--control-template",
        os.fspath(fixture / "lower-control.c128"),
        "--input-ci16",
        os.fspath(fixture / RAW),
        "--dwell-ms",
        "120",
        "--probe-stride-ms",
        "120",
    ]


def ordinary_projection(document: dict[str, object]) -> list[dict[str, object]]:
    projected = json.loads(json.dumps(document["rows"]))
    for row in projected:
        row.pop("timings_ms")
        for candidate in row["candidates"]:
            candidate.pop("fractional_epoch")
    return projected


def test_fractional_epoch_is_additive_and_never_fabricated(
    built: tuple[Path, Path],
) -> None:
    output, fixture = built
    ordinary = json.loads(
        subprocess.run(command(output, fixture), check=True, text=True, capture_output=True).stdout
    )
    fractional = json.loads(
        subprocess.run(
            [*command(output, fixture), "--fractional-epoch"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    )

    assert len(ordinary["rows"]) == len(fractional["rows"]) == 2
    assert ordinary_projection(ordinary) == ordinary_projection(fractional)
    ordinary_candidates = [candidate for row in ordinary["rows"] for candidate in row["candidates"]]
    candidates = [candidate for row in fractional["rows"] for candidate in row["candidates"]]
    assert len(candidates) == len(ordinary_candidates) == 6
    assert all(
        candidate["fractional_epoch"]["status"] == "not_evaluated"
        for candidate in ordinary_candidates
    )
    assert all(
        candidate["fractional_epoch"]["offset_samples"] is None for candidate in ordinary_candidates
    )
    assert all(candidate["fractional_epoch"]["status"] == "complete" for candidate in candidates)
    for candidate in candidates:
        result = candidate["fractional_epoch"]
        assert len(result["exact_score_grid"]) == len(result["control_score_grid"]) == 5
        assert -2.0 <= result["offset_samples"] <= 2.0
        assert result["margin"] == pytest.approx(result["exact_score"] - result["control_score"])
        assert result["tracking_cfo_hz"] == pytest.approx(
            candidate["acquired_cfo_hz"] + result["residual_cfo_hz"]
        )


def test_persistent_replay_reuses_one_context_and_carries_metadata(
    built: tuple[Path, Path], tmp_path: Path
) -> None:
    output, fixture = built
    fields = [
        "2500000",
        "120",
        "120",
        os.fspath(fixture / "lower-exact.c128"),
        os.fspath(fixture / "lower-control.c128"),
        os.fspath(fixture / RAW),
        '{"dataset_id":"DS9"}',
    ]
    schedule = tmp_path / "schedule.tsv"
    schedule.write_text("\n".join("\t".join([str(index), *fields]) for index in range(2)) + "\n")
    process = subprocess.run(
        [
            os.fspath(output / "leo-native-adaptive-replay"),
            "--manifest",
            os.fspath(schedule),
            "--thermal-path",
            "/nonexistent",
            "--fractional-epoch",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    lines = [json.loads(line) for line in process.stdout.splitlines()]

    assert lines[0]["kind"] == "setup"
    assert lines[0]["entries"] == 2
    assert lines[0]["unique_inputs"] == 1
    assert lines[0]["fractional_epoch_enabled"] is True
    calls = [line["result"] for line in lines if line.get("result", {}).get("kind") == "call"]
    assert [call["sequence"] for call in calls] == [0, 1]
    assert all(call["metadata"] == '{"dataset_id":"DS9"}' for call in calls)
    assert lines[-1]["kind"] == "summary"
    assert lines[-1]["destroy_status"] == 0


def test_server_coverage_mode_retains_all_native_hypotheses(
    research_built: tuple[Path, Path],
) -> None:
    output, fixture = research_built
    document = json.loads(
        subprocess.run(
            [*command(output, fixture), "--server-coverage-fractional"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    )

    assert document["refinement_mode"] == "server-coverage-fractional"
    assert all(
        row["candidate_count"] == row["retained_peak_count"] == 8 for row in document["rows"]
    )
    candidates = [candidate for row in document["rows"] for candidate in row["candidates"]]
    assert len(candidates) == 16
    assert all(
        candidate["fractional_epoch"]["status"] in {"complete", "unbracketed"}
        for candidate in candidates
    )


def test_server_reference_mode_matches_symbolwise_reference_inventory(
    research_built: tuple[Path, Path],
) -> None:
    output, fixture = research_built
    document = json.loads(
        subprocess.run(
            [*command(output, fixture), "--server-reference-fractional"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    )

    assert document["refinement_mode"] == "server-reference-fractional"
    assert [row["proposal_executed"] for row in document["rows"]] == [0, 0]
    assert [row["candidate_count"] for row in document["rows"]] == [8, 8]
    # Frozen from the maintained acquire_symbolwise function with the default
    # zero-center calibration; these assert selection and final CFO, not GLRT.
    first = document["rows"][0]["candidates"][:3]
    assert [candidate["epoch"] for candidate in first] == [558, 2715, 2745]
    assert [candidate["acquired_cfo_hz"] for candidate in first] == pytest.approx(
        [-316369.88457639597, -159668.3007374858, -144595.4147571697]
    )


def test_deployed_server_wrapper_applies_geometry_retention_and_peer_fallback(
    research_built: tuple[Path, Path],
) -> None:
    output, fixture = research_built
    wrapper = [
        "--deployed-server-wrapper-fractional",
        "--receiver-0-center-hz",
        "2",
        "--receiver-1-center-hz",
        "2",
        "--residual-cfo-min-hz",
        "-429685.5",
        "--residual-cfo-max-hz",
        "429685.5",
    ]
    missing_geometry = subprocess.run(
        [*command(output, fixture), "--deployed-server-wrapper-fractional"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert missing_geometry.returncode == 2

    invocation = command(output, fixture)
    invocation[invocation.index(os.fspath(fixture / RAW))] = os.fspath(fixture / FALLBACK_RAW)
    document = json.loads(
        subprocess.run([*invocation, *wrapper], check=True, text=True, capture_output=True).stdout
    )

    assert document["refinement_mode"] == "deployed-server-wrapper-fractional"
    assert [row["candidate_count"] for row in document["rows"]] == [8, 8]
    assert [row["proposal_tracking_fallback"] for row in document["rows"]] == [0, 1]
    passing = [
        sum(
            candidate["fractional_epoch"]["status"] == "complete"
            and candidate["fractional_epoch"]["margin"] >= 0.025
            for candidate in row["candidates"]
        )
        for row in document["rows"]
    ]
    assert passing == [2, 0]

    schedule = fixture / "wrapper.tsv"
    schedule.write_text(
        "\t".join(
            (
                "0",
                "2500000",
                "120",
                "120",
                os.fspath(fixture / "lower-exact.c128"),
                os.fspath(fixture / "lower-control.c128"),
                os.fspath(fixture / FALLBACK_RAW),
                "2",
                "2",
                "-429685.5",
                "429685.5",
                '{"dataset_id":"DS9"}',
            )
        )
        + "\n"
    )
    replay = subprocess.run(
        [
            os.fspath(output / "leo-native-adaptive-replay"),
            "--manifest",
            os.fspath(schedule),
            "--thermal-path",
            "/nonexistent",
            "--deployed-server-wrapper-fractional",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    lines = [json.loads(line) for line in replay.stdout.splitlines()]
    assert lines[0]["deployed_server_wrapper_mode"] is True
    replay_call = next(line["result"] for line in lines if "result" in line)
    assert [row["proposal_tracking_fallback"] for row in replay_call["rows"]] == [0, 1]


def test_interval_dot_certificate_covers_adversarial_inputs(
    research_built: tuple[Path, Path],
) -> None:
    output, _ = research_built
    library = ctypes.CDLL(os.fspath(output / "libleo-adaptive-detector.so"))
    probe = library.leo_full_search_interval_dot_probe
    probe.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
    ]
    probe.restype = ctypes.c_int

    cases = (
        ([0.0] * 22, [1.0] * 11, [0.0] * 11),
        (
            [(-1.0) ** index for index in range(22)],
            [(-1.0) ** index for index in range(11)],
            [(-1.0) ** (index + 1) for index in range(11)],
        ),
        ([2.0**-149] * 22, [1.0] * 11, [0.5] * 11),
    )
    for sample_values, real_values, imaginary_values in cases:
        samples = (ctypes.c_float * 22)(*sample_values)
        real = (ctypes.c_double * 11)(*real_values)
        imaginary = (ctypes.c_double * 11)(*imaginary_values)
        approximate = ctypes.c_double()
        exact = ctypes.c_double()
        bound = ctypes.c_double()
        assert (
            probe(
                samples,
                real,
                imaginary,
                11,
                ctypes.byref(approximate),
                ctypes.byref(exact),
                ctypes.byref(bound),
            )
            == 0
        )
        assert abs(approximate.value - exact.value) <= bound.value

    huge = (ctypes.c_double * 11)(*[1e308] * 11)
    finite_samples = (ctypes.c_float * 22)(*[0.5] * 22)
    output_values = [ctypes.c_double() for _ in range(3)]
    assert (
        probe(
            finite_samples,
            huge,
            huge,
            11,
            *(ctypes.byref(value) for value in output_values),
        )
        == -1
    )


def test_interval_frontier_certificate_preserves_ties_and_separation_chains(
    research_built: tuple[Path, Path],
) -> None:
    output, _ = research_built
    library = ctypes.CDLL(os.fspath(output / "libleo-adaptive-detector.so"))

    class Peak(ctypes.Structure):
        _fields_ = [
            ("score", ctypes.c_double),
            ("epoch", ctypes.c_int32),
            ("coarse_bin", ctypes.c_int32),
        ]

    probe = library.leo_full_search_interval_certificate_probe
    probe.argtypes = [
        ctypes.POINTER(Peak),
        ctypes.c_size_t,
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_double),
    ]
    probe.restype = ctypes.c_int
    frequencies = (ctypes.c_double * 11)(*[float(offset * 80_000) for offset in range(-5, 6)])
    # The +/-80 kHz equal-score cells arrive in deliberately non-scan order,
    # as unequal interval upper bounds can cause in the real frontier.  Both
    # are suppressed by the stronger epoch-zero peak.  Epochs spaced exactly
    # 20 samples form the eight retained basins; the epoch-ten cells exercise
    # the strict (<20) separation chain at its interior.
    values = [
        Peak(99.5, 10, 6),
        Peak(99.5, 10, 4),
        Peak(100.0, 0, 5),
        *[Peak(99.0 - index, 20 * (index + 1), 5) for index in range(7)],
    ]

    def certified(order: list[Peak], remaining_upper: float) -> tuple[int, float]:
        peaks = (Peak * len(order))(*order)
        eighth = ctypes.c_double()
        result = probe(
            peaks,
            len(order),
            200,
            frequencies,
            remaining_upper,
            ctypes.byref(eighth),
        )
        return result, eighth.value

    result, eighth = certified(values, math.nextafter(93.0, -math.inf))
    assert (result, eighth) == (1, 93.0)
    assert certified(values, 93.0) == (0, 93.0)  # An exact tie remains live.
    assert certified(list(reversed(values)), math.nextafter(93.0, -math.inf)) == (
        1,
        93.0,
    )


def test_interval_wrapper_repairs_exact_scientific_rows(
    research_built: tuple[Path, Path],
) -> None:
    output, fixture = research_built
    geometry = [
        "--receiver-0-center-hz",
        "2",
        "--receiver-1-center-hz",
        "2",
        "--residual-cfo-min-hz",
        "-429685.5",
        "--residual-cfo-max-hz",
        "429685.5",
    ]
    scalar = json.loads(
        subprocess.run(
            [
                *command(output, fixture),
                "--deployed-server-wrapper-fractional",
                *geometry,
            ],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    )
    interval = json.loads(
        subprocess.run(
            [
                *command(output, fixture),
                "--deployed-server-interval-fractional",
                *geometry,
            ],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    )
    for row in interval["rows"]:
        assert row["interval_screened_cells"] == 39_996
        assert 0 < row["interval_possible_peaks"] <= 39_996
        assert 0 < row["interval_repaired_cells"] <= 39_996
        assert row["interval_scalar_fallbacks"] == 0
    for row in [*scalar["rows"], *interval["rows"]]:
        row.pop("timings_ms")
        for field in (
            "interval_screened_cells",
            "interval_possible_peaks",
            "interval_repaired_cells",
            "interval_scalar_fallbacks",
        ):
            row.pop(field)
    assert interval["rows"] == scalar["rows"]


def test_research_create_rejects_non_nearest_rounding(
    research_built: tuple[Path, Path], tmp_path: Path
) -> None:
    output, _ = research_built
    source = tmp_path / "rounding.c"
    source.write_text(
        """
#include <fenv.h>
#include <stdlib.h>
#include "native_glrt_research.h"
int main(void) {
    size_t n=(2500000u+375u)/750u;
    leo_native_glrt_complex *a=calloc(n,sizeof(*a));
    leo_native_glrt *context=NULL;
    if(!a || fesetround(FE_DOWNWARD)) return 3;
    int status=leo_native_glrt_create_with_mode(&context,2500000u,a,a,n,
        LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_INTERVAL_FRACTIONAL);
    free(a);
    return status==LEO_NATIVE_GLRT_INVALID ? 0 : 4;
}
"""
    )
    executable = tmp_path / "rounding"
    (output / "libleo-adaptive-detector.so.1").symlink_to(output / "libleo-adaptive-detector.so")
    subprocess.run(
        [
            "/usr/bin/gcc",
            "-std=c11",
            os.fspath(source),
            f"-I{SOURCE}",
            f"-L{output}",
            "-Wl,-rpath," + os.fspath(output),
            "-lleo-adaptive-detector",
            "-lm",
            "-o",
            os.fspath(executable),
        ],
        check=True,
    )
    subprocess.run([os.fspath(executable)], check=True)


def test_interval_plateau_and_tiny_template_fallback(
    research_built: tuple[Path, Path], tmp_path: Path
) -> None:
    output, fixture = research_built
    zero_raw = tmp_path / "zero.ci16"
    zero_raw.write_bytes(array("h", [0]) * 1_200_000)
    base = command(output, fixture)
    base[base.index(os.fspath(fixture / RAW))] = os.fspath(zero_raw)
    geometry = [
        "--receiver-0-center-hz",
        "2",
        "--receiver-1-center-hz",
        "2",
        "--residual-cfo-min-hz",
        "-429685.5",
        "--residual-cfo-max-hz",
        "429685.5",
    ]
    plateau = json.loads(
        subprocess.run(
            [*base, "--deployed-server-interval-fractional", *geometry],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    )
    for row in plateau["rows"]:
        assert row["candidate_count"] == 0
        assert row["interval_possible_peaks"] > row["interval_repaired_cells"] > 0
        assert row["interval_scalar_fallbacks"] == 1

    tiny_template = tmp_path / "tiny.c128"
    tiny_template.write_bytes(array("d", [2.0**-1022, 0.0]) * 3_333)
    tiny = [
        tiny_template
        if value in {fixture / "lower-exact.c128", fixture / "lower-control.c128"}
        else value
        for value in map(Path, base)
    ]
    tiny_document = json.loads(
        subprocess.run(
            [
                *map(os.fspath, tiny),
                "--deployed-server-interval-fractional",
                *geometry,
            ],
            check=True,
            text=True,
            capture_output=True,
        ).stdout
    )
    assert [row["interval_scalar_fallbacks"] for row in tiny_document["rows"]] == [
        1,
        1,
    ]


def test_build_receipt_exposes_truthful_capabilities(built: tuple[Path, Path]) -> None:
    output, _ = built
    receipt = json.loads((output / "build-receipt.json").read_text())

    assert receipt["thread_safety"] == "independent-context-execution-lifecycle-serialized"
    assert receipt["fractional_epoch_mode_available"] is True
    assert receipt["server_coverage_fractional_mode_available"] is False
    assert receipt["server_reference_fractional_mode_available"] is False
    assert receipt["deployed_server_wrapper_fractional_mode_available"] is False
    assert receipt["deployed_server_interval_fractional_mode_available"] is False
    assert receipt["fractional_epoch_server_parity_qualified"] is False
    assert set(receipt["outputs"]) == {
        "libleo-adaptive-detector.a",
        "libleo-adaptive-detector.so",
        "leo-native-adaptive-detector",
        "leo-native-adaptive-replay",
    }


def test_research_build_receipt_exposes_research_modes(
    research_built: tuple[Path, Path],
) -> None:
    output, _ = research_built
    receipt = json.loads((output / "build-receipt.json").read_text())
    assert receipt["thread_safety"] == "process-serialized-busy-on-contention"
    assert receipt["server_coverage_fractional_mode_available"] is True
    assert receipt["server_reference_fractional_mode_available"] is True
    assert receipt["deployed_server_wrapper_fractional_mode_available"] is True
    assert receipt["deployed_server_interval_fractional_mode_available"] is True


def test_independent_contexts_execute_concurrently_without_cross_contamination(
    built: tuple[Path, Path], tmp_path: Path
) -> None:
    output, fixture = built
    executable = tmp_path / "test-context-concurrency"
    subprocess.run(
        [
            "/usr/bin/gcc",
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pthread",
            f"-I{SOURCE}",
            os.fspath(Path(__file__).with_name("test_context_concurrency.c")),
            os.fspath(output / "libleo-adaptive-detector.a"),
            "-lfftw3f",
            "-lfftw3",
            "-lm",
            "-o",
            os.fspath(executable),
        ],
        check=True,
    )
    subprocess.run(
        [
            os.fspath(executable),
            os.fspath(fixture / "lower-exact.c128"),
            os.fspath(fixture / "lower-control.c128"),
            os.fspath(fixture / RAW),
            os.fspath(fixture / FALLBACK_RAW),
        ],
        check=True,
        timeout=30,
    )


def test_concurrent_build_rejects_analyze_time_fft_planning() -> None:
    result = subprocess.run(
        [
            "/usr/bin/gcc",
            "-E",
            "-DLEO_NATIVE_GLRT_DISABLE_FINE_PLAN_REUSE=1",
            f"-I{SOURCE}",
            f"-I{SOURCE / 'kernel'}",
            f"-I{SOURCE / 'kernel/private'}",
            os.fspath(SOURCE / "native_glrt.c"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "concurrent production contexts require eager fine FFT plan reuse" in result.stderr


def test_server_comparator_never_reuses_a_candidate() -> None:
    native = [
        {
            "epoch": 10,
            "acquired_cfo_hz": 100.0,
            "fractional_epoch": {"status": "complete"},
        },
        {
            "epoch": 11,
            "acquired_cfo_hz": 101.0,
            "fractional_epoch": {"status": "complete"},
        },
    ]
    server = [
        {"integer_epoch_sample": 10, "acquired_cfo_hz": 100.0, "candidate_rank": 0},
        {"integer_epoch_sample": 11, "acquired_cfo_hz": 101.0, "candidate_rank": 1},
    ]

    matches = _one_to_one_candidate_matches(native, server, 100)

    assert matches == [(0, 0), (1, 1)]
    assert len({native_index for native_index, _ in matches}) == len(matches)
    assert len({server_index for _, server_index in matches}) == len(matches)


def test_deployed_wrapper_panel_has_strict_rank_and_availability_parity() -> None:
    report = ROOT / "reports/2026_09_30_native_adaptive_deployment/ds9"
    comparison = compare_deployed_wrapper_strict(
        sorted(report.glob("deployed-wrapper-*.jsonl")),
        report / "deployed-fractional-oracle.json",
    )

    assert comparison["saved_panel_scientific_parity_passed"] is True
    assert comparison["production_capability_parity_qualified"] is False
    assert comparison["counts"] == {
        "probe_rows": 160,
        "candidate_ranks": 1280,
        "complete_ranks": 880,
        "unavailable_ranks": 400,
        "server_gate_ranks": 295,
        "native_gate_ranks": 295,
        "peer_fallback_rows": 32,
        "missing_ranks": 0,
        "additional_ranks": 0,
        "availability_mismatches": 0,
        "epoch_mismatches": 0,
        "gate_mismatches": 0,
        "numerical_tolerance_mismatches": 0,
        "tolerance_match_off_diagonal_pairs": 38,
    }


def test_saved_server_comparisons_have_one_to_one_detail_rows() -> None:
    report = ROOT / "reports/2026_09_30_native_adaptive_deployment/ds9"
    for name in ("fractional-server-comparison.json", "server-coverage-comparison.json"):
        document = json.loads((report / name).read_text())
        cohorts = document.get("cohorts", [document])
        for cohort in cohorts:
            summary = cohort["summary"]
            assert summary["one_to_one_invariants_verified"] is True
            assert (
                summary["matched_server_gate_candidate_count"]
                <= summary["server_gate_candidate_count"]
            )
            assert (
                summary["matched_native_gate_candidate_count"]
                <= summary["native_gate_candidate_count"]
            )
            for row in cohort["rows"]:
                native_indexes = [item["native_candidate_index"] for item in row["matches"]]
                server_ranks = [item["server_candidate_rank"] for item in row["matches"]]
                assert len(native_indexes) == len(set(native_indexes))
                assert len(server_ranks) == len(set(server_ranks))
