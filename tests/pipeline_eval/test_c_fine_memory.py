import ctypes
import os
import random
import subprocess

import pytest

from tools.pipeline_eval.qualification import c_fine_memory_build as build
from tools.pipeline_eval.qualification import c_fine_memory_trial as trial


@pytest.fixture(scope="module")
def replay(tmp_path_factory):
    work = tmp_path_factory.mktemp("compact-verifier")
    trial.stage_fixtures(work)
    trial.guard_fixtures(work)
    return work


@pytest.fixture(scope="module")
def stage_builds(replay):
    return [build.build(replay, "x86", arm, "stage")[0] for arm in trial.ARMS]


def packet(binary, fixture):
    result = subprocess.run([binary, fixture], check=True, capture_output=True, timeout=30)
    return list(trial.RESULT.iter_unpack(result.stdout))


def test_tied_negatives_nyquist_and_short_final_frame(replay, stage_builds):
    rows = [packet(path, replay / "guard-stage.bin") for path in stage_builds]
    info = trial.errors(*rows)
    counts = info["counts"]
    assert counts["candidates"] == 15
    for key in ("fine_guard", "conditioned_tie", "equivalent_tie", "short_conditioned_frames"):
        assert counts[key] > 0
    assert counts["fractional_pass"] == 0
    assert info["max_absolute_errors"]["fine_hz"] == 0


def test_recorded_gate_adjacent_candidates(replay, stage_builds):
    rows = [packet(path, replay / "DS26-0237-stage.bin") for path in stage_builds]
    info = trial.errors(*rows)
    assert info["counts"]["candidates"] == 32
    assert 0 < info["closest_fractional_margin"]["pass"] - 0.025 < 3e-6
    assert 0 < 0.025 - info["closest_fractional_margin"]["fail"] < 1e-4


def test_fine_radix_prefix_boundary_matches_stock(stage_builds):
    rng = random.Random(11951)
    pilot = (ctypes.c_double * (2 * 6600))(*(rng.uniform(-1e5, 1e5) for _ in range(2 * 6600)))
    bins_to_check = (2, 31, 32, 33, 159, 160, 161, 319, 320, 321)
    outputs = []
    for binary in stage_builds:
        parent = binary.parent
        shared = parent / "fft-test.so"
        subprocess.run(
            [
                "cc",
                "-O3",
                "-march=x86-64-v3",
                "-ffp-contract=off",
                "-fopenmp-simd",
                "-shared",
                "-fPIC",
                parent / build.VARIANTS / "fine_search.c",
                "-lm",
                "-o",
                shared,
            ],
            check=True,
            env=os.environ | {"TMPDIR": str(parent)},
            timeout=30,
        )
        library = ctypes.CDLL(str(shared))
        pointer = ctypes.POINTER(ctypes.c_double)
        library.fine_search_twiddles.argtypes = [pointer]
        library.fine_search_twiddles.restype = None
        library.fine_search_transform.argtypes = [pointer] * 4 + [ctypes.c_int] * 2
        library.fine_search_transform.restype = None
        roots = (ctypes.c_double * (2 * 20000))()
        scratch = (ctypes.c_double * (2 * 2 * 20000))()
        library.fine_search_twiddles(roots)
        projected = []
        for bins in bins_to_check:
            row = (ctypes.c_double * (2 * bins))()
            library.fine_search_transform(pilot, roots, scratch, row, 1, bins)
            projected.append(bytes(row))
        outputs.append(projected)
    assert outputs[0] == outputs[1]


def test_full_detector_present_and_truncated_input(replay):
    previous = None
    for arm in trial.ARMS:
        binary, _ = build.build(replay, "x86", arm, "full")
        run = subprocess.run(
            [binary, replay / "guard-full.bin"], check=True, capture_output=True, timeout=30
        )
        inventory, records, counts = trial.full_result(run.stdout, {101, 102})
        assert counts["visits"] == 3
        assert counts["groups"] == 6
        assert records
        if previous:
            old_inventory, old_records = previous
            assert old_inventory == inventory
            assert trial.errors(old_records, records)["counts"]["fractional_pass"] == 0
        previous = inventory, records
        bad = subprocess.run([binary, replay / "truncated.bin"], capture_output=True, timeout=15)
        assert bad.returncode == 2
        assert bad.stderr == b"truncated raw coarse stream\n"
        assert bad.stdout == trial.HEADER.pack(b"LEOCOUT1", 1)
