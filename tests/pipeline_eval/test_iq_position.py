from __future__ import annotations

import json
import subprocess
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
from sgp4.api import SatrecArray

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets
from leo.storage.short_window import ShortWindowWriter
from native.adaptive.detector.build import build
from tests.pipeline_eval.geometry import tle
from tools.pipeline_eval.variants.iq_position import replay, replay_metrics, run
from tools.pipeline_eval.variants.iq_stream import load_windows

RATE = 2_500_000
ANCHOR = 1_767_571_200_000_000_000
DAY_NS = 86_400 * 10**9
TRUTH = (80.02, -179.86)
REGIONS = [
    dict(id="offset", center=[-40.0, 60.0]),
    dict(id="dateline", center=[79.94, 179.95]),
    dict(id="other", center=[29.0, -90.0]),
    dict(id="remote", center=[-27.0, 130.0]),
]
LO = 9_750_000_000
TARGETS = [
    dict(target_id=f"ch{channel}", edge="lower", channel=channel, lnb_lo_hz=LO)
    for channel in range(1, 7)
]


@pytest.fixture(scope="module")
def native_library(tmp_path_factory):
    root = tmp_path_factory.mktemp("pipeline-native")
    compiler = Path("/usr/bin/gcc")
    float_archive = subprocess.check_output(
        [compiler, "-print-file-name=libfftw3f.a"], text=True
    ).strip()
    prefix = root / "fftw"
    (prefix / "include").mkdir(parents=True)
    (prefix / "lib").mkdir()
    (prefix / "include/fftw3.h").symlink_to("/usr/include/fftw3.h")
    (prefix / "lib/libfftw3f.a").symlink_to(float_archive)
    build(
        output_dir=root / "output",
        work_dir=root / "work",
        compiler=compiler,
        archiver=Path("/usr/bin/gcc-ar"),
        fftw_prefix=prefix,
        target="host",
    )
    return root / "output/libleo-adaptive-detector.so"


def _scene():
    rng = np.random.default_rng(550)
    text = "".join(
        tle(
            number,
            4.45,
            rng.uniform(0, 360),
            rng.uniform(0, 360),
            rng.uniform(75, 100),
            rng.uniform(14.8, 15.8),
        )
        for number in range(1000, 1256)
    )
    satellites = SatrecArray(parse_element_sets(text).satellites)
    site = geodetic_to_ecef_km(*TRUTH, 0.0)
    up = ecef_to_enu_matrix(*TRUTH)[2]
    plan = []
    used = set()
    for start in (0.0, 168.0):
        times = start + np.arange(14) * 4
        jday, frac = julian_day_from_utc_ns(ANCHOR + np.rint((times + 0.08) * 1e9).astype(np.int64))
        errors, r, v = satellites.sgp4(jday, frac)
        assert not errors.any()
        r, _ = teme_to_ecef(r, v, greenwich_mean_sidereal_time_rad(jday, frac))
        delta = r - site
        elevation = (delta @ up) / np.linalg.norm(delta, axis=-1)
        eligible = [
            i
            for i in np.argsort(-elevation.mean(axis=1))
            if i not in used and min(elevation[i]) > 0.14
        ][: len(TARGETS)]
        assert len(eligible) == len(TARGETS)
        used.update(eligible)
        for lane, satellite in enumerate(eligible):
            if_hz = 950_000_000 + lane * 100_000_000
            rf_hz = LO + if_hz
            starts = times + lane * 0.024
            jday, frac = julian_day_from_utc_ns(
                ANCHOR + np.rint((starts + 0.010) * 1e9).astype(np.int64)
            )
            errors, r, v = satellites.sgp4(jday, frac)
            assert not errors.any()
            r, v = teme_to_ecef(
                r[satellite], v[satellite], greenwich_mean_sidereal_time_rad(jday, frac)
            )
            delta = r - site
            rays = delta / np.linalg.norm(delta, axis=-1)[:, None]
            cfo = -(rf_hz / 299792.458) * np.sum(rays * v, axis=1)
            cfo += 22_000 * (rf_hz / 1e9 - 11.5)
            plan.extend((t, lane, if_hz, f) for t, f in zip(starts, cfo, strict=True))
    return text, sorted(plan)


