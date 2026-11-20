"""Project and audit the complete causal recovery sky bank in bounded row blocks."""

import json
import os
import sys
from contextlib import ExitStack, contextmanager
from functools import partial
from hashlib import sha256
from operator import index
from pathlib import Path
from tempfile import TemporaryFile
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.__main__ import local_output, save_json
from tools.pipeline_eval.variants import orbit_projector, v5_armijo_aligned_finish, v5_lean

METHOD = "v5_stream_recovery"
BOUNDARY = "Complete native GLRT through paired compact v5 recovery with bounded causal orbit rows"
BLOCK = 128


class OrbitRows:
    """Float64 state rows on an unlinked file with bounded, independent reads."""

    def __init__(self, file, knots):
        self.file = file
        self.knots = knots
        self.count = 0
        self.finite = True
        self.digest = sha256()

    @property
    def shape(self):
        return (self.count, self.knots, 3)

    @property
    def nbytes(self):
        return self.count * self.row_bytes

    @property
    def row_bytes(self):
        return self.knots * 3 * 8

    def append(self, values):
        array = np.ascontiguousarray(values, dtype=np.float64)
        if array.ndim != 3 or array.shape[1:] != self.shape[1:]:
            raise ValueError("invalid orbit state block shape")
        if len(array) == 0:
            return
        self.finite &= bool(np.isfinite(array).all())
        raw = memoryview(array).cast("B")
        if self.file.write(raw) != raw.nbytes:
            raise OSError("short orbit scratch write")
        self.digest.update(raw)
        self.count += len(array)

    def __getitem__(self, item):
        scalar = not isinstance(item, slice)
        if scalar:
            start = index(item)
            if start < 0:
                start += self.count
            if not 0 <= start < self.count:
                raise IndexError("orbit row outside bank")
            stop = start + 1
        else:
            start, stop, step = item.indices(self.count)
            if step != 1:
                raise ValueError("orbit bank requires a contiguous row range")
        amount = max(0, stop - start)
        if amount > BLOCK:
            raise ValueError("orbit bank read exceeds bounded row block")
        raw = os.pread(self.file.fileno(), amount * self.row_bytes, start * self.row_bytes)
        if len(raw) != amount * self.row_bytes:
            raise OSError("short orbit scratch read")
        values = np.frombuffer(raw, np.float64).reshape((amount, *self.shape[1:]))
        return values[0] if scalar else values


class EligibleRows:
    """Expose the exact eligibility selection the frozen producers perform."""

    def __init__(self, rows, eligible):
        self.rows, self.eligible = rows, eligible

    def __getitem__(self, mask):
        if mask is not self.eligible:
            raise ValueError("the streamed bank can only be filtered by its original usable mask")
        return self.rows


def new_components(stack, directory, knots):
    return tuple(
        OrbitRows(stack.enter_context(TemporaryFile("w+b", buffering=0, dir=directory)), knots)
        for _ in range(2)
    )


def receipt(position, velocity, usable=None):
    return dict(
        rows=position.count,
        knots=position.knots,
        scratch_bytes=position.nbytes + velocity.nbytes,
        position_sha256=position.digest.hexdigest(),
        velocity_sha256=velocity.digest.hexdigest(),
        usable_sha256=sha256(usable).hexdigest() if usable is not None else None,
    )


def stream_states(original, stack, directory, events, catalogue, origin, times):
    position, velocity = new_components(stack, directory, len(times))
    good = np.empty(len(catalogue), dtype=bool)
    for start in range(0, len(catalogue), BLOCK):
        sl = slice(start, start + BLOCK)
        subset = type(catalogue)(
            catalogue.names[sl], catalogue.satellite_numbers[sl], catalogue.satellites[sl]
        )
        p, v, usable = original(subset, origin, times)
        position.append(p[usable])
        velocity.append(v[usable])
        good[sl] = usable
    events.append(receipt(position, velocity, good))
    return EligibleRows(position, good), EligibleRows(velocity, good), good


def stream_audit(original, stack, directory, events, satellites):
    class Audit:
        def sgp4(self, jd, fraction):
            position, velocity = new_components(stack, directory, len(jd))
            codes = []
            for start in range(0, len(satellites), BLOCK):
                error, p, v = original(satellites[start : start + BLOCK]).sgp4(jd, fraction)
                codes.append(error)
                position.append(p)
                velocity.append(v)
            events.append(receipt(position, velocity))
            return np.concatenate(codes), position, velocity

    return Audit() if satellites else original(satellites)


