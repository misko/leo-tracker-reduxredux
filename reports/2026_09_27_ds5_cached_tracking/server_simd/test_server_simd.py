from __future__ import annotations

import ctypes as ct
import hashlib
import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
NATIVE = REPORT / "native"
FP32 = REPORT / "fft32" / "libfft32_fftw.so"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(HERE), str(NATIVE), str(DEPLOY), str(DEPLOY / "src")]

from blind_strided_v4 import NativeStridedBlindV4  # noqa: E402
from server_simd import NativeServerSIMD  # noqa: E402
from tools.presence_dwell import DwellResult  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scientific(value):
    if isinstance(value, ct.Structure):
        return {
            name: scientific(getattr(value, name))
            for name, _ in value._fields_
            if "cpu_ms" not in name and "wall_ms" not in name
        }
    if isinstance(value, ct.Array):
        return [scientific(item) for item in value]
    return value


def make_random(rate: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(-32768, 32768, (rate * 120 // 1000, 2, 2), dtype=np.int16)


def make_extrema(rate: int) -> np.ndarray:
    count = rate * 120 // 1000
    pattern = np.array(
        [
            [-32768, -32768, 32767, 32767],
            [32767, -32768, -32768, 32767],
            [-32768, 32767, 32767, -32768],
            [32767, 32767, -32768, -32768],
            [1, -1, -1, 1],
            [0, 0, 0, 0],
            [12345, -23456, -32100, 21000],
        ],
        dtype=np.int16,
    )
    return np.resize(pattern, (count, 4)).reshape(count, 2, 2)


@pytest.fixture(scope="module")
def library() -> Path:
    spec = importlib.util.spec_from_file_location("server_simd_build_test", HERE / "build.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build()


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("receiver", [0, 1])
@pytest.mark.parametrize("kind", ["random", "extrema"])
def test_forced_simd_is_scientifically_exact(library, rate, receiver, kind):
    raw = make_random(rate, rate + receiver) if kind == "random" else make_extrema(rate)
    before = raw.copy()
    with NativeServerSIMD(rate, "lower", library) as detector:
        detector.force("scalar")
        expected = detector.run(raw, receiver, maximum=1, seeded=False)
        expected_screens = detector.screens()
        assert detector.kernel_identity == "scalar-forced"
        detector.force("simd")
        actual = detector.run(raw, receiver, maximum=1, seeded=False)
        actual_screens = detector.screens()
        assert detector.kernel_identity == "ssse3-sse4.1-forced"
        detector.force("auto")
    assert scientific(actual) == scientific(expected)
    assert scientific(actual_screens) == scientific(expected_screens)
    np.testing.assert_array_equal(raw, before)


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("receiver", [0, 1])
def test_scalar_and_simd_match_frozen_fp32_library(library, rate, receiver):
    raw = make_random(rate, 91 + rate + receiver)
    before = raw.copy()
    with NativeStridedBlindV4(rate, "upper", library=FP32, bins=512) as baseline, \
            NativeServerSIMD(rate, "upper", library) as candidate:
        expected = baseline.run(raw[:, receiver, :], maximum=1, seeded=False)
        expected_screens = baseline.screens()
        for mode in ("scalar", "simd"):
            candidate.force(mode)
            actual = candidate.run(raw, receiver, maximum=1, seeded=False)
            assert scientific(actual) == scientific(expected)
            assert scientific(candidate.screens()) == scientific(expected_screens)
        candidate.force("auto")
    np.testing.assert_array_equal(raw, before)


def test_pack_probe_exact_for_terminal_remainders_and_invalid_is_untouched(library):
    native = ct.CDLL(str(library))
    native.leo_server_simd_force.argtypes = [ct.c_int]
    native.leo_server_simd_pack_probe.argtypes = [
        ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_void_p,
    ]
    native.leo_server_simd_pack_probe.restype = ct.c_int
    rng = np.random.default_rng(888)
    for count in range(1, 18):
        raw = rng.integers(-32768, 32768, (count, 2, 2), dtype=np.int16)
        for mode in (0, 1):
            assert native.leo_server_simd_force(mode) == 0
            for receiver in (0, 1):
                output = np.full((count, 2), 123, dtype=np.int16)
                assert native.leo_server_simd_pack_probe(
                    raw.ctypes.data, count, receiver, output.ctypes.data
                ) == 0
                np.testing.assert_array_equal(output, raw[:, receiver, :])
    sentinel = np.full((4, 2), -1234, dtype=np.int16)
    assert native.leo_server_simd_pack_probe(0, 4, 0, sentinel.ctypes.data) == -1
    assert native.leo_server_simd_pack_probe(raw.ctypes.data, 4, 2, sentinel.ctypes.data) == -1
    np.testing.assert_array_equal(sentinel, -1234)
    assert native.leo_server_simd_force(-1) == 0


def test_invalid_run_does_not_modify_result(library):
    raw = make_random(2_500_000, 421)
    with NativeServerSIMD(2_500_000, "lower", library) as detector:
        result = DwellResult()
        ct.memset(ct.byref(result), 0xA5, ct.sizeof(result))
        before = bytes(result)
        status = detector.library.leo_server_simd_run_ci16(
            detector.workspace, raw.ctypes.data, len(raw), 2, 1, 0, ct.byref(result)
        )
        assert status == -1
        assert bytes(result) == before


@pytest.mark.parametrize("kind", ["zero", "tone"])
def test_zero_and_active_tone_nuisance_paths_are_exact(library, kind):
    rate = 2_500_000
    count = rate * 120 // 1000
    if kind == "zero":
        raw = np.zeros((count, 2, 2), dtype=np.int16)
    else:
        sample = np.arange(count)
        tone = np.rint(30000 * np.exp(2j * np.pi * 100_000 * sample / rate))
        iq = np.stack((tone.real, tone.imag), axis=1).astype(np.int16)
        raw = np.stack((iq, iq), axis=1)
    with NativeStridedBlindV4(rate, "lower", library=FP32, bins=512) as baseline, \
            NativeServerSIMD(rate, "lower", library) as candidate:
        expected = baseline.run(raw[:, 1, :], maximum=1, seeded=False)
        for mode in ("scalar", "simd"):
            candidate.force(mode)
            actual = candidate.run(raw, 1, maximum=1, seeded=False)
            assert scientific(actual) == scientific(expected)
            if kind == "tone":
                assert actual.nuisances[0].enabled == 1
                assert actual.nuisances[0].applied == 1
        candidate.force("auto")


def test_guard_page_catches_terminal_rx1_overread(library):
    child = r'''
import ctypes as ct
import sys

lib = ct.CDLL(sys.argv[1])
lib.leo_server_simd_force.argtypes = [ct.c_int]
lib.leo_server_simd_pack_probe.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_void_p]
lib.leo_server_simd_pack_probe.restype = ct.c_int
libc = ct.CDLL(None)
libc.mmap.restype = ct.c_void_p
page = 4096
PROT_READ, PROT_WRITE, PROT_NONE = 1, 2, 0
MAP_PRIVATE, MAP_ANONYMOUS = 2, 0x20
base = libc.mmap(None, 2 * page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0)
if base in (None, ct.c_void_p(-1).value):
    raise SystemExit(2)
if libc.mprotect(ct.c_void_p(base + page), page, PROT_NONE):
    raise SystemExit(3)
try:
    for count in range(1, 18):
        start = base + page - count * 8
        values = (ct.c_int16 * (count * 4)).from_address(start)
        for k in range(count * 4):
            values[k] = (k * 1229 + count * 41) % 65536 - 32768
        expected = list(values)
        for mode in (0, 1):
            if lib.leo_server_simd_force(mode):
                raise SystemExit(4)
            for receiver in (0, 1):
                output = (ct.c_int16 * (count * 2))()
                if lib.leo_server_simd_pack_probe(start, count, receiver, output):
                    raise SystemExit(5)
                truth = [expected[4*k + 2*receiver + lane] for k in range(count) for lane in (0, 1)]
                if list(output) != truth:
                    raise SystemExit(6)
finally:
    libc.munmap(ct.c_void_p(base), 2 * page)
'''
    completed = subprocess.run(
        [sys.executable, "-c", child, str(library)], capture_output=True, text=True
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)


def test_full_rank_terminal_rx1_stops_at_guard_page(library):
    child = r'''
import ctypes as ct
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, sys.argv[2])
from server_simd import NativeServerSIMD

rate = 2_500_000
count = rate * 120 // 1000
byte_count = count * 8
page = 4096
data_pages = (byte_count + page - 1) // page
libc = ct.CDLL(None)
libc.mmap.restype = ct.c_void_p
PROT_READ, PROT_WRITE, PROT_NONE = 1, 2, 0
MAP_PRIVATE, MAP_ANONYMOUS = 2, 0x20
base = libc.mmap(None, (data_pages + 1) * page, PROT_READ | PROT_WRITE,
                 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0)
if base in (None, ct.c_void_p(-1).value):
    raise SystemExit(2)
guard = base + data_pages * page
if libc.mprotect(ct.c_void_p(guard), page, PROT_NONE):
    raise SystemExit(3)
start = guard - byte_count
libc.memset(ct.c_void_p(start), 0x5A, byte_count)
storage = (ct.c_int16 * (count * 4)).from_address(start)
raw = np.ctypeslib.as_array(storage).reshape(count, 2, 2)
try:
    with NativeServerSIMD(rate, "lower", Path(sys.argv[1])) as detector:
        detector.force("simd")
        for receiver in (0, 1):
            result = detector.run(raw, receiver, maximum=1, seeded=False)
            if result.confirmation_count != 1:
                raise SystemExit(4)
finally:
    libc.munmap(ct.c_void_p(base), (data_pages + 1) * page)
'''
    completed = subprocess.run(
        [sys.executable, "-c", child, str(library), str(HERE)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)


def test_first_dispatch_is_thread_safe_in_fresh_process(library):
    child = r'''
import ctypes as ct
import sys
import threading

lib = ct.CDLL(sys.argv[1])
lib.leo_server_simd_force.argtypes = [ct.c_int]
lib.leo_server_simd_kernel.restype = ct.c_char_p
barrier = threading.Barrier(8)
values = []
def worker():
    if lib.leo_server_simd_force(-1):
        values.append(b"error")
        return
    barrier.wait()
    values.append(lib.leo_server_simd_kernel())
threads = [threading.Thread(target=worker) for _ in range(8)]
for thread in threads: thread.start()
for thread in threads: thread.join()
if values != [b"ssse3-sse4.1-auto"] * 8:
    raise SystemExit(repr(values))
'''
    completed = subprocess.run(
        [sys.executable, "-c", child, str(library)], capture_output=True, text=True
    )
    assert completed.returncode == 0, (completed.stdout, completed.stderr)


def test_build_receipt_pins_sources_and_attests_no_global_isa(library):
    receipt = json.loads(library.with_name(library.name + ".build.json").read_text())
    assert receipt["binary_sha256"] == digest(library)
    assert receipt["global_isa_flags_added"] == []
    assert receipt["simd_dispatch"].startswith("CPUID SSSE3+SSE4.1")
    assert set(receipt["effective_custom_dependencies"]) <= set(
        receipt["preprocessor_dependencies"]
    )
    assert all(Path(path).parent == HERE for path in receipt["effective_custom_dependencies"])
    for source, expected in receipt["sources_sha256"].items():
        assert digest(Path(source)) == expected
    for name in receipt["generated_parent_sources_match_upstream"]:
        assert (HERE / name).read_bytes() == (
            DEPLOY / "src/leo/analysis/native_presence" / name
        ).read_bytes()
