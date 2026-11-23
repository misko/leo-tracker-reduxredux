"""Score the released geographic mixture after the whole-track horizon test."""

from collections import Counter
from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from unittest.mock import patch

import numpy as np


PIN = "6e7ae57a5762be3028756e3033c070de587c461707dda059692aee5d7c717b96"
PROJECTOR_PIN = "c21c07ec7b5ee206290e8578d4cbd46dcd85fe7cfd742dafb38a70d8a112529e"


class VisibleProjection:
    """Keep all ranges checked, but evaluate Doppler only for eligible tracks."""

    def __init__(self, geometry, latitude, longitude, kernel, counts):
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Geodetic coordinate outside domain")
        self.geometry, self.kernel, self.counts = geometry, kernel, counts
        base = self.base = geometry.geometry
        observer = self.observer = kernel.geodetic_to_ecef_km(latitude, longitude, 0.)
        up = kernel.ecef_to_enu_matrix(latitude, longitude)[2]
        self.distance = np.sqrt(base.position_norm_squared
                                - 2 * np.einsum("snj,j->sn", base.position_km, observer)
                                + observer @ observer)
        if np.any(self.distance <= 0) or not np.isfinite(self.distance).all():
            raise ValueError("Positive finite satellite ranges required")
        vertical = np.einsum("snj,j->sn", base.position_km, up) - observer @ up
        # For a finite positive range, the original clipped arcsine and degree
        # conversion preserve this sign, including equality at the horizon.
        self.visible = vertical / self.distance >= 0
        counts["full_projection_cells"] += self.distance.size

    def score(self, observed, indices, q, labels, catalogue_size):
        visible = np.flatnonzero(self.visible[:, indices].all(axis=1))
        self.counts["track_trials"] += 1
        if not len(visible) or len(observed) < 2:
            return 0., None
        cells = visible[:, None], indices
        self.counts["track_projection_cells"] += len(visible) * len(indices)
        base, geometry, observer = self.base, self.geometry, self.observer
        distance = self.distance[cells]
        numerator = base.position_dot_velocity[cells] - np.einsum("snj,j->sn", base.velocity_km_s[cells], observer)
        derivative_numerator = (geometry.numerator_derivative[cells]
                                - np.einsum("snj,j->sn", geometry.velocity_derivative[cells], observer))
        derivative_range = (geometry.position_dot_derivative[cells]
                            - np.einsum("snj,j->sn", geometry.position_derivative[cells], observer))
        rate = numerator / distance
        derivative = derivative_numerator / distance - numerator * derivative_range / distance**3
        ratios = self.kernel.contrast_log_ratio(observed, q * (-11.5e9 * rate / 299792.458),
                                                q * (-11.5e9 * derivative / 299792.458))
        log_odds = np.logaddexp.reduce(ratios) - np.log(catalogue_size)
        owner = int(labels[visible][np.argmax(ratios)]) if log_odds > 0 else None
        return float(np.logaddexp(0, log_odds)), owner


def source_binding(kernel, stock, counts):
    source = getsource(stock)
    start = '            frequency, elevation, derivative = phase_linear_frequency(geometry, *point["latlon"])\n'
    end = '        point.update(score='
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError("Unreviewed regional score boundary")
    begin, finish = source.index(start), source.index(end)
    dense = "\n".join("    " + line for line in source[begin:finish].splitlines())
    sparse = '''            try:
                project = _project(geometry, *point["latlon"], _kernel, _counts)
                for track, indices in zip(tracks, indexes, strict=True):
                    q = track["rf_hz"] / 11.5e9
                    score, owner = project.score(track["values"], indices, q, labels, catalogue_size)
                    sums[track["receiver"]] += score
                    owners[track["key"]] = owner
                _counts["sparse_probes"] += 1
            except (ValueError, ArithmeticError):
                _counts["dense_fallback_probes"] += 1
                sums = dict.fromkeys(groups, 0.)
                owners = dict.fromkeys(t["key"] for t in tracks)
'''
    namespace = dict(stock.__globals__, _kernel=kernel, _project=VisibleProjection, _counts=counts)
    exec(compile(source[:begin] + sparse + dense + "\n" + source[finish:], stock.__code__.co_filename, "exec"), namespace)
    return namespace[stock.__name__]


@contextmanager
def visible_proof():
    """Bind only the pinned released scorer in a saved research process."""
    from tools.pipeline_eval.variants.experimental import regional_reassignment as kernel

    stock = kernel._prepare_probe_scores
    counts = Counter()
    projector_source = kernel.phase_linear_frequency.__code__.co_filename
    if (sha256(Path(kernel.__file__).read_bytes()).hexdigest() != PIN
            or sha256(Path(projector_source).read_bytes()).hexdigest() != PROJECTOR_PIN):
        counts["unsupported_kernel"] += 1
        yield counts
        return
    with patch.object(kernel, "_prepare_probe_scores", source_binding(kernel, stock, counts)):
        yield counts
