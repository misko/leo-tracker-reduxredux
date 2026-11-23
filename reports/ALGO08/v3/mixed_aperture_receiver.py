"""One complete stereo scout, four short stereo primaries and three quiet slots."""

from collections import Counter
from contextlib import contextmanager
import ctypes as ct
from hashlib import sha256
from pathlib import Path
from time import process_time_ns, perf_counter_ns


INSTALLED_SHA = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
PILOT_SHA = {
    "lower": "1b98937cbd87fd5f27b82e4d535512ca5ee12b33a64a6bae90e07ec041368adb",
    "upper": "eef7b89526adb80fc64cd0be61f35b7cc5edceb3eb293d72066378e751b4467c",
}
RULE = ("full", "short_primary", "skip", "short_primary", "skip", "short_primary", "skip", "short_primary")
FULL_RULE = ("full",) + ("short_primary",) * 7


def verified(path, expected):
    if path is None:
        raise ValueError("The mixed receiver requires a concrete pinned artifact")
    contents = Path(path).read_bytes()
    if sha256(contents).hexdigest() != expected:
        raise ValueError(f"The mixed receiver artifact differs at {path}")
    return contents


class StereoSchedule:
    def __init__(self, *, full_coverage=False):
        self.rule = FULL_RULE if full_coverage else RULE
        self.streams = {}

    def visit(self, edge, target, capture):
        if edge != target["edge"]:
            raise ValueError("The visit uses the wrong pilot edge")
        rf_hz = float(capture["actual_if_center_hz"] + target["lnb_lo_hz"])
        key = (edge, target["channel"], rf_hz)
        counter = capture["sample_start"]
        index, last = self.streams.get(key, (0, None))
        if last is not None and counter <= last:
            raise ValueError("Chronological native opportunity required for each RF and edge")
        self.streams[key] = (index + 1, counter)
        return index, self.rule[index % len(self.rule)]


def strongest(candidates):
    if any(not row["passed_fractional_margin_gate"] for row in candidates):
        raise ValueError("A native call exported an unverified candidate")
    return max(candidates, key=lambda row: (row["fractional_margin"], -row["candidate_rank"]), default=None)


class NativePath:
    """Bind one native library and one fixed aperture without search fallthrough."""

    def __init__(self, library, asset, mode):
        from tools.pipeline_eval.qualification.blind_compact_run import Factor, Native

        self.native = Native(Path(library), asset)
        self.factor = Factor
        self.maximum = 1 if mode == "short_primary" else 2
        symbol = "cancellation_primary_factors" if self.maximum == 1 else "cancellation_factors"
        try:
            self.call = getattr(self.native.lib, symbol)
        except AttributeError:
            self.native.close()
            raise
        self.call.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(Factor)]
        self.call.restype = ct.c_int

    def close(self):
        self.native.close()

    def run(self, samples, lane, center):
        out = (self.factor * 2)()
        begin = process_time_ns(), perf_counter_ns()
        count = self.call(self.native.ctx, samples.ctypes.data, lane, center-800000, center+800000, out)
        clock = process_time_ns()-begin[0], perf_counter_ns()-begin[1]
        if not 0 <= count <= self.maximum:
            raise ValueError("The native aperture returned an invalid factor count")
        if self.maximum == 1 and count and out[0].rank != 0:
            raise ValueError("The primary ABI emitted a residual factor")
        rows = tuple(tuple(getattr(factor, key) for key, _ in self.factor._fields_) for factor in out[:count])
        return rows, clock


class MixedApertureDetector:
    def __init__(self, short_binary, short_sha256, *, full_coverage=False):
        self.short_binary = Path(short_binary).resolve()
        self.short_sha256 = short_sha256
        self.schedule = StereoSchedule(full_coverage=full_coverage)
        self.active = set()
        self.visits = Counter()
        self.native_calls = Counter()
        self.factors = Counter()
        self.native_cpu_ns = Counter()
        self.native_wall_ns = Counter()

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        import numpy as np
        from tools.pipeline_eval.qualification.blind_compact_run import _probe, factor_candidate

        if method != "cancellation" or edge in self.active:
            raise ValueError("Expected a single scoped signed receiver per pilot edge")
        verified(binary, INSTALLED_SHA)
        verified(self.short_binary, self.short_sha256)
        asset = np.frombuffer(verified(pilot, PILOT_SHA[edge]), dtype="<f4")
        if asset.shape != (133413,):
            raise ValueError("Expected the pinned signed receiver pilot")
        full = NativePath(binary, asset, "full")
        try:
            short = NativePath(self.short_binary, asset, "short_primary")
        except BaseException:
            full.close()
            raise
        engines = {"full": full, "short_primary": short}
        self.active.add(edge)
        open_scope = True

        def receive(window):
            if not open_scope:
                raise RuntimeError("The native mixed-aperture context has closed")
            samples = window.samples
            if (tuple(window.receiver_ids) != (0, 1) or window.sample_rate_hz != 10_000_000
                    or samples.shape != (200_000, 2, 2) or samples.dtype != np.dtype("<i2")
                    or not samples.flags.c_contiguous):
                raise ValueError("Expected the unmodified 20 ms stereo CI16 input")
            target, acquisition = window.target, window.acquisition
            _, mode = self.schedule.visit(edge, target, acquisition)
            self.visits[mode] += 1
            center = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
            output = []
            for lane in window.receiver_ids:
                candidates = []
                if mode in engines:
                    measured, (cpu, wall) = engines[mode].run(samples, lane, center)
                    self.native_calls[mode] += 1
                    self.native_cpu_ns[mode] += cpu
                    self.native_wall_ns[mode] += wall
                    candidates = [factor_candidate(rank, epoch, status="complete", offset=offset, cfo=hz,
                                                   exact=exact, control=roll, margin=exact-roll)
                                  for rank, epoch, offset, hz, exact, roll in measured]
                selected = strongest(candidates)
                self.factors[mode] += selected is not None
                output.append(_probe(window, lane, [] if selected is None else [selected]))
            return output

        try:
            yield receive
        finally:
            open_scope = False
            self.active.remove(edge)
            short.close()
            full.close()

    def receipt(self):
        return dict(rule=list(self.schedule.rule), installed_sha256=INSTALLED_SHA, short_primary_sha256=self.short_sha256,
                    visits=dict(self.visits), native_calls=dict(self.native_calls),
                    factors=dict(self.factors), native_cpu_ns=dict(self.native_cpu_ns),
                    native_wall_ns=dict(self.native_wall_ns),
                    streams=[dict(edge=edge, channel=ch, rf_hz=rf, admitted=count,
                                  final_valid_counter=last)
                             for (edge, ch, rf), (count, last) in sorted(self.schedule.streams.items())])
