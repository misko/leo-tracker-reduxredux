"""Isolate acquisition timing from truth-blind whole-dwell qualification."""

import json
import subprocess
from contextlib import ExitStack

import numpy as np
import pytest

from tools.native_presence import ROOT, NativePresence, build_library
from tools.presence_dwell import unpack
from tools.presence_structured_challenge import generate


@pytest.fixture(scope="module")
def protocol():
    return json.loads(
        (ROOT / "config/analysis/arm-presence-energy-support-challenge-v1.json").read_text()
    )


@pytest.fixture(scope="module")
def libraries(tmp_path_factory, protocol):
    detector = json.loads((ROOT / protocol["detector_protocol"]).read_text())
    flags = (
        tuple(detector["common_flags"])
        + tuple(f"-DLEO_PRESENCE_{k}={v}" for k, v in detector["variants"][0]["defines"].items())
        + ("-DLEO_PRESENCE_DIFFERENTIAL_CI16=1", "-DLEO_PRESENCE_GLRT_SYMBOL_DIVERSITY=1")
    )
    root = tmp_path_factory.mktemp("presence-support")
    return {
        name: build_library(root / f"{name}.so", cflags=flags + extra)
        for name, extra in (
            ("default", ()),
            ("disabled", ("-DLEO_PRESENCE_ENERGY_SUPPORT=0",)),
            ("supported", ("-DLEO_PRESENCE_ENERGY_SUPPORT=1",)),
        )
    }


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_late_burst_acquisition_and_reuse_keep_original_fractional_epoch(
    libraries, protocol, rate, edge
):
    # Seeded epoch isolates CFO/epoch refinement from the independent ranker.
    # The complete challenge remains blind and uses different seeds.
    with NativePresence(libraries["supported"], rate, edge) as native:
        for start in (56.0, 40.0, 56.0):
            iq, truth = generate(
                dict(
                    rate_hz=rate,
                    edge=edge,
                    seed=995101,
                    kind="pilot",
                    snr_db=12.0,
                    start_ms=start,
                    duration_ms=4.0,
                ),
                protocol,
            )
            section = iq[rate // 25 : rate * 3 // 50].copy()
            original = section.copy()
            result = unpack(native.confirm(section, round(truth["epoch_samples"])))
            assert result["candidate_count"] == 1
            candidate = result["candidates"][0]
            assert abs(candidate["acquired_cfo_hz"] - truth["cfo_hz"]) < 800
            assert candidate["fractional_complete"]
            assert (
                abs(
                    candidate["epoch"]
                    + candidate["fractional_offset_samples"]
                    - truth["epoch_samples"]
                )
                / rate
                < 2e-6
            )
            assert candidate["exact_score"] >= 0.175 and candidate["margin"] >= 0.025
            assert native.profile()["fine_frames"] == native.profile()["epoch_frames"] == 2
            np.testing.assert_array_equal(section, original)


def test_default_off_is_numerically_identical_and_final_glrt_never_moves(libraries, protocol):
    iq, truth = generate(
        dict(
            rate_hz=2500000,
            edge="lower",
            seed=995102,
            kind="pilot",
            snr_db=6.0,
            start_ms=56.0,
            duration_ms=4.0,
        ),
        protocol,
    )
    section = iq[100000:150000]
    values = section[:, 0].astype(float) + 1j * section[:, 1]
    with ExitStack() as stack:
        engines = {
            name: stack.enter_context(NativePresence(path, 2500000, "lower"))
            for name, path in libraries.items()
        }
        results = {name: unpack(native.run(values)) for name, native in engines.items()}
        assert results["default"]["candidate_count"] == results["disabled"]["candidate_count"]
        assert results["default"]["candidates"] == results["disabled"]["candidates"]
        # Force previous acquisition support near the terminal end, then call
        # the public final statistic at a fixed position. Support must not leak.
        scores = [
            native.glrt(values, round(truth["epoch_samples"]), truth["cfo_hz"], 0.375)
            for native in engines.values()
        ]
        for score in scores[1:]:
            np.testing.assert_array_equal(score, scores[0])
        zeros = np.zeros_like(section)
        for native in engines.values():
            result = unpack(native.confirm(zeros, 300))
            assert all(np.isfinite(c["exact_score"]) for c in result["candidates"])


@pytest.mark.parametrize(
    "defines",
    [
        ("-DLEO_PRESENCE_ENERGY_SUPPORT=2",),
        ("-DLEO_PRESENCE_ENERGY_SUPPORT=1", "-DLEO_PRESENCE_FINE_FRAMES=3"),
        ("-DLEO_PRESENCE_ENERGY_SUPPORT=1", "-DLEO_PRESENCE_EPOCH_FRAMES=3"),
    ],
)
def test_unreviewed_support_geometry_does_not_compile(tmp_path, defines):
    with pytest.raises(subprocess.CalledProcessError):
        build_library(tmp_path / "invalid.so", cflags=defines)
