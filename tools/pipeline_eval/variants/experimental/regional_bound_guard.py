"""Optional boundary-gated regional diagnostic for the compact saved solver."""

from contextlib import contextmanager
from functools import wraps
from math import inf, isfinite, nextafter
from unittest.mock import patch

from tools.pipeline_eval.variants.experimental.regional_exterior_veto import evaluate


ARMS = ("c0", "fitted_c")


def bound_arms(endpoints, width_km):
    """Return arms within one binary64 step of a native optimizer bound."""
    half = width_km / 2
    if not isfinite(half) or half <= 0:
        return None
    inward = nextafter(half, -inf)
    active = []
    for arm in ARMS:
        try:
            east, north = endpoints[arm]
            if not isfinite(east) or not isfinite(north) or max(abs(east), abs(north)) > half:
                return None
        except (KeyError, TypeError, ValueError):
            return None
        if max(abs(east), abs(north)) >= inward:
            active.append(arm)
    return active


def inspect_boundary(endpoints, width_km, score):
    active = bound_arms(endpoints, width_km)
    result = dict(bound_arms=active, evaluated=False, would_withhold=False)
    if not active:
        return result
    try:
        points = score()
    except (OSError, ValueError) as error:
        return dict(result, diagnostic_error=str(error))
    return dict(result, **evaluate(points, width_km), evaluated=True)


def causal_probes(prepared_tracks, archive, region):
    """Use the original causal catalogue and exactly the saved all-track score."""
    from leo.analysis.localization_v3.elements import ElementParser
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from tools.pipeline_eval.variants.experimental.regional_reassignment import evaluate as score

    cutoff = prepared_tracks["metadata"]["causal_cutoff_utc_ns"]
    catalogue = causal_catalogue(archive, cutoff, element_parser=ElementParser())
    result = score(prepared_tracks, catalogue.catalogue, region)
    result["snapshots"] = sorted({row["snapshot_digest"] for row in catalogue.provenance})
    return result


def guard_inference(infer, score):
    @wraps(infer)
    def guarded(prepared, region, bound, stage_s, *, selected_evidence=None, **options):
        diagnostic = None

        def assess(ready, signed, fit):
            nonlocal diagnostic
            selected = signed["arms"] if fit is None else fit["policy_arms"]
            endpoints = {arm: row.get("endpoint_east_north_km") for arm, row in selected.items()}
            diagnostic = inspect_boundary(
                endpoints, region.width_km, lambda: score(ready["tracks"], region),
            )
            if selected_evidence is not None and not diagnostic["would_withhold"]:
                selected_evidence(ready, signed, fit)

        result = infer(prepared, region, bound, stage_s, selected_evidence=assess, **options)
        if diagnostic is None:
            return result
        metrics = dict(result["metrics"], regional_bound_guard=diagnostic)
        if diagnostic["would_withhold"]:
            return dict(result, status="withheld", reason="both_receivers_support_far_exterior",
                        arms={arm: {"latlon": None} for arm in ARMS}, metrics=metrics)
        return dict(result, metrics=metrics)

    return guarded


@contextmanager
def bound_exterior_veto(archive):
    """Opt in within one dedicated experimental solver process."""
    from tools.pipeline_eval.variants import v5_core

    def score(tracks, region):
        return causal_probes(tracks, archive, region)["points"]

    with patch.object(v5_core, "infer", guard_inference(v5_core.infer, score)):
        yield