def project_rows(original, events, bank, time, positions, **kwargs):
    source = bank["position_km"]
    if not isinstance(source, OrbitRows):
        return original(bank, time, positions, **kwargs)
    receivers = tuple(positions)
    velocity = bank["velocity_km_s"]
    shape = (source.count, len(time))
    outputs = [(np.empty(shape), np.empty(shape)) for _ in receivers]
    for start in range(0, max(1, source.count), BLOCK):
        sl = slice(start, start + BLOCK)
        subset = dict(time_s=bank["time_s"], position_km=source[sl], velocity_km_s=velocity[sl])
        values = original(subset, time, receivers, **kwargs)
        for (frequency, elevation), (f, e) in zip(outputs, values, strict=True):
            frequency[sl] = f
            elevation[sl] = e
    events["projected_grids"] += 1
    events["max_output_grid_bytes"] = max(
        events["max_output_grid_bytes"], sum(x.nbytes for pair in outputs for x in pair)
    )
    events["max_state_read_bytes"] = max(
        events["max_state_read_bytes"],
        min(BLOCK, source.count) * (source.row_bytes + velocity.row_bytes),
    )
    return outputs


@contextmanager
def streamed_recovery(directory):
    from leo.analysis.localization_v3 import (
        reassociation_admission,
        reassociation_catalogue,
        reassociation_screen,
        residual_screen,
    )

    from leo.analysis.research.track_catalogue_geometry import interpolate_states

    events = dict(
        ecef=[], audit=[], projected_grids=0, max_output_grid_bytes=0, max_state_read_bytes=0
    )
    original_freeze = residual_screen.FrozenOrbitBank

    def freeze(bank):
        p, v = bank["position_km"], bank["velocity_km_s"]
        if not isinstance(p, OrbitRows):
            return original_freeze(bank)
        if not (p.finite and v.finite):
            raise ValueError("finite orbital inputs required")
        interpolate_states(
            dict(time_s=bank["time_s"], position_km=p[:1], velocity_km_s=v[:1]), np.empty(0)
        )
        return bank

    def prepare(catalogue, scan_receipt):
        module = reassociation_catalogue
        ledger = catalogue["elements"]
        cutoff = scan_receipt["cutoff_utc_ns"]
        for record in ledger.values():
            age = (cutoff - record["element_epoch_utc_ns"]) / 3.6e12
            if not (0 <= age <= 72 and record["collected_utc_ns"] <= cutoff):
                raise ValueError("noncausal or too old catalogue")
        nums, bank, failures = module.bank_for(ledger, scan_receipt["origin_utc_ns"])
        propagation = module.audit(ledger, scan_receipt)
        eligible = (
            module.propagation_eligible(propagation, failures)
            and len(nums) + len(failures) == len(ledger)
            and bank["position_km"].finite
            and bank["velocity_km_s"].finite
        )
        return dict(
            ledger=ledger,
            nums=nums,
            bank=bank,
            failures=failures,
            propagation=propagation,
            eligible=bool(eligible),
        )

    with ExitStack() as stack:
        for module in (residual_screen, reassociation_catalogue):
            buffered = partial(stream_states, module.ecef_states, stack, directory, events["ecef"])
            stack.enter_context(patch.object(module, "ecef_states", buffered))
        for module in (residual_screen, reassociation_screen):
            buffered_projection = partial(project_rows, module.phase_frequency_grids, events)
            stack.enter_context(patch.object(module, "phase_frequency_grids", buffered_projection))
        stack.enter_context(patch.object(residual_screen, "FrozenOrbitBank", freeze))
        audit = partial(
            stream_audit, reassociation_catalogue.SatrecArray, stack, directory, events["audit"]
        )
        stack.enter_context(patch.object(reassociation_catalogue, "SatrecArray", audit))
        stack.enter_context(patch.object(reassociation_admission, "prepare_catalogue", prepare))
        yield events


def worker(request, result, library):
    with streamed_recovery(Path(result).parent) as metrics:
        v5_armijo_aligned_finish.worker(request, result, library)
    path = Path(result)
    value = json.loads(path.read_bytes())
    value["boundary"] = BOUNDARY
    value["metrics"]["bounded_recovery_rows"] = metrics
    save_json(path, value)


def run(case, work_dir):
    work_dir = local_output(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    library = work_dir / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    return v5_lean.run_bound_worker(case, work_dir, Path(__file__), worker_args=(str(library),))


if __name__ == "__main__":
    worker(*sys.argv[1:])
