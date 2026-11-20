"""Choose one native fifth-center lane per valid visit and RF center."""

import ctypes as ct

from .dual_lane import DualLane


class RfStagger:
    """One counter map per recording, called in acquisition order before detection."""

    def __init__(self):
        self._next = {}

    def reserve(self, center_hz, *, valid=True):
        if not valid:
            return None
        if type(center_hz) is not int or center_hz <= 0:
            raise ValueError("a valid visit requires its exact RF center in integer hertz")
        lane = self._next.get(center_hz, 0)
        self._next[center_hz] = 1 - lane
        return lane


class StaggeredLane(DualLane):
    """Preserve the public dual decoder and add a per-call fifth-lane selector."""

    def __init__(self, library, edge, *, helper_cpu=-1):
        super().__init__(library, edge, helper_cpu=helper_cpu)
        try:
            self._port = ct.CDLL(str(library))
            self._mixed = self._port.leo_dual_lane_analyze_staggered_v1
            self._mixed.argtypes = self.call.argtypes
            self._mixed.restype = self.call.restype
        except BaseException:
            self.__exit__()
            raise
        original = self.call
        self._selected = None

        def dispatch(ctx, mode, *args):
            if self._selected is None:
                return original(ctx, mode, *args)
            return self._mixed(ctx, self._selected, *args)

        self.call = dispatch

    def mixed(self, samples, fifth_lane, *, trace=False):
        if type(fifth_lane) is not int or fifth_lane not in (0, 1):
            raise ValueError("the fifth lane must be physical receiver 0 or 1")
        with self.lock:
            self._selected = fifth_lane
            try:
                value = self._analyze(samples, "stock", trace)
            finally:
                self._selected = None
        if trace:
            value[1]["fifth_lane"] = fifth_lane
        return value
