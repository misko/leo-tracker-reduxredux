"""Reuse white-noise curve work arrays within all-catalogue discovery."""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import numpy as np

from leo.analysis.research.retained_track_likelihood import BIAS, NOISE, PERIOD


class DenseWhiteProfile:
    """Use a private workspace and remember the scan's immutable whitening matrices."""

    def __init__(self, original, *, scratch_bytes=16 * 1024**2):
        self.original = original
        self.maximum_values = scratch_bytes // np.dtype(float).itemsize
        self.buffer = np.empty(0)
        self.whitening = {}
        self.calls = self.cells = 0

    def __call__(self, observed, predicted, inverse, logvolume=0.0, *, bias_sigma=BIAS):
        y, f, w = np.asarray(observed), np.atleast_2d(predicted), np.asarray(inverse)
        if (
            y.dtype != np.float64 or f.dtype != np.float64 or w.dtype != np.float64
            or y.ndim != 1 or f.ndim != 2 or f.shape[1] != len(y)
            or w.shape != (len(y), len(y)) or f.size > self.maximum_values
            or not np.isfinite(bias_sigma) or bias_sigma <= 0
        ):
            return self.original(observed, predicted, inverse, logvolume, bias_sigma=bias_sigma)

        prepared = self.whitening.get(id(w))
        if prepared is None:
            one = np.diag(w)
            if np.count_nonzero(w) != len(y) or np.count_nonzero(one) != len(y):
                return self.original(observed, predicted, inverse, logvolume, bias_sigma=bias_sigma)
            prepared = w, one, one @ one
            self.whitening[id(w)] = prepared
        _, one, information = prepared

        # The dense bias product makes the stock innovation matrix C ordered.
        # The residual from a column broadcast keeps the original raw layout.
        raw = y - f
        alias = np.rint(-raw.mean(axis=1) / PERIOD)
        raw += alias[:, None] * PERIOD
        z = raw * one
        bias = z @ one / (information + 1 / bias_sigma**2)
        if self.buffer.size < raw.size:
            self.buffer = np.empty(raw.size)
        work = self.buffer[:raw.size].reshape(raw.shape)
        np.multiply(bias[:, None], one, out=work)
        innovations = z if z.flags.c_contiguous else np.empty(raw.shape)
        np.subtract(z, work, out=innovations)
        np.square(innovations, out=work)
        cost = np.sum(work, axis=1) + (bias / bias_sigma) ** 2
        cost += logvolume + np.log1p(bias_sigma**2 * information)
        np.subtract(raw, bias[:, None], out=raw)
        order = "F" if raw.flags.f_contiguous else "C"
        residual_work = self.buffer[:raw.size].reshape(raw.shape, order=order)
        np.square(raw, out=residual_work)
        rms = np.sqrt(np.mean(residual_work, axis=1))
        innovations *= NOISE
        self.calls += 1
        self.cells += raw.size
        return dict(alias=alias, bias=bias, residual=raw, innovations=innovations, rms=rms, cost=cost)


@contextmanager
def dense_discovery(scan, *, use_scratch=False, reuse_associations=False):
    """Apply the two controls independently for one complete initial ranking."""
    from leo.analysis.localization_v3 import discovery, scan as scan_module

    counts = dict(association_reused=0)
    profile = DenseWhiteProfile(scan_module.profile)
    explore = discovery.explore

    def exploration(current, *args, **kwargs):
        if current is not scan:
            return explore(current, *args, **kwargs)
        association = scan.association
        previous = None

        def associate(state, base, point, method, **options):
            nonlocal previous
            if options or method not in ("shared_phase", "receiver_smooth") or state.get("extra"):
                return association(state, base, point, method, **options)
            key = tuple(point), method
            if previous and state is previous[0] and base is previous[1] and key == previous[2]:
                counts["association_reused"] += 1
                return previous[3]
            result = association(state, base, point, method)
            previous = state, base, key, result
            return result

        with patch.object(scan, "association", associate):
            return explore(current, *args, **kwargs)

    with ExitStack() as stack:
        if use_scratch:
            stack.enter_context(patch.object(scan_module, "profile", profile))
        if reuse_associations:
            stack.enter_context(patch.object(discovery, "explore", exploration))
        yield counts
    counts.update(profile_calls=profile.calls, profile_cells=profile.cells,
                  scratch_bytes=profile.buffer.nbytes)
