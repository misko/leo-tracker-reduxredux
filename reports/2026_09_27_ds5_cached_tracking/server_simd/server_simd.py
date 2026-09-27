"""ctypes interface for the exact runtime-dispatched server SIMD dwell."""

from __future__ import annotations

import ctypes as ct
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(REPORT / "native"), str(DEPLOY), str(DEPLOY / "src")]

from build import build  # noqa: E402
from leo.analysis.starlink.templates import qin_edge_pilot_frame  # noqa: E402
from tools.native_presence import array, pointer  # noqa: E402
from tools.presence_dwell import DwellResult  # noqa: E402
from tools.presence_window_rank import RankScreens, read_screens  # noqa: E402


class NativeServerSIMD:
    def __init__(self, rate: int, edge: str, library: Path | None = None, *, bins: int = 512):
        if type(rate) is not int or rate not in (2_500_000, 5_000_000) or edge not in ("lower", "upper"):
            raise ValueError("unsupported server SIMD geometry")
        self.rate = rate
        self.library_path = (library or build()).resolve()
        self.library = ct.CDLL(str(self.library_path))
        self.library.leo_server_simd_force.argtypes = [ct.c_int]
        self.library.leo_server_simd_force.restype = ct.c_int
        self.library.leo_server_simd_kernel.argtypes = []
        self.library.leo_server_simd_kernel.restype = ct.c_char_p
        self.library.leo_server_simd_pack_probe.argtypes = [
            ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_void_p,
        ]
        self.library.leo_server_simd_pack_probe.restype = ct.c_int
        self.library.leo_server_simd_create.argtypes = [
            ct.c_uint32, ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_uint32,
        ]
        self.library.leo_server_simd_create.restype = ct.c_void_p
        self.library.leo_server_simd_destroy.argtypes = [ct.c_void_p]
        self.library.leo_server_simd_run_ci16.argtypes = [
            ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_uint32, ct.c_uint32,
            ct.c_uint32, ct.POINTER(DwellResult),
        ]
        self.library.leo_server_simd_run_ci16.restype = ct.c_int
        self.library.leo_server_simd_get_screens.argtypes = [ct.c_void_p, ct.POINTER(RankScreens)]
        self.library.leo_server_simd_get_screens.restype = ct.c_int
        exact, control = [array(qin_edge_pilot_frame(rate, edge, symbol_roll=roll)) for roll in (0, 17)]
        self.workspace = self.library.leo_server_simd_create(
            rate, pointer(exact), pointer(control), len(exact), bins, 0
        )
        if not self.workspace:
            raise ValueError("server SIMD initialization failed")

    def force(self, mode: str) -> None:
        value = {"auto": -1, "scalar": 0, "simd": 1}.get(mode)
        if value is None or self.library.leo_server_simd_force(value):
            raise ValueError(f"unsupported kernel mode: {mode}")

    @property
    def kernel_identity(self) -> str:
        return self.library.leo_server_simd_kernel().decode("ascii")

    def run(self, raw: np.ndarray, receiver: int, *, maximum: int = 1, seeded: bool = False):
        values = np.asarray(raw)
        if (not self.workspace or values.dtype != np.dtype("int16") or
                values.shape != (self.rate // 50 * 6, 2, 2) or
                values.strides != (8, 4, 2) or not values.flags.c_contiguous or
                type(receiver) is not int or receiver not in (0, 1) or
                type(maximum) is not int or not 1 <= maximum <= 6 or type(seeded) is not bool):
            raise ValueError("sample-aligned C-contiguous dual-RX CI16 dwell required")
        result = DwellResult()
        if self.library.leo_server_simd_run_ci16(
            self.workspace, values.ctypes.data_as(ct.c_void_p), len(values), receiver,
            maximum, int(seeded), ct.byref(result),
        ):
            raise ValueError("server SIMD run rejected input")
        return result

    def screens(self):
        return read_screens(self.library, self.workspace, "leo_server_simd_get_screens")

    def close(self):
        if self.workspace:
            self.library.leo_server_simd_destroy(self.workspace)
            self.workspace = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
