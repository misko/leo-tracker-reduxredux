"""Opt-in exact fine-salvage projection limited to its consumed outputs."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from struct import pack
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from rescue_phase_prepare import PreparedFinePhase, ShadowMismatch, exact_port


FRAME_PIN = "b6c98c11d25957c8f535d09a4f4cc47f3f82745b63ca57c61f9e8d5949fbb8e0"
KINDS = ("ordinary", "prepared", "projected")


class FineDopplerElevation(PreparedFinePhase):
    """Keep the original binary64 range-rate and elevation, with a local ENU frame."""

    def __init__(self, bank, times, phases):
        super().__init__(bank, times, phases)
        self.frame_key = None
        self.frame = None

    def project(self, j, coordinates):
        from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

        if (len(coordinates) != 2 or not all(type(x) in (float, np.float64) for x in coordinates)
                or not np.isfinite(coordinates).all()):
            return super().project(j, coordinates)
        key = pack("!2d", *coordinates)
        if self.frame_key != key:
            self.frame = geodetic_to_ecef_km(*coordinates, 0.0), ecef_to_enu_matrix(*coordinates)
            self.frame_key = key
        observer, orient = self.frame
        position, velocity = self.interpolate(j)
        relative = position - observer
        enu = relative @ orient.T
        slant_range = np.linalg.norm(relative, axis=-1)
        elevation = np.rad2deg(np.arctan2(enu[..., 2], np.hypot(enu[..., 0], enu[..., 1])))
        with np.errstate(invalid="ignore", divide="ignore"):
            rate = np.where(slant_range > 0.0, np.einsum("...i,...i->...", relative, velocity) / slant_range, 0.0)
        return (-11.5e9 * rate / 299792.458).reshape(self.size), elevation.reshape(self.size)


def checked_ports(original):
    from leo.analysis.research import continuous_curve_fit as phase
    from leo.sky import frames

    if (sha256(Path(frames.__file__).read_bytes()).hexdigest() != FRAME_PIN
            or getattr(phase.phase_frequency_from_states, "__module__", None) != phase.__name__
            or phase.look_angles is not frames.look_angles
            or phase.geodetic_to_ecef_km is not frames.geodetic_to_ecef_km
            or phase.ecef_to_enu_matrix is not frames.ecef_to_enu_matrix):
        raise ValueError("Unsupported original Doppler and elevation projection bindings")
    return exact_port(original), exact_port(original, prepare=FineDopplerElevation)


def compare(original, prepared, projected, audit):
    """Rotate the treatment order, return the original answer and fail on drift."""
    operations = dict(zip(KINDS, (original, prepared, projected), strict=True))

    def run(stock, counts, kernel, scan, track, *operands):
        offset = len(audit) % len(KINDS)
        order = KINDS[offset:] + KINDS[:offset]
        results, clocks, work = {}, {}, {}
        for name in order:
            counter = Counter()
            started_wall, started_cpu = perf_counter_ns(), process_time_ns()
            results[name] = operations[name](stock, counter, kernel, scan, track, *operands)
            clocks[name] = dict(cpu_ns=process_time_ns() - started_cpu, wall_ns=perf_counter_ns() - started_wall)
            work[name] = dict(counter)
        result = results["ordinary"]
        gates = ("support_trials", "interval_rejected", "dominated", "profile_calls", "noise_calls", "fine_replays")
        if any(results[name] != result or any(work[name].get(g, 0) != work["ordinary"].get(g, 0) for g in gates)
               for name in KINDS[1:]):
            raise ShadowMismatch(f"Fine-salvage result or certificate drift for {track['key']}")
        counts.update(work["ordinary"])
        audit.append(dict(track=track["key"], order=order, clocks=clocks, counters=work,
                          supports=result[1], alternatives=len(result[0])))
        return result

    return run


@contextmanager
def binding(*, audit=None):
    import certified_salvage

    original = certified_salvage.fine_alternatives
    try:
        prepared, projected = checked_ports(original)
    except (OSError, ValueError):
        if audit is not None:
            raise
        yield False
        return
    with patch.object(certified_salvage, "fine_alternatives",
                      projected if audit is None else compare(original, prepared, projected, audit)):
        yield True
