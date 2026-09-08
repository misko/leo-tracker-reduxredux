"""Execution optimizations must not reduce temporal search or change decisions."""

import ctypes as ct
import json
import math
import subprocess
from contextlib import ExitStack

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.benchmark_presence_execution import differences, numerical
from tools.native_presence import ROOT, NativePresence, build_dwell_presence, pointer
from tools.presence_dwell import NativeDwell, unpack
from tools.qualify_presence_dwell_controls import generate


@pytest.fixture(scope="module")
def libraries(tmp_path_factory):
    root = tmp_path_factory.mktemp("presence-execution")
    protocol = json.loads(
        (ROOT / "config/analysis/arm-presence-native-tone-ci16-v1.json").read_text()
    )
    common = (
        tuple(protocol["common_flags"])
        + tuple(
            f"-DLEO_PRESENCE_{key}={value}"
            for key, value in protocol["variants"][0]["defines"].items()
        )
        + ("-DLEO_PRESENCE_DIFFERENTIAL_CI16=1", "-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1")
    )
    artifacts = {}
    for name, cache, magnitude, block, diverse in (
        ("baseline", 0, 0, 0, 0),
        ("cache", 1, 0, 0, 0),
        ("magnitude", 1, 1, 0, 0),
        ("blocked", 1, 0, 1, 0),
        ("combined", 1, 1, 1, 0),
        ("diverse", 1, 0, 0, 1),
        ("diverse-combined", 1, 1, 1, 1),
        ("wide", 1, 0, 0, 0),
    ):
        if name == "wide":
            common = tuple(f for f in common if "CONDITIONED_RADIUS=" not in f) + (
                "-DLEO_PRESENCE_CONDITIONED_RADIUS=2000",
            )
        flags = common + (
            f"-DLEO_PRESENCE_PRECOMPUTE={cache}",
            f"-DLEO_PRESENCE_BOUNDED_MAGNITUDE={magnitude}",
            f"-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION={block}",
            f"-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY={diverse}",
            f"-DLEO_PRESENCE_RANK_AMPLITUDE_WEIGHTED={diverse}",
        )
        artifacts[name] = build_dwell_presence(root / f"{name}.so", cflags=flags)
        helper = root / f"{name}-helper.so"
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-shared",
                "-fPIC",
                "-O3",
                "-fno-math-errno",
                "-Wall",
                "-Wextra",
                "-Werror",
                *flags,
                str(ROOT / "tests/fixtures/native_presence_execution.c"),
                str(ROOT / "src/leo/analysis/native_presence/fft.c"),
                "-lm",
                "-o",
                str(helper),
            ],
            check=True,
        )
        api = ct.CDLL(str(helper))
        api.test_magnitude.argtypes = [ct.c_double, ct.c_double]
        api.test_magnitude.restype = ct.c_double
        api.test_execution_bytes.argtypes = [ct.c_uint32]
        api.test_execution_bytes.restype = ct.c_size_t
        api.test_rounding_guards.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_size_t]
        api.test_conditioned_scores.argtypes = [
            ct.c_void_p,
            ct.c_void_p,
            ct.c_size_t,
            ct.c_int,
            ct.c_double,
            ct.c_void_p,
        ]
        artifacts[name + "_helper"] = api
    return artifacts


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("kind", ["pilot", "pilot_plus_tone", "white_noise", "two_tones"])
def test_complete_dwell_coverage_and_numerical_parity(libraries, rate, edge, kind):
    with ExitStack() as stack:
        native = {
            name: stack.enter_context(NativeDwell(libraries[name], rate, edge, 512))
            for name in (
                "baseline",
                "cache",
                "magnitude",
                "blocked",
                "combined",
                "diverse",
                "diverse-combined",
            )
        }
        # A reused workspace sees changing windows and IQ; no retained signal
        # estimate, transmitter phase or previous dwell is an acquisition seed.
        for window in (0, 3, 5):
            iq, _ = generate(
                rate,
                edge,
                731 + window,
                kind,
                window if kind in ("pilot", "pilot_plus_tone") else None,
            )
            original = iq.tobytes()
            outputs = {
                name: numerical(unpack(n.run(iq, maximum=1, seeded=False)))
                for name, n in native.items()
            }
            assert outputs["cache"] == outputs["baseline"]
            for name in ("magnitude", "blocked", "combined"):
                assert differences(outputs["baseline"], outputs[name]) == []
            assert differences(outputs["diverse"], outputs["diverse-combined"]) == []
            assert iq.tobytes() == original


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_rotation_cache_keys_include_cfo_and_fraction_not_sample_identity(libraries, rate, edge):
    rng = np.random.default_rng(741)
    iq = rng.integers(-32768, 32768, (rate // 50, 2), dtype=np.int16)
    values = iq[:, 0].astype(float) + 1j * iq[:, 1]
    with ExitStack() as stack:
        native = {
            name: stack.enter_context(NativePresence(libraries[name], rate, edge))
            for name in ("baseline", "cache", "magnitude")
        }
        for index, (cfo, fraction) in enumerate(
            (
                (173123.0, 0.0),
                (173123.0, 0.375),
                (-400000.0, 0.375),
                (-400000.0, 0.375),
                (400000.0, -1.875),
                (0.0, 1.5),
                (173123.0, 0.0),
            )
        ):
            samples = values if index % 2 else values[::-1].copy()
            outputs = {
                name: n.glrt(samples, 317 + index, cfo, fraction) for name, n in native.items()
            }
            np.testing.assert_array_equal(outputs["cache"], outputs["baseline"])
            np.testing.assert_allclose(
                outputs["magnitude"], outputs["baseline"], rtol=1e-9, atol=1e-10
            )


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_full_scale_alternating_input_preserves_same_backend_results(libraries, rate, edge):
    # A perfectly alternating full-scale waveform has ambiguous timing. It is
    # a numerical stress control, not a positive pilot or a golden RF fixture.
    iq = np.empty((rate // 50 * 6, 2), dtype=np.int16)
    iq[::2] = [-32768, 32767]
    iq[1::2] = [32767, -32768]
    outputs = {}
    for name in ("baseline", "cache", "magnitude"):
        with NativeDwell(libraries[name], rate, edge, 512) as native:
            outputs[name] = numerical(unpack(native.run(iq, maximum=6, seeded=False)))
    assert outputs["cache"] == outputs["baseline"]
    assert differences(outputs["baseline"], outputs["magnitude"]) == []


def test_bounded_magnitude_retains_extreme_and_nonfinite_libc_fallback(libraries):
    function = libraries["magnitude_helper"].test_magnitude
    rng = np.random.default_rng(736)
    for exponent in (-1074, -1022, -600, -512, -511, -1, 0, 30, 500, 511, 512, 600, 1023):
        for real, imag in rng.uniform(-1, 1, (16, 2)):
            real, imag = math.ldexp(real, exponent), math.ldexp(imag, exponent)
            expected = math.hypot(real, imag)
            assert function(real, imag) == pytest.approx(expected, rel=7e-16, abs=0)
    for real, imag in ((0.0, -0.0), (math.inf, 0.0), (math.inf, math.nan), (math.nan, 1.0)):
        expected = math.hypot(real, imag)
        actual = function(real, imag)
        assert math.isnan(actual) if math.isnan(expected) else actual == expected


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize(
    "name,radius", [("cache", 200), ("blocked", 200), ("combined", 200), ("wide", 2000)]
)
@pytest.mark.parametrize("center", [-400000.0, -399973.125, 0.375, 399973.125, 400000.0])
@pytest.mark.parametrize("short", [False, True])
def test_compact_frequency_tables_cover_clipped_and_nonregular_endpoints(
    libraries, rate, name, radius, center, short
):
    helper = libraries[name + "_helper"]
    rng = np.random.default_rng(82)
    count = math.ceil(rate / 375) if short else rate // 50
    samples = rng.normal(size=count) + 1j * rng.normal(size=count)
    scores = np.full(44, -7.0, dtype=float)
    with NativePresence(helper._name, rate, "upper") as native:
        nf = helper.test_conditioned_scores(
            native.workspace, pointer(samples), len(samples), 317, center, pointer(scores)
        )
    start, stop = max(-400000.0, center - radius), min(400000.0, center + radius)
    frequencies = start + np.arange(math.floor((stop - start) / 100 + 1e-12) + 1) * 100
    if abs(frequencies[-1] - stop) > 1e-9:
        frequencies = np.append(frequencies, stop)
    template = qin_edge_pilot_frame(rate, "upper").astype(np.complex128)
    expected = np.zeros(len(frequencies))
    rotations = np.exp(-2j * np.pi * frequencies[:, None] * np.arange(len(template)) / rate)
    frames = 0
    for frame in range(2):
        start = 317 + round(frame * (rate / 750))
        if start + len(template) > len(samples):
            break
        row = samples[start : start + len(template)]
        expected += np.abs(rotations @ (row * template.conj())) / np.sqrt(
            np.sum(np.abs(row) ** 2) * np.sum(np.abs(template) ** 2)
        )
        frames += 1
    assert nf == len(frequencies)
    np.testing.assert_allclose(scores[:nf], expected / frames, rtol=1e-9, atol=1e-10)
    np.testing.assert_array_equal(scores[nf:], -7.0)


def test_conditioned_block_rotation_rejects_unreviewed_compile_flag():
    result = subprocess.run(
        [
            "cc",
            "-std=c11",
            "-fsyntax-only",
            "-DLEO_PRESENCE_CONDITIONED_BLOCK_ROTATION=2",
            str(ROOT / "src/leo/analysis/native_presence/presence.c"),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "LEO_PRESENCE_CONDITIONED_BLOCK_ROTATION must be 0 or 1" in result.stderr


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_compact_tables_reduce_private_allocation_without_changing_public_layout(libraries, rate):
    old = libraries["baseline_helper"].test_execution_bytes(rate)
    new = libraries["cache_helper"].test_execution_bytes(rate)
    # 42 old tables -> six bounded tables plus one GLRT rotation cache.
    # The small symbol-boundary/key additions are included in sizeof(workspace).
    saved_table_bytes = 35 * round(rate / 750) * 16
    assert saved_table_bytes - 2048 < old - new < saved_table_bytes


@pytest.mark.parametrize("name", ["baseline", "cache", "magnitude"])
def test_all_entrypoints_reject_changed_rounding_mode(libraries, name):
    helper = libraries[name + "_helper"]
    with NativePresence(helper._name, 2500000, "lower") as native:
        iq = np.ones((50000, 2), dtype=np.int16)
        samples = np.full(50000, 1 + 1j, dtype=np.complex128)
        assert (
            helper.test_rounding_guards(native.workspace, pointer(samples), pointer(iq), 50000) == 0
        )
        # Guard restores the caller's floating-point mode, so a normal call works.
        native.glrt(samples, 317, 173123.0, 0.375)


def test_benchmark_comparison_keeps_measurements_and_discards_only_timings():
    a = {
        "epoch": 9007199254741011,
        "fractional_offset_samples": 0.375,
        "total_cpu_ms": 20.0,
        "row": [{"cfo_hz": 173123.0}],
    }
    b = {**a, "total_cpu_ms": 90.0}
    assert numerical(a) == numerical(b)
    assert differences(numerical(a), numerical(b)) == []
    assert differences(numerical(a), numerical({**b, "epoch": a["epoch"] + 1})) == ["result.epoch"]
    assert differences(numerical(a), numerical({**b, "fractional_offset_samples": 0.376}))
