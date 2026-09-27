"""Generated-array numerical qualification; no saved corpus is opened."""
import ctypes as ct
from dataclasses import asdict
import importlib.util
from pathlib import Path
import sys
import mmap
import os

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'native_guided_boundary')]
from native_tone_guided import NativeToneGuided, build_library, _ResultNative
from native_guided_boundary import NativeGuidedBoundary
from leo.analysis.starlink.templates import qin_edge_pilot_frame


@pytest.fixture(scope='module')
def library():
    return build_library()


def raw_noise(rate):
    return np.random.default_rng(92931).integers(
        -700, 701, (rate * 120 // 1000, 2, 2), dtype=np.int16)


@pytest.mark.parametrize('rate', [2500000, 5000000])
@pytest.mark.parametrize('edge', ['lower', 'upper'])
def test_unapplied_nuisance_matches_raw_science(library, rate, edge):
    raw = raw_noise(rate)
    before = raw.copy()
    with NativeToneGuided(rate, edge, library) as new, NativeGuidedBoundary(rate, edge) as old:
        for rx in (0, 1):
            for phase in (0.0, 317.5, rate / 750 - .1):
                kwargs = dict(receiver=rx, probe_index=10,
                              predicted_local_epoch_sample=phase,
                              scoring_cfo_hz=400000., expected_physical_cfo_hz=400000.)
                a, b = old.guided(raw, **kwargs), new.guided(raw, **kwargs)
                assert a is not None and b is not None
                assert not b.nuisance_applied
                for name, value in asdict(a).items():
                    if name not in ('total_cpu_ms', 'total_wall_ms'):
                        assert getattr(b, name) == value, name
                assert b.glrt_evaluations == 1
                assert b.coarse_search_evaluations == b.fine_search_evaluations == 0
                assert b.conditioned_search_evaluations == b.epoch_lattice_evaluations == 0
    np.testing.assert_array_equal(raw, before)


@pytest.mark.parametrize('rate', [2500000, 5000000])
def test_applied_tone_transform_matches_frozen_blind(library, rate):
    # Reference checkout is a numerical oracle only, never a production import.
    oracle_path = Path('/home/mouse9911/gits/leo-adaptive-position-deploy/tools/native_presence.py')
    spec = importlib.util.spec_from_file_location('tone_test_presence_oracle', oracle_path)
    oracle = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = oracle
    spec.loader.exec_module(oracle)
    raw = raw_noise(rate)
    n = len(raw)
    x = 8000 * np.exp(2j * np.pi * 173123.25 * np.arange(n) / rate)
    template = np.asarray(qin_edge_pilot_frame(rate, 'lower'))
    pilot = np.zeros(n, dtype=np.complex128)
    for frame in range(91):
        start = 317 + round(frame * rate / 750)
        stop = min(n, start + len(template))
        if start < n:
            pilot[start:stop] += 3000 * template[:stop-start]
    x += pilot
    raw[:, 1, 0] += np.rint(x.real).astype(np.int16)
    raw[:, 1, 1] += np.rint(x.imag).astype(np.int16)
    before = raw.copy()
    packed = np.ascontiguousarray(raw[:rate//50, 1])
    frozen = HERE.parent / 'tg11/libtg11.so'
    with oracle.NativePresence(frozen, rate, 'lower') as blind:
        result = oracle.Result()
        assert blind.library.leo_presence_run_ci16(
            blind.workspace, packed.ctypes.data_as(ct.c_void_p), len(packed), ct.byref(result)) == 0
        nuisance = blind.nuisance()
        assert nuisance['applied'] == 1
        complete = [c for c in result.candidates[:result.candidate_count] if c.fractional_complete]
        assert complete, 'fixture must exercise an actual final blind score'
        with NativeToneGuided(rate, 'lower', library) as scorer:
            for c in complete:
                point = scorer.guided_components(raw, receiver=1, probe_index=0,
                    epoch_sample=c.epoch, fractional_offset_samples=c.fractional_offset_samples,
                    scoring_cfo_hz=c.acquired_cfo_hz, expected_physical_cfo_hz=c.tracking_cfo_hz)
                assert point is not None
                for name in ('exact_score', 'control_score', 'margin', 'tracking_cfo_hz'):
                    assert getattr(point, name) == getattr(c, name), name
                for name in ('enabled', 'applied', 'frequency_hz', 'spectral_fraction', 'fitted_power_fraction'):
                    assert getattr(point, 'nuisance_' + name) == nuisance[name]
    np.testing.assert_array_equal(raw, before)


def test_support_guard_and_error_output_untouched(library):
    rate = 2500000
    raw = np.zeros((rate * 120 // 1000, 2, 2), dtype=np.int16)
    with NativeToneGuided(rate, 'upper', library) as engine:
        args = dict(receiver=1, probe_index=0, predicted_local_epoch_sample=3268.,
                    scoring_cfo_hz=320268.11034612823, expected_physical_cfo_hz=206631.74670976176)
        point = engine.guided(raw, **args)
        assert point is not None and point.status & 2
        assert point.acquired_cfo_hz == args['scoring_cfo_hz']
        args['expected_physical_cfo_hz'] = args['scoring_cfo_hz'] - .5/4.4e-6 - 2e-6
        assert engine.guided(raw, **args) is None
        output = _ResultNative()
        ct.memset(ct.byref(output), 0xA5, ct.sizeof(output))
        before = bytes(output)
        assert engine.library.leo_tone_guided_probe_ci16(
            engine.workspace, raw.ctypes.data_as(ct.c_void_p), len(raw), 2, 0,
            317, 0., 0., 0., ct.byref(output)) != 0
        assert bytes(output) == before


def test_rx1_last_probe_guard_page(library):
    # Run in a child: any native read past the final Q sample hits PROT_NONE.
    pid = os.fork()
    if pid == 0:
        try:
            rate = 2500000
            size = rate * 120 // 1000 * 8
            page = mmap.PAGESIZE
            usable = ((size + page - 1) // page) * page
            memory = mmap.mmap(-1, usable + page)
            address = ct.addressof(ct.c_char.from_buffer(memory))
            libc = ct.CDLL(None)
            libc.mprotect.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_int]
            assert libc.mprotect(address + usable, page, 0) == 0
            raw = np.ndarray((rate * 120 // 1000, 2, 2), np.int16,
                             buffer=memory, offset=usable-size)
            raw.fill(0)
            with NativeToneGuided(rate, 'lower', library) as engine:
                result = engine.guided(raw, receiver=1, probe_index=10,
                    predicted_local_epoch_sample=317.25,
                    scoring_cfo_hz=0., expected_physical_cfo_hz=0.)
                assert result is not None
            os._exit(0)
        except BaseException:
            os._exit(1)
    _, status = os.waitpid(pid, 0)
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
