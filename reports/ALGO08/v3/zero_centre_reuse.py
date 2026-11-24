"""Reuse the zero centre from the rejected scout rank on one identical scan."""

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import fields, is_dataclass
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

import two_centre_seeds as seeds


BEFORE = "    for number, beta in enumerate(proposals):\n        state = zero_state(scan)\n"
AFTER = "    return candidates\n"
BYTE_LIMIT = 96 * 1024**2


class StateStamp:
    """Compare mutable numeric inputs as bytes, including strides and signed zeros."""

    def __init__(self):
        self.digest = sha256()
        self.bytes = 0

    def add(self, value, depth=0):
        if depth > 16:
            raise ValueError("Unsupported nested scan state")
        type_ = type(value)
        self.digest.update(f"{type_.__module__}.{type_.__qualname__}\0".encode())
        if isinstance(value, (np.ndarray, np.generic, float)):
            array = np.asarray(value)
            if array.dtype.hasobject or self.bytes + array.nbytes > BYTE_LIMIT:
                raise ValueError("Unsupported or oversized scan array")
            self.digest.update(repr((array.dtype.str, array.shape, array.strides)).encode())
            flat = array.ravel(order="K")
            self.digest.update(memoryview(flat).cast("B"))
            self.bytes += array.nbytes
        elif type_ in (tuple, list, dict) or is_dataclass(value):
            if type_ is dict:
                value = list(value.items())
            elif is_dataclass(value):
                value = [(item.name, getattr(value, item.name)) for item in fields(value)]
            self.digest.update(str(len(value)).encode()+b":")
            for item in value:
                self.add(item, depth + 1)
        elif type_ in (str, int, bool, type(None)):
            self.digest.update(repr(value).encode()+b"\0")
        else:
            raise ValueError(f"Unsupported scan input {type_.__name__}")


class ZeroCentre:
    def __init__(self, scan, audit):
        self.scan = scan
        self.audit = audit
        self.key = None
        self.node = None
        self.scouting = False

    def stamp(self, scan, sigma, beta, base):
        from leo.analysis.localization_v3.scan import ScanLikelihood
        from leo.analysis.localization_v4.native_bound import NativeBound

        if scan is not self.scan or type(scan) is not ScanLikelihood or type(scan.bound) is not NativeBound or beta.any():
            return None
        start = process_time_ns()
        try:
            # The active whole-bound object's LRU contains symbolic layouts.
            # No numerical input or fitted value is cached there.
            bound = scan.bound
            numerical = {k: v for k, v in vars(scan).items() if k not in ("association", "bound", "geometry")}
            geometry = scan.geometry
            if (not is_dataclass(geometry) or any(
                array.flags.writeable or not array.flags.owndata
                for array in (geometry.positions, geometry.velocities, geometry.index, geometry.fraction, geometry.rotation)
            )):
                return None
            state = StateStamp()
            state.add((numerical, sigma, beta, base, bound.manifest, bound.min_rcond,
                       bound.cache_entries, bound.provider_info))
            self.audit["guard_bytes"] += state.bytes
            return state.digest.digest(), geometry, bound, bound.original
        except (AttributeError, BufferError, TypeError, ValueError) as exc:
            self.audit["guard_fallback"] = str(exc)
            return None
        finally:
            self.audit["guard_cpu_ns"] += process_time_ns()-start

    def lookup(self, key):
        if key is None or self.key is None or self.scouting:
            return None
        if key[0] != self.key[0] or any(a is not b for a, b in zip(key[1:], self.key[1:], strict=True)):
            self.audit["guard_misses"] += 1
            return None
        start = process_time_ns()
        result = deepcopy(self.node)
        self.audit["copy_cpu_ns"] += process_time_ns()-start
        self.audit["reused"] += 1
        self.key = self.node = None
        return result

    def save(self, key, node, started):
        if key is None or not self.scouting:
            return
        self.audit["original_zero_cpu_ns"] += process_time_ns()-started
        start = process_time_ns()
        self.key, self.node = key, deepcopy(node)
        self.audit["copy_cpu_ns"] += process_time_ns()-start

    def instrument(self, source):
        if source.count(BEFORE) != 1 or source.count(AFTER) != 1:
            raise ValueError("The installed zero calibration boundary changed")
        entry = """    for number, beta in enumerate(proposals):
        if number == 0:
            stamp = _stamp(scan, sigma, beta, base)
            reused = _lookup(stamp)
            if reused is not None:
                candidates.append(reused)
                continue
            started = _clock()
        state = zero_state(scan)
"""
        finish = """        if number == 0:
            _save(stamp, candidates[-1], started)
    return candidates
"""
        return source.replace(BEFORE, entry).replace(AFTER, finish), dict(
            _stamp=self.stamp, _lookup=self.lookup, _save=self.save, _clock=process_time_ns)

    @contextmanager
    def ordinary(self, discovery):
        original = discovery.fresh_discovery
        source, bindings = self.instrument(getsource(original))
        namespace = dict(original.__globals__, **bindings)
        exec(compile(source, original.__code__.co_filename, "exec"), namespace)
        with patch.object(discovery, "fresh_discovery", namespace["fresh_discovery"]):
            yield


@contextmanager
def zero_centre_reuse():
    """Keep the original guard, ranking and named checkpoint decisions."""
    import combined_successor as combined
    from leo.analysis.localization_v3 import discovery

    original = combined.SuccessorHandoff

    class ReusedZero(original):
        def rank(self, scan):
            if scan is not self.scan or self.scout:
                return super().rank(scan)
            source = Path(discovery.fresh_discovery.__code__.co_filename)
            if sha256(source.read_bytes()).hexdigest() != seeds.DISCOVERY_SHA256:
                return super().rank(scan)
            memo = ZeroCentre(scan, Counter())
            exact_rank = self.exact_rank

            @contextmanager
            def nominate(audit):
                memo.scouting = True
                try:
                    with seeds.two_seeds(audit, instrument=memo.instrument):
                        yield
                finally:
                    memo.scouting = False

            def exact(current):
                if memo.scouting or memo.key is None or current is not scan:
                    return exact_rank(current)
                with memo.ordinary(discovery):
                    return exact_rank(current)

            with patch.object(combined, "two_seeds", nominate), patch.object(self, "exact_rank", exact):
                result = super().rank(scan)
            self.scout["zero_centre"] = dict(memo.audit)
            return result

    with patch.object(combined, "SuccessorHandoff", ReusedZero):
        yield
