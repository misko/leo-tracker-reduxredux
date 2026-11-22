"""Defer unused diagnostics inside the pinned deployed salvage loop."""

from contextlib import contextmanager
from functools import wraps
from hashlib import sha256
from pathlib import Path
from time import process_time
from unittest.mock import patch

import numpy as np

SALVAGE_SHA256 = "9d5047f873a22790c4f0818877b09270ee91a0761a9a3d7204c8a849639ee656"
PROFILE_SHA256 = "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf"


class ProfileRows:
    def __init__(self, fields, readout, fallback, counts):
        self.fields = fields
        self.readout = readout
        self.fallback = fallback
        self.counts = counts
        self.selected = None
        self.full = None

    def materialize(self):
        if self.full is None:
            start = process_time()
            self.full = self.fallback()
            self.counts["full_array_requests"] += 1
            self.counts["full_array_cpu_s"] += process_time() - start
        return self.full

    def row(self, name, index):
        if (name not in ("residual", "rms") or not self.fields["raw"].flags.c_contiguous
                or not (type(index) is int or isinstance(index, np.integer))):
            return self.materialize()[name][index]
        if self.selected is None or self.selected[0] != index:
            start = process_time()
            self.selected = index, self.readout(self.fields, index)
            self.counts["winning_rows"] += 1
            self.counts["winning_readout_cpu_s"] += process_time() - start
        return self.selected[1][name]


class DeferredDiagnostic:
    def __init__(self, rows, face):
        self.rows = rows
        self.face = face

    def __getitem__(self, index):
        return self.rows.row(self.face, index)

    def __array__(self, dtype=None, copy=None):
        return np.asarray(self.rows.materialize()[self.face], dtype=dtype, copy=copy)

    def __getattr__(self, name):
        return getattr(self.rows.materialize()[self.face], name)


@contextmanager
def defer_readout(score_rows, winning_readout):
    """Scope deferred fields to the released stock consumer and binary64 inputs."""
    from leo.analysis.localization_v3 import conservative_recovery as recovery
    from leo.analysis.research import retained_track_likelihood as likelihood

    stock, salvage = recovery.profile, recovery.salvage
    active = (stock is likelihood.profile and salvage.__module__ == recovery.__name__
              and sha256(Path(recovery.__file__).read_bytes()).hexdigest() == SALVAGE_SHA256
              and sha256(Path(likelihood.__file__).read_bytes()).hexdigest() == PROFILE_SHA256)
    counts = dict(enabled=active, salvage_cpu_s=0.0, score_cpu_s=0.0, profile_calls=0,
                  winning_rows=0, winning_readout_cpu_s=0.0, full_array_requests=0,
                  full_array_cpu_s=0.0, unsupported_profiles=0, trims=[])

    def evaluate(observed, predicted, inverse, *args, **kwargs):
        domains = ((observed, 1), (predicted, 2), (inverse, 2))
        if args or kwargs or any(type(a) is not np.ndarray or a.dtype != np.float64 or a.ndim != n
                                 for a, n in domains):
            counts["unsupported_profiles"] += 1
            return stock(observed, predicted, inverse, *args, **kwargs)
        start = process_time()
        fields = score_rows(observed, predicted, inverse)
        counts["profile_calls"] += 1
        counts["score_cpu_s"] += process_time() - start
        rows = ProfileRows(fields, winning_readout,
                           lambda: stock(observed, predicted, inverse), counts)
        return dict(
            {key: fields[key] for key in ("cost", "alias", "bias")},
            **{name: DeferredDiagnostic(rows, name) for name in ("rms", "residual", "innovations")},
        )

    @wraps(salvage)
    def patched_salvage(*args, **kwargs):
        start = process_time()
        with patch.object(recovery, "profile", evaluate):
            result = salvage(*args, **kwargs)
        counts["salvage_cpu_s"] += process_time() - start
        counts["trims"].extend(row for row in result[2] if row["selected"] is not None)
        return result

    if active:
        with patch.object(recovery, "salvage", patched_salvage):
            yield counts
    else:
        yield counts
