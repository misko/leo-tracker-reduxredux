"""Private dense feature storage for scalar-only, serial standard-grid scores."""

from collections import Counter
from contextlib import contextmanager
from functools import _lru_cache_wrapper
from hashlib import sha256
from inspect import getsource
from pathlib import Path
import subprocess
from textwrap import dedent
from unittest.mock import patch

import numpy as np

from grid_design_template import Designs
from grid_feature_projection import FLAGS


TEMPLATE_PY = "5c485d4b36fc090ddbc4568f92fefdf68a164cec392c65173660edf3c02b8817"
TEMPLATE_C = "cf54e0c11a75178571cb3d69eeed08ea789a6982a40d6ab8c8fbb3cc3f918080"
SAMPLER = "9f21ca2c990d61cec8b9da2cfc99b6b1a12b7021bb8cf39c86d4d0707645a481"
CACHED = "3a8c9bde7ddddc115fcb219f8588fd51188ef4081567d8e2fe91df8324418e9f"
OBJECTIVE = "14b1d6329472767c424ef78eeab72a989e1bf71b39df3b58c78d42e152ad48de"


def check(path, expected):
    content = Path(path).read_bytes()
    if sha256(content).hexdigest() != expected:
        raise ValueError(f"Unexpected source or binary {path}")
    return content


def build(binary):
    source = Path(Designs.binding.__wrapped__.__code__.co_filename).with_suffix(".c")
    text = check(source, TEMPLATE_C).decode()
    old = "    memcpy(output, fixed, rows * width * sizeof(*output));"
    if text.count(old) != 1:
        raise ValueError("Missing original template copy")
    modified = binary.with_suffix(".c")
    with modified.open("x") as handle:
        handle.write(text.replace(old, "    if (output != fixed)\n    " + old))
    subprocess.run(["cc", *FLAGS, str(modified), "-o", str(binary)], check=True, timeout=15)


class Workspace(Designs):
    def __init__(self, binary):
        super().__init__(binary)
        self.owner = None
        operation = Designs.binding.__wrapped__
        check(operation.__code__.co_filename, TEMPLATE_PY)
        text = dedent(getsource(operation))
        old = "        result = np.empty_like(fixed)"
        if text.count(old) != 1:
            raise ValueError("Missing original owned dense allocation")
        new = """        borrowed = self.owner is problem
        result = fixed if borrowed else np.empty_like(fixed)
        if borrowed:
            self.counts["borrowed_designs"] += 1
            self.counts["template_bytes_not_copied"] += fixed.nbytes"""
        namespace = dict(operation.__globals__)
        exec(compile(text.replace(old, new), operation.__code__.co_filename, "exec"), namespace)
        self.binding = namespace["binding"].__get__(self)


def released_cache(problem, module):
    fn = problem.calculate
    if (getattr(fn, "__globals__", None) is not vars(module)
            or fn.__qualname__ != "cached.<locals>.<lambda>"
            or fn.__code__.co_freevars != ("calculate",)):
        return None
    cache = fn.__closure__[0].cell_contents
    if (type(cache) is not _lru_cache_wrapper or cache.cache_parameters() != dict(maxsize=8, typed=False)
            or cache.__wrapped__.__qualname__ != "cached.<locals>.calculate"
            or cache.__wrapped__.__globals__ is not vars(module)):
        return None
    return cache


@contextmanager
def scalar_grid_score(original_sampler, context, endpoints, workspace, *, map_batches=None):
    """Keep endpoint records and expose no reusable full matrix through the LRU."""
    from leo.analysis import position_grid
    from leo.analysis.localization_v3 import event_position, reassociation_context

    objective = reassociation_context.objective
    problems = {arm: row[0] for arm, row in context["problems"].items()}
    metrics = Counter()
    by_arm = {arm: Counter() for arm in problems}
    endpoint_keys = {tuple(position) for position in endpoints.values()}

    def ordinary(arm, position):
        return objective(problems[arm], context, np.asarray(position))

    if (original_sampler is not position_grid.sample_position_grid or context["families"]
            or map_batches is not None or len({id(problem) for problem in problems.values()}) != len(problems)):
        yield ordinary, by_arm, metrics
        return
    try:
        for item, pin in ((position_grid, SAMPLER), (event_position, CACHED), (reassociation_context, OBJECTIVE)):
            check(item.__file__, pin)
    except ValueError:
        yield ordinary, by_arm, metrics
        return
    caches = {arm: released_cache(problem, event_position) for arm, problem in problems.items()}
    if any(cache is None for cache in caches.values()):
        yield ordinary, by_arm, metrics
        return
    metrics["admitted"] += 1
    seen = {arm: set() for arm in problems}

    def score(arm, position):
        key = tuple(position)
        if key in endpoint_keys or key in seen[arm] or workspace.owner is not None:
            by_arm[arm]["ordinary"] += 1
            return ordinary(arm, position)
        seen[arm].add(key)
        problem = problems[arm]
        original = caches[arm].__wrapped__
        try:
            workspace.owner = problem
            with patch.object(problem, "calculate", lambda query: original(tuple(query))):
                by_arm[arm]["scalar_only"] += 1
                return ordinary(arm, position)
        finally:
            workspace.owner = None

    yield score, by_arm, metrics
