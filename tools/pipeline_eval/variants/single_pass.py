"""Change only the bound capture producer's paired anchor policy for an assay."""

from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import patch

MODES = ("conditional", "primary12", "wide22")


@contextmanager
def route(analysis, detector, mode):
    if mode not in MODES:
        raise ValueError(f"unknown anchor policy {mode}")
    dwell = analysis.analyze_glrt64_dwell
    evaluate = detector._evaluate_probe
    attempts = []
    wide = ()

    def paired(samples, configuration, *, edge, search_geometry):
        nonlocal wide
        wide = search_geometry.fallback_anchor_symbols
        if len(wide) != 22:
            raise ValueError("the capture geometry does not declare the 22-anchor retry")
        if mode != "conditional":
            search_geometry = replace(search_geometry, fallback_anchor_symbols=())
        return dwell(samples, configuration, edge=edge, search_geometry=search_geometry)

    def attempt(probe, configuration, calibration, *, acquisition_config, **keys):
        anchors = acquisition_config.anchor_symbols
        if len(anchors) != 12 and anchors != wide:
            raise ValueError("unexpected anchor set in the capture producer")
        if mode == "wide22":
            acquisition_config = replace(acquisition_config, anchor_symbols=wide)
        result = evaluate(
            probe, configuration, calibration, acquisition_config=acquisition_config, **keys
        )
        gate = configuration.glrt64_margin_gate
        passing = result.has_fractional_detection(gate)
        if passing != any(
            c.fractional_epoch_status == "complete"
            and c.fractional_margin is not None
            and c.fractional_margin >= gate
            for c in result.candidates
        ):
            raise ValueError("the retry gate could not be recovered from fractional factors")
        attempts.append((keys["receiver_id"], len(acquisition_config.anchor_symbols), passing))
        return result

    with (
        patch.object(analysis, "analyze_glrt64_dwell", paired),
        patch.object(detector, "_evaluate_probe", attempt),
    ):
        yield attempts
