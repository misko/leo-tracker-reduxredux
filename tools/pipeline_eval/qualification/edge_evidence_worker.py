"""Use the current signed compact support to verify one face without reassignment."""

import runpy
from importlib import import_module
from time import perf_counter
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import compact_tile_interior, edge_evidence, portable_v5

original = portable_v5.run


def run(document, *, tile, **kwargs):
    saved = {}
    signed = import_module("leo.analysis.localization_v3.signed_context")
    signed_original = signed.signed_context

    def context(*args, **kwargs):
        result = signed_original(*args, **kwargs)
        saved.update(result)
        return result

    with patch.object(signed, "signed_context", context):
        result = original(document, tile=tile, **kwargs)
    baseline = compact_tile_interior.guard(result, tile)
    if baseline.get("reason") != "terminal_compact_fit_at_tile_face":
        return baseline
    start = perf_counter()
    triplet = edge_evidence.normal_hypotheses(result, tile)
    if triplet is None:
        check = dict(status="ambiguous_face")
    elif not saved or any(
        not np.array_equal(saved["arms"][arm]["endpoint_latlon"], result["arms"][arm]["latlon"])
        for arm in edge_evidence.ARMS
    ):
        check = dict(status="terminal_support_unavailable")
    else:
        evidence = edge_evidence.evaluate(saved, triplet)
        inside = all(r["state"] == "inside" for r in evidence.values())
        check = dict(status="inside" if inside else "not_certified", arms=evidence)
        if inside:
            check["accepted_same_endpoint"] = True
            baseline = result
    check["wall_s"] = perf_counter() - start
    baseline["metrics"]["edge_evidence"] = check
    return baseline


if __name__ == "__main__":
    with patch.object(portable_v5, "run", run):
        runpy.run_path("/trial/main.py", run_name="__main__")
