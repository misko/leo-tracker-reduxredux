"""Compact v5 inference and the evidence used to draw its own eight figures."""

import json
import traceback
from contextlib import nullcontext

from leo.analysis.localization_v3.recovery_inventory import (
    baseline_pair, publication_support, recovery_context,
)
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v4.native_bound import NativeBound
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.application.localization_v3 import prepare_native_scan
from leo.application.localization_v3_engine import _json_value, _prepared_values
from leo.contracts.fast_standard_analysis import ALGO08
from leo.presentation.localization_v3 import prepare_packet
from leo.presentation.position_path import recorded_fit_path
from tools.pipeline_eval.qualification.compact_history_replay import history_support
from tools.pipeline_eval.variants import orbit_projector, v5_core
from tools.pipeline_eval.variants.v5_direct_cavity import numerical_bindings
from tools.pipeline_eval.variants.v5_orbit_domain import OUTSIDE, corner_support


def selected_packet(prepared, signed, fit):
    if fit is None:
        fit = dict(status="complete", accepted=False, baseline_node=signed["node"],
                   baseline_entries=signed["entries"], baseline_means=signed["means"],
                   original_mask=signed["keep"], powers=signed["powers"], model=signed["model"],
                   policy_arms=signed["arms"])
    ctx = recovery_context(signed["scan"], fit)
    ctx["families"] = []
    arms = fit["policy_arms"]
    _, replayed = baseline_pair(ctx)
    owners = {k: v["owners"] for k, v in publication_support(arms, replayed).items()}
    stage = json.loads(json.dumps(dict(model_version=ALGO08, arms=arms), default=_json_value))
    path = recorded_fit_path([stage], ALGO08)
    tracks = prepared["tracks"]
    return prepare_packet(ctx, owners, arms, tracks["observations"], tracks["tracks"],
                          selected_model=ALGO08, position_path=path, grid_seconds=30)


def solve(native, archive, assets):
    from leo.analysis.localization_v4.backend import read_manifest, validate_manifest
    if not native["source"]["probes"]:
        return dict(status="withheld", reason="no valid receiver windows in the sealed recording",
                    arms={arm: {"latlon": None} for arm in ("c0", "fitted_c")}), None, "stock"
    manifest = validate_manifest(read_manifest(assets / "native/manifest.json"), check_provider=True)
    config = json.loads((assets / "tracks.json").read_bytes())["config"]
    projector = orbit_projector.Projector(assets / "projector.so")
    region = SearchRegion((37.906, -122.545), width_km=25)
    packet = None

    def evidence(*args):
        nonlocal packet
        packet = selected_packet(*args)

    def attempt(support):
        with support:
            prepared = _prepared_values(prepare_native_scan(
                native, archive, TrackConfig(**config),
                screen_latitude_deg=37.5, screen_longitude_deg=-122.0))
            with numerical_bindings(projector):
                return v5_core.infer(prepared, region, NativeBound(manifest["binary"]), {},
                                     selected_evidence=evidence)

    policy = "stock"
    try:
        result = attempt(nullcontext())
    except (ValueError, AssertionError) as exc:
        frame = traceback.extract_tb(exc.__traceback__)[-1].name
        if isinstance(exc, ValueError) and str(exc) == OUTSIDE and frame == "prepare":
            policy, retry = "orbit_support", corner_support()
        elif isinstance(exc, AssertionError) and not str(exc) and frame == "previous_bank":
            policy, retry = "history_support", history_support()
        else:
            raise
        result = attempt(retry)
    return result, packet, policy