def _archive(root, plan, pilot=True):
    count = RATE // 50
    writer = ShortWindowWriter(
        root,
        "waveforms",
        configuration={"targets": TARGETS},
        radio={"provider": "test"},
        receiver_ids=(0,),
        chunk_windows=32,
    )
    template = qin_edge_pilot_frame(RATE, "lower")
    rng = np.random.default_rng(78426)
    base_counter = 100_000
    bracket = dict(
        sample_counter=base_counter,
        before={"realtime_ns": ANCHOR - 10_000},
        after={"realtime_ns": ANCHOR + 10_000},
    )
    for sequence, (t, lane, if_hz, hz) in enumerate(plan):
        n = np.arange(count)
        noise = rng.normal(0, 8, (count, 1, 2))
        if pilot:
            seconds = n / RATE
            time_phase = np.zeros(count, dtype=complex)
            epoch = 600 + lane * 150
            for frame in np.rint(np.arange(15) * RATE / 750).astype(int):
                first = frame + epoch
                last = min(count, first + len(template))
                time_phase[first:last] = template[: last - first]
            signal = 1_200 * time_phase * np.exp(2j * np.pi * hz * seconds)
            noise[:, 0] += np.stack((signal.real, signal.imag), axis=1)
        counter = base_counter + round(t * RATE)
        writer.append(
            sequence=sequence,
            target_id=f"ch{lane + 1}",
            samples=np.rint(noise).astype("<i2"),
            acquisition=dict(
                sample_start=counter,
                sample_end=counter + count,
                generation=8,
                device_session=19,
                global_visit=sequence,
                complete=True,
                validity_authority="provider_attested",
                counter_authority="hardware",
                actual_if_center_hz=if_hz,
                quality_flags=[],
                retune_receipt=json.dumps({"utc_clock_bracket": bracket if not sequence else None}),
            ),
            powers=({"decision": "quiet"},),
        )
    path = writer.finish(stop_reason="fixture") / "manifest.json"
    case = dict(
        recording_path=str(path), recording_sha256="sha256:" + sha256(path.read_bytes()).hexdigest()
    )
    return case


def _replay(case, count, catalogue, native_library, path):
    return replay(
        iter(load_windows(case, range(count))),
        REGIONS,
        catalogue,
        ANCHOR - DAY_NS // 4,
        native_library,
        path,
        replay_metrics(count),
    )


def test_planted_iq_reaches_causal_association_and_position(native_library, tmp_path: Path):
    catalogue, plan = _scene()
    case = _archive(tmp_path, plan)
    result = _replay(case, len(plan), catalogue, native_library, tmp_path)
    assert result["status"] == "ok", result
    assert result["arms"]["c0"] == result["arms"]["fitted_c"]
    fix = result["arms"]["c0"]["latlon"]
    error_km = np.linalg.norm(geodetic_to_ecef_km(*fix, 0.0) - geodetic_to_ecef_km(*TRUTH, 0.0))
    assert error_km < 2.0
    assert result["metrics"]["projected_detections"] >= len(plan)
    assert result["metrics"]["tracks"] == 12
    assert result["metrics"]["causal_satellites"] == 256
    assert result["metrics"]["association_ran"]
    assert result["metrics"]["time_shift_controls"] == 19
    assert result["metrics"]["windows_analyzed"] == len(plan)


def test_noise_withholds_and_missing_recording_is_unavailable(native_library, tmp_path: Path):
    plan = [(float(t), 0, 950_000_000, 0.0) for t in range(4)]
    case = _archive(tmp_path, plan, pilot=False)
    result = _replay(case, len(plan), "", native_library, tmp_path)
    assert result["status"] == "withheld"
    assert result["metrics"]["windows_analyzed"] == len(plan)
    assert result["metrics"]["projected_detections"] == 0
    assert all(arm["latlon"] is None for arm in result["arms"].values())
    assert not result["metrics"]["association_ran"]
    assert run({"panel": "Synthetic", **case}, tmp_path)["status"] == "unavailable"
