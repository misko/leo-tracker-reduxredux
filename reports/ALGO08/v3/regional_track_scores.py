"""Score all regional tracks directly on the original projected orbit arrays."""

from ctypes import CDLL, c_double, c_int, c_size_t, c_void_p
from inspect import getclosurevars

import numpy as np


class TrackScores:
    def __init__(self, library, scorer):
        state = getclosurevars(scorer).nonlocals
        self.geometry = state["geometry"]
        self.labels = np.asarray(state["labels"])
        self.index = np.ascontiguousarray(np.concatenate(state["indexes"]), dtype=np.int64)
        self.tracks = state["tracks"]
        self.counts = state["counts"]
        self.groups = state["groups"]
        self.total = len(state["rows"])
        self.catalogue = state["catalogue_size"]
        self.original = scorer
        sizes = np.asarray([len(t["values"]) for t in self.tracks])
        self.offset = np.r_[np.int64(0), np.cumsum(sizes, dtype=np.int64)]
        self.observed = np.ascontiguousarray(np.concatenate([t["values"] for t in self.tracks]), dtype=np.float64)
        self.scale = np.asarray([t["rf_hz"] / 11.5e9 for t in self.tracks], dtype=np.float64)
        from leo.analysis.research.retained_track_likelihood import NOISE, PERIOD

        self.noise = NOISE
        self.base = (sizes - 1) * np.log(PERIOD / (np.sqrt(2 * np.pi) * NOISE)) - .5 * np.log(sizes)
        if (self.observed.ndim != 1 or self.index.ndim != 1 or self.labels.ndim != 1 or np.any(sizes < 1)
                or any(len(ix) != n for ix, n in zip(state["indexes"], sizes, strict=True))
                or self.index.min() < 0 or self.catalogue < 1):
            raise ValueError("Invalid track projection input")
        self.last = self.index.max()
        self.raw, self.phase = np.empty(sizes.max()), np.empty(sizes.max())
        self.score = np.empty(len(sizes))
        self.owner = np.empty(len(sizes), dtype=np.int64)
        self.lib = CDLL(str(library))
        self.call = self.lib.regional_track_scores
        self.call.argtypes = [c_size_t] * 3 + [c_void_p] * 8 + [c_double] * 2 + [c_void_p] * 4
        self.call.restype = c_int
        self.native = self.fallbacks = 0

    def __call__(self, point):
        from tools.pipeline_eval.variants.experimental import regional_reassignment as kernel

        if self.geometry is not None:
            f, h, d = kernel.phase_linear_frequency(self.geometry, *point["latlon"])
            if (f.ndim == 2 and f.shape == h.shape == d.shape and f.shape[0] == len(self.labels)
                    and self.last < f.shape[1] and f.dtype == d.dtype == np.float64 and h.dtype == np.int8
                    and all(a.flags.c_contiguous and a.flags.aligned for a in (f, h, d))):
                arrays = (self.offset, self.index, self.observed, self.scale, self.base, f, h, d)
                result = self.call(len(self.tracks), *f.shape, *(a.ctypes.data for a in arrays),
                                   self.noise, np.log(self.catalogue),
                                   *(a.ctypes.data for a in (self.raw, self.phase, self.score, self.owner)))
                if result == 0:
                    self.native += 1
                    sums = dict.fromkeys(self.groups, 0.)
                    owners = {}
                    for track, score, owner in zip(self.tracks, self.score, self.owner, strict=True):
                        sums[track["receiver"]] += float(score)
                        owners[track["key"]] = None if owner < 0 else int(self.labels[owner])
                    point.update(score=sum(sums.values()) / self.total, owners=owners,
                                 receiver_scores={str(r): sums[r] / self.counts[r] for r in self.groups})
                    return point
        self.fallbacks += 1
        return self.original(point)
