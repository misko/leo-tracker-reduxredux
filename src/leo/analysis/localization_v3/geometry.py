"""Scan-owned exact phase-geometry reuse over a privately frozen orbit bank.

No rounded keys, approximation, cross-scan cache or historical worker inputs.
The first query retains the original arithmetic; repeated identical queries
reuse immutable arrays. Receiver position is applied by the likelihood later.
"""
from collections import OrderedDict
from dataclasses import fields, replace

import numpy as np

from leo.analysis.research.phase_linear_geometry import prepare_phase_geometry
from leo.analysis.research.track_catalogue_geometry import interpolate_states


def _frozen(array):
    value = np.asarray(array)
    if value.dtype.hasobject:
        raise ValueError('Numeric arrays required for immutable geometry')
    return np.frombuffer(value.tobytes(order='C'), dtype=value.dtype).reshape(value.shape)


def _key(array):
    return array.dtype.str, array.shape, array.tobytes(order='C')


def _freeze_result(value):
    converted = {}
    size = 0
    for field in fields(value):
        original = getattr(value, field.name)
        if isinstance(original, np.ndarray):
            converted[field.name] = _frozen(original)
            size += original.nbytes
        else:
            converted[field.name], nested_size = _freeze_result(original)
            size += nested_size
    return replace(value, **converted), size


class ScanGeometry:
    """Bounded derived-array cache; one owner per scan and no concurrent writers."""

    def __init__(self, bank, *, maximum_cache_bytes=256 * 1024 * 1024):
        if type(maximum_cache_bytes) is not int or maximum_cache_bytes < 0:
            raise ValueError('Nonnegative integer cache byte limit required')
        self._bank = {name: _frozen(np.asarray(bank[name], float))
                      for name in ('time_s', 'position_km', 'velocity_km_s')}
        interpolate_states(self._bank, np.array([], float))
        self.maximum_cache_bytes = maximum_cache_bytes
        self.bank_bytes = sum(a.nbytes for a in self._bank.values())
        self._cache = OrderedDict()
        self.cached_bytes = self.hits = self.misses = 0

    def prepare(self, times, phases=0.0, *, derivative_step_s=0.05):
        # Private snapshots bind the key to precisely what is evaluated, including
        # float32 versus float64 phase arithmetic and the derivative-step type.
        times, phases = _frozen(times), _frozen(phases)
        step = np.asarray(derivative_step_s)
        if step.ndim != 0 or not np.isfinite(step) or step <= 0:
            raise ValueError('Positive finite scalar phase difference step required')
        key = (_key(times), _key(phases), _key(step), type(derivative_step_s))
        if key in self._cache:
            self.hits += 1
            result, _ = self._cache[key]
            self._cache.move_to_end(key)
            return result
        self.misses += 1
        result = prepare_phase_geometry(self._bank, times, phases,
                                        derivative_step_s=derivative_step_s)
        result, size = _freeze_result(result)
        size += sum(len(part[2]) for part in key[:3])
        if size <= self.maximum_cache_bytes:
            while self.cached_bytes + size > self.maximum_cache_bytes:
                _, (_, removed) = self._cache.popitem(last=False)
                self.cached_bytes -= removed
            self._cache[key] = result, size
            self.cached_bytes += size
        return result
