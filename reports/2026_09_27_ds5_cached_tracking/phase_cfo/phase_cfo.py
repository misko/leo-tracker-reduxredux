"""Binding for the isolated lag-4 phase-CFO blind detector."""

from __future__ import annotations

import ctypes as ct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NATIVE_REPORT = HERE.parent / "native"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
sys.path[:0] = [str(NATIVE_REPORT), str(DEPLOY), str(DEPLOY / "src")]

from blind_strided_v4 import NativeStridedBlindV4  # noqa: E402
from tools.native_presence import Profile  # noqa: E402

from build import build  # noqa: E402


class NativePhaseCFO(NativeStridedBlindV4):
    def __init__(self, rate: int, edge: str):
        super().__init__(rate, edge, library=build(), bins=512)
        self.library.leo_phase_cfo_get_profile.argtypes = [ct.c_void_p, ct.POINTER(Profile)]
        self.library.leo_phase_cfo_get_profile.restype = ct.c_int

    def profile(self) -> dict:
        result = Profile()
        if self.library.leo_phase_cfo_get_profile(self.workspace, ct.byref(result)):
            raise ValueError("phase-CFO profile unavailable")
        return {name: getattr(result, name) for name, _ in result._fields_}
