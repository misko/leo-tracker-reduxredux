"""Research port for the released normal bound's full, unit-scale design."""

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from hashlib import sha256
from inspect import getclosurevars
from pathlib import Path
from types import FunctionType
from unittest.mock import patch

import numpy as np

PINS = {
    "curved": "8b24f19af9f2e73ee54ca25c3432875ee25e06cd5c0ee260cbd696c6042c6ff4",
    "marginal": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609",
    "position": "c3507e6ecaba0adf6d3677f56d8056afcccbcf90d6a561bca7a42b06b0daef9d",
    "hierarchical": "c906a5992ca3428c29b5c44326264549e18dc4206653b3d6f2fd12b48638607e",
    "native": "fa7b67e0e539be9971ee1a530c2d1d941c7940701d40dae7cc6744cbc20de6a2",
    "native_source": "40888d6143f385c2146e5e2cb28ea99a96b2f1bb791fab4c22b5afaaa2b3a23b",
    "binary": "c649042b2a5ddf7890177d84b302a19edcf7a662aea16c18cb177317ccba818b",
}


def _select_full(features, scale, keep, ordinary, counts):
    if (
        type(features) is not np.ndarray
        or type(scale) is not np.ndarray
        or type(keep) is not np.ndarray
        or features.ndim != 2
        or not features.size
        or features.dtype != np.float64
        or not (features.flags.c_contiguous and features.flags.aligned)
        or keep.shape != (features.shape[0],)
        or keep.dtype != np.bool_
        or scale.shape != (features.shape[1],)
        or scale.dtype != np.float64
    ):
        counts["shape_fallbacks"] += 1
        return ordinary(features, scale, keep)
    counts["mask_entries_checked"] += keep.size
    if not keep.all():
        counts["mask_fallbacks"] += 1
        return ordinary(features, scale, keep)
    counts["scale_entries_checked"] += scale.size
    if not (scale == 1.0).all():
        counts["scale_fallbacks"] += 1
        return ordinary(features, scale, keep)

    result = features.view()
    result.setflags(write=False)
    counts["forwarded_calls"] += 1
    counts["design_copy_bytes_avoided"] += features.nbytes
    counts["unit_multiplies_avoided"] += features.size
    return result


@contextmanager
def borrowed_normal_design(owner):
    """Scope a read-only design operand to one audited installed native bound.

    Enter inside the released enabled curved-design context in an isolated
    single-solver process. The design is fresh and finite at this call site.
    A private view lives only through the synchronous read-only bound.
    """
    from leo.analysis.localization_v3 import hierarchical, marginal, position
    from leo.analysis.localization_v4 import native_bound
    from tools.pipeline_eval.variants import algo08_curved_design as curved

    counts = Counter()
    if type(owner) is not native_bound.NativeBound:
        counts["inactive_owner"] += 1
        yield counts
        return

    binary, library = owner.binary, owner.library
    bounded = native_bound.NativeBound.__call__
    validate, finish = native_bound._VALIDATE, native_bound._FINISH
    original = hierarchical.hierarchical_bound
    normal = position.NormalPosition.calculate
    joint = marginal.JointMarginal.calculate
    namespace = normal.__globals__ if isinstance(normal, FunctionType) else {}
    selector = namespace.get("_select")
    primitive = curved.selected_design
    functions = (normal, joint, selector, primitive, bounded, validate, finish, original)
    scopes = getclosurevars(selector).nonlocals if isinstance(selector, FunctionType) else {}
    sources = {
        "curved": curved.__file__, "marginal": marginal.__file__, "position": position.__file__,
        "hierarchical": hierarchical.__file__, "native": native_bound.__file__,
        "native_source": native_bound.SOURCE, "binary": binary,
    }
    if (
        not all(isinstance(function, FunctionType) for function in functions)
        or normal.__code__.co_filename != position.__file__
        or joint.__code__.co_filename != marginal.__file__
        or "_assemble" not in joint.__code__.co_names
        or selector.__code__.co_filename != curved.__file__
        or primitive.__code__.co_filename != curved.__file__
        or selector.__globals__ is not vars(curved)
        or scopes.get("method") != "normal"
        or scopes.get("enabled") is not True
        or bounded.__code__.co_filename != native_bound.__file__
        or validate.__code__.co_filename != "<native-bound-original-boundaries>"
        or finish.__code__.co_filename != "<native-bound-original-boundaries>"
        or original.__code__.co_filename != hierarchical.__file__
        or library._name != str(binary)
        or any(sha256(Path(path).read_bytes()).hexdigest() != PINS[key]
               for key, path in sources.items())
    ):
        counts["inactive_binding"] += 1
        yield counts
        return

    context = ContextVar("full_mask_normal_bound", default=False)

    @wraps(normal)
    def calculate(self, x):
        compatible = (
            self.scan.bound is owner
            and owner.binary is binary
            and owner.library is library
            and owner.original is original
            and type(owner).__call__ is bounded
            and native_bound._VALIDATE is validate
            and native_bound._FINISH is finish
            and marginal.JointMarginal.calculate is joint
            and owner.layout is library.nb_layout
            and owner.run is library.nb_run
        )
        if not compatible:
            counts["owner_fallbacks"] += 1
        token = context.set(compatible)
        try:
            return normal(self, x)
        finally:
            context.reset(token)

    def select(features, scale, keep):
        if context.get():
            return _select_full(features, scale, keep, primitive, counts)
        return primitive(features, scale, keep)

    with patch.object(curved, "selected_design", select), patch.object(
        position.NormalPosition, "calculate", calculate,
    ):
        yield counts
