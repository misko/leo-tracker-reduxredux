import ctypes as ct
import os

import numpy as np
import pytest

from tools.pipeline_eval.qualification import c_coarse_tiles_build as build
from tools.pipeline_eval.qualification import c_coarse_tiles_trial as trial
from tools.pipeline_eval.variants import fine_batch
from tools.pipeline_eval.variants.portable_coarse import Coarse, Peak


@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    if not fine_batch.supports_host():
        pytest.skip("compiled comparison requires x86-64-v3")
    work = tmp_path_factory.mktemp("c-coarse-tiles")
    source = work / "source"
    build.snapshot(source)
    for method in trial.METHODS:
        build.compile_binary(work / "grid" / method, source, "x86", method, shared=True)
        build.compile_binary(work / "x86" / method, source, "x86", method)
    return work


def test_raw_packet_inventory_checks_stream_boundary():
    f = trial.RAW.pack(7, 5, 0, 3, 0, 0.0, 0.0, -40_000, 40_000)
    packet = f + bytes(5 * 8)
    [(fields, payload)] = trial.input_packets(trial.stream([packet]))
    assert fields[:5] == (7, 5, 0, 3, 0)
    assert payload == packet
    with pytest.raises(ValueError, match="truncated"):
        trial.input_packets(trial.stream([packet[:-1]]))
    with pytest.raises(ValueError, match="trailing"):
        trial.input_packets(trial.stream([packet + b"x"]))


def direct(template, iq, count, epoch, cfo):
    spacing = 26 if count == 12 else 14
    demod = np.exp(-2j * np.pi * cfo / 10_000_000 * np.arange(44))
    strengths = []
    for anchor in range(2, 2 + count * spacing, spacing):
        first = anchor * 44
        pilot = template[first : first + 44]
        for frame in range(15):
            start = first + (40_000 * frame + 1) // 3 + epoch
            signal = iq[start : start + 44]
            if len(signal) == 44:
                strengths.append(
                    abs(np.vdot(pilot, signal * demod))
                    / (np.linalg.norm(pilot) * np.linalg.norm(signal))
                )
    return np.mean(strengths), len(strengths)


@pytest.mark.hardware
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_multirate_grid_matches_direct_physical_correlations(builds, edge):
    rng = np.random.default_rng(14)
    iq = rng.integers(-1200, 1200, (26_622, 2, 2), dtype=np.int16)
    lane = ("lower", "upper").index(edge)
    values = iq[:, lane, 0] + 1j * iq[:, lane, 1]
    residuals = (-80_000, 0, 80_000)
    centers = (-4_920_000, 4_920_000)
    for anchors in (12, 22):
        ordered = {}
        for method in trial.METHODS:
            with Coarse(builds / "grid" / method / "detector.so", edge) as bank:
                seeds, peaks = bank.acquire(
                    iq, lane, anchors, centers, (residuals[0], residuals[-1])
                )
                grid, support = bank.grid()
                assert len(seeds) == 8
                for freq, residual in enumerate(residuals):
                    for epoch in (0, 127, 128, 255, 256, 13_331, 13_332):
                        score, count = direct(
                            bank.template(), values, anchors, epoch, centers[lane] + residual
                        )
                        assert count == support[epoch]
                        assert grid[freq, epoch] == pytest.approx(score, abs=4e-7)
                ordered[method] = (seeds, [peak["original_epoch"] for peak in peaks])
        assert ordered["incumbent"] == ordered["pairs"] == ordered["tiles"]


@pytest.mark.hardware
def test_equal_peaks_keep_signed_cfo_order_and_circular_suppression(builds):
    scores = np.zeros((2, 64), dtype=np.float64)
    scores[0, [0, 63, 20]] = 1
    scores[1, [0, 20]] = 1
    residuals = np.array([-5_000.0, 5_000.0])
    mask = np.empty_like(scores, dtype=np.uint8)
    for method in trial.METHODS:
        lib = ct.CDLL(str(builds / "grid" / method / "detector.so"))
        select = lib.portable_coarse_select
        select.argtypes = (
            ct.c_void_p,
            ct.c_void_p,
            ct.c_uint,
            ct.c_uint,
            ct.c_void_p,
            ct.POINTER(Peak),
        )
        select.restype = ct.c_uint
        peaks = (Peak * 8)()
        count = select(scores.ctypes.data, residuals.ctypes.data, 2, 64, mask.ctypes.data, peaks)
        positive = [(p.original_epoch, p.cfo_lane) for p in peaks[:count] if p.score > 0]
        assert positive == [(0, 0), (20, 0)]


@pytest.mark.hardware
def test_complete_receiver_regenerates_null_and_repeated_pilot_controls(builds, tmp_path):
    with Coarse(builds / "grid" / "incumbent" / "detector.so", "upper") as bank:
        pilot = bank.template()
    n = 200_000
    epoch = 707
    rng = np.random.default_rng(51)
    raw = rng.integers(-25, 25, (n, 2, 2), dtype=np.int16)
    offsets = np.arange(len(pilot))
    for frame in range(14):
        start = epoch + (40_000 * frame + 1) // 3
        p = 4_500 * pilot * np.exp(2j * np.pi * (start + offsets) * 21_000 / 10_000_000)
        raw[start : start + len(pilot), 0, 0] += p.real.astype(np.int16)
        raw[start : start + len(pilot), 0, 1] += p.imag.astype(np.int16)
    fields = (n, 1, 3, 1, 0.0, 0.0, -80_000.0, 80_000.0)
    zero = trial.RAW.pack(1, *fields) + bytes(n * 8)
    live = [trial.RAW.pack(i, *fields) + raw.astype("<i2").tobytes() for i in (2, 3)]
    path = tmp_path / "control.ci16"
    path.write_bytes(trial.stream([zero, *live]))
    cpu = min(os.sched_getaffinity(0))
    baseline = None
    for method in trial.METHODS:
        visits, _, _ = trial.run(builds, method, "x86", cpu, path)
        assert not any(group["seeds"] for group in visits[0][1])
        assert trial.compare(visits[1][1], visits[2][1]) == {
            "inventory_equal": True,
            "ordered_peaks_equal": True,
            "verifier_bytes_equal": True,
            "max_abs_peak_score": 0,
        }
        counts, candidates = trial.evidence(visits[1][1])
        assert counts["integer_pass"] >= 1
        assert counts["fractional_pass"] >= 1
        assert any(c["epoch"] == epoch and c["flags"] & 2 for c in candidates)
        if baseline is None:
            baseline = visits[1][1]
        else:
            compare = trial.compare(baseline, visits[1][1])
            assert compare["ordered_peaks_equal"]
            assert compare["verifier_bytes_equal"]
