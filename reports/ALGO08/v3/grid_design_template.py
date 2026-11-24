"""Fill a private frozen selected-view design in the original row order."""

from collections import Counter
from contextlib import contextmanager
import ctypes as ct
from inspect import getsource
from pathlib import Path
import subprocess
from unittest.mock import patch

import numpy as np

from grid_feature_projection import FLAGS, contiguous, exact


def build(path):
    subprocess.run(["cc", *FLAGS, str(Path(__file__).with_suffix(".c")), "-o", str(path)],
                   check=True, timeout=15)


class Designs:
    def __init__(self, library):
        self.fill = ct.CDLL(str(library)).grid_design_template
        self.fill.argtypes = [ct.c_size_t, ct.c_size_t] + [ct.c_void_p] * 8
        self.fill.restype = None
        self.counts = Counter()

    @contextmanager
    def binding(self, scope):
        ordinary = scope["_assemble"]
        # Do not apply the stencil to an unrecognized source replacement.
        if "result = (direct_features(problem, derivative, modes, scales) if use_direct" not in getsource(ordinary):
            self.counts["assembly_binding_fallbacks"] += 1
            yield
            return
        views = {}

        def created(problem, frequency, derivative, modes, scales):
            labels = problem.flat_labels
            phase = np.ascontiguousarray(problem.hardware.shape[1] + problem.smooth.shape[1] + labels,
                                         dtype=np.intp)
            columns = np.full(len(problem.labels), -1, dtype=np.intp)
            for index, label in enumerate(problem.supported_local):
                columns[label] = problem.hardware.shape[1] + problem.smooth.shape[1] + len(columns) + 3 * index
            orbit = columns[labels]
            fixed = ordinary(problem, frequency, np.zeros_like(derivative), np.zeros_like(modes), scales, True)
            if (fixed.ndim != 2 or not contiguous(fixed, fixed.shape) or not fixed.shape[0] == len(labels)
                    or not np.all((0 <= phase) & (phase < fixed.shape[1]))
                    or not np.all((orbit == -1) | ((0 <= orbit) & (orbit + 2 < fixed.shape[1])))):
                return None
            self.counts["template_bytes"] += fixed.nbytes + phase.nbytes + orbit.nbytes
            return fixed, phase, orbit, problem.q, np.ascontiguousarray(problem.phase_sigma[labels])

        def assemble(problem, frequency, derivative, modes, scales, geometry_only):
            n = len(derivative)
            if (not geometry_only or problem.variant != "radio_noise" or len(scales) != 3
                    or not np.all(scales == 1.) or not contiguous(derivative, (n,))
                    or not contiguous(modes, (n, 3)) or not contiguous(problem.q, (n,))
                    or not contiguous(problem.flat_labels, (n,), np.intp)):
                self.counts["assembly_layout_fallbacks"] += 1
                return ordinary(problem, frequency, derivative, modes, scales, geometry_only)
            key = id(problem)
            view = views.get(key)
            operands = (problem.hardware, problem.smooth, problem.constants, problem.flat_labels,
                        problem.phase_sigma, problem.q)
            first = view is None
            if first:
                view = (problem, operands, created(problem, frequency, derivative, modes, scales))
                views[key] = view
            if (view[2] is None or not all(a is b for a, b in zip(operands, view[1], strict=True))):
                self.counts["assembly_view_fallbacks"] += 1
                return ordinary(problem, frequency, derivative, modes, scales, geometry_only)
            fixed, *_ = view[2]
            result = np.empty_like(fixed)
            self.fill(*fixed.shape, *(a.ctypes.data for a in (*view[2], derivative, modes, result)))
            if first:
                reference = ordinary(problem, frequency, derivative, modes, scales, True)
                if not exact(reference, result):
                    self.counts["assembly_exact_fallbacks"] += 1
                    views[key] = (problem, operands, None)
                    return reference
                self.counts["assembly_exact_checks"] += 1
            self.counts["assembly_calls"] += 1
            return result

        with patch.dict(scope, _assemble=assemble):
            yield
