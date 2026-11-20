"""Replace the physical peer retry's anchor schedule within the original detector."""

from contextlib import ExitStack, contextmanager
from dataclasses import replace
from unittest.mock import patch

MODES = ("conditional", "primary12", "complement8")


def complement(primary, retry):
    """Choose eight evenly spaced entries of the original disjoint retry anchors."""
    options = tuple(sorted(set(retry) - set(primary)))
    if len(primary) != 12 or len(retry) != 22 or len(options) < 8:
        raise ValueError("unexpected capture anchor geometry")
    return tuple(options[round(i * (len(options) - 1) / 7)] for i in range(8))


@contextmanager
def route(analysis, detector, acquisition, mode, *, trace=False):
    if mode not in MODES:
        raise ValueError(f"unknown peer retry measurement: {mode}")
    dwell = analysis.analyze_glrt64_dwell
    evaluate = detector._evaluate_probe
    acquire = detector.acquire_symbolwise
    select = acquisition._retain_score_map_peaks
    attempts = []
    peaks = []
    acquisitions = []

    def paired(samples, configuration, *, edge, search_geometry):
        if len(search_geometry.fallback_anchor_symbols) != 22:
            raise ValueError("the bound producer does not declare its original peer retry")
        if mode == "primary12":
            search_geometry = replace(search_geometry, fallback_anchor_symbols=())
        return dwell(samples, configuration, edge=edge, search_geometry=search_geometry)

    def scored(*args, **kwargs):
        chosen = select(*args, **kwargs)
        peaks.append(chosen)
        return chosen

    def acquired(*args, **kwargs):
        result = acquire(*args, **kwargs)
        acquisitions.extend(result.candidates)
        return result

    def attempt(probe, configuration, calibration, *, acquisition_config, **keys):
        anchors = acquisition_config.anchor_symbols
        retry = len(anchors) == 22
        if len(anchors) == 12:
            primary = anchors
        elif retry:
            primary = attempts[0]["anchors"]
            if mode == "complement8":
                acquisition_config = replace(
                    acquisition_config, anchor_symbols=complement(primary, anchors)
                )
        else:
            raise ValueError("unexpected probe anchor schedule")
        peaks.clear()
        acquisitions.clear()
        result = evaluate(
            probe, configuration, calibration, acquisition_config=acquisition_config, **keys
        )
        row = dict(
            receiver=keys["receiver_id"],
            anchors=acquisition_config.anchor_symbols,
            retry=retry,
            gate=result.has_fractional_detection(configuration.glrt64_margin_gate),
            public=result.candidates,
        )
        if trace:
            if not peaks:
                raise ValueError("genuine acquisition did not produce a retained peak trace")
            row.update(
                coarse=tuple(
                    (float(s), int(e), calibration.absolute_cfo_hz(float(f)))
                    for s, e, f in peaks[-1]
                ),
                acquired=tuple(
                    (int(c.rank), int(c.refined_epoch_sample), float(c.absolute_cfo_hz))
                    for c in acquisitions
                ),
            )
        attempts.append(row)
        return result

    with ExitStack() as context:
        context.enter_context(patch.object(analysis, "analyze_glrt64_dwell", paired))
        context.enter_context(patch.object(detector, "_evaluate_probe", attempt))
        if trace:
            context.enter_context(patch.object(acquisition, "_retain_score_map_peaks", scored))
            context.enter_context(patch.object(detector, "acquire_symbolwise", acquired))
        yield attempts
