"""Feed released cold associations the existing full-catalogue centre track rows."""

from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from textwrap import dedent
from types import MethodType
from unittest.mock import patch

import numpy as np


SCAN_PIN = "49f1f2e9d73b967f694e48033b6d02ea2e1d66285f7941c4f282f5b238e79f89"
SPARSE_PIN = "e381e0807e47a10091ffd9c9d1d8c0d43aa531a5e4c81acda53ddbfa922ef021"
SHARING_PIN = "321df8d3771fd478543e7c161a4b1c7d1a84734c8c4a0ae2768ebdf1c9038831"


def reused_rows(frequency, elevation, indices, scale, nominal, visible, work):
    """Preserve F-order predictions and full row numbering for the released likelihood."""
    changed = frequency.changed_rows
    if not len(changed):
        return nominal, visible
    predictions = nominal.copy(order="F")
    visibility = visible.copy()
    predictions[changed] = scale * frequency.values[:, indices]
    visibility[changed] = elevation.values[:, indices].min(axis=1) >= 0
    work["copy_bytes"] += predictions.nbytes + visibility.nbytes
    work["shifted_cells"] += len(changed) * len(indices)
    return predictions, visibility


class CentreRows:
    def __init__(self, tables, projected, work):
        self.tables = tables
        self.projected = projected
        self.work = work

    def __call__(self, track, indices, frequency, elevation):
        scale = track["rf_hz"] / 11.5e9
        tables = self.tables
        cached = tables.tracks.get(track["key"])
        if (cached is None or tables.current is None or tables.current is not tables.nominal
                or cached[0] is not track["times"] or cached[1] != scale
                or type(frequency) is not self.projected or type(elevation) is not self.projected
                or frequency.materialized is not None or elevation.materialized is not None
                or frequency.base is not tables.nominal[0] or elevation.base is not tables.nominal[1]
                or frequency.changed_rows is not elevation.changed_rows):
            self.work["released_requests"] += 1
            return scale * frequency[:, indices], elevation[:, indices].min(axis=1) >= 0
        nominal, visible = cached[2][:2]
        if nominal.shape != (frequency.base.shape[0], len(indices)) or not nominal.flags.f_contiguous:
            self.work["released_requests"] += 1
            return scale * frequency[:, indices], elevation[:, indices].min(axis=1) >= 0
        self.work["reused_requests"] += 1
        self.work["reused_nominal_cells"] += nominal.size
        return reused_rows(frequency, elevation, indices, scale, nominal, visible, self.work)


def associate_with_rows(original, rows):
    """Change only the two track gathers in the pinned released association."""
    source = getsource(original)
    old = ('            terms = self.curve(i, y, t["rf_hz"] / 11.5e9 * f[:, ix], method)\n'
           '            visible = e[:, ix].min(axis=1) >= 0\n')
    new = ('            predictions, visible = _rows(t, ix, f, e)\n'
           '            terms = self.curve(i, y, predictions, method)\n')
    if source.count(old) != 1:
        raise ValueError("The released association gather changed")
    namespace = dict(original.__globals__, _rows=rows)
    exec(compile(dedent(source.replace(old, new)), original.__code__.co_filename, "exec"), namespace)
    return namespace[original.__name__]


@contextmanager
def shared_association_rows(scan, tables, work):
    from leo.analysis.localization_v3 import scan as kernel
    from tools.pipeline_eval.variants import algo08_sparse_rank_projection as sparse

    association = scan.association
    pins = ((association.__code__.co_filename, SCAN_PIN), (sparse.__file__, SPARSE_PIN),
            (tables.projection.__code__.co_filename, SHARING_PIN))
    if (getattr(association, "__func__", None) is not kernel.ScanLikelihood.association
            or any(sha256(Path(path).read_bytes()).hexdigest() != pin for path, pin in pins)):
        raise ValueError("Unexpected association, projection or centre-cache binding")
    operation = associate_with_rows(association.__func__, CentreRows(tables, sparse.ProjectedRows, work))
    with patch.object(scan, "association", MethodType(operation, scan)):
        yield
