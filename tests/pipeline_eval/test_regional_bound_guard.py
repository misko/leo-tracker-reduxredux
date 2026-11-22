from functools import partial
from math import inf, nextafter

import pytest

from leo.analysis.localization_v3.region import SearchRegion
from leo.operations.tle_archive import TleArchiveError, TleArchiveReader
from tools.pipeline_eval.variants import v5_core
from tools.pipeline_eval.variants.experimental.regional_bound_guard import (
    ARMS, bound_arms, bound_exterior_veto, causal_probes, guard_inference, inspect_boundary,
)
from tools.pipeline_eval.variants.experimental.regional_reassignment import probes


WIDTH = 25.
HALF = WIDTH / 2


@pytest.mark.parametrize(("coordinate", "expected"), (
    (HALF, ["c0"]), (-HALF, ["c0"]), (nextafter(HALF, -inf), ["c0"]),
    (nextafter(nextafter(HALF, -inf), -inf), []), (HALF - .00001, []),
    (nextafter(HALF, inf), None), (float("nan"), None),
))
def test_boundary_uses_binary64_local_coordinates(coordinate, expected):
    assert bound_arms({"c0": [coordinate, 0.], "fitted_c": [0., .01]}, WIDTH) == expected


def test_skips_unavailable_pair_before_touching_score():
    result = inspect_boundary({"c0": [0., HALF]}, WIDTH, lambda: pytest.fail("unexpected score"))
    assert result == dict(bound_arms=None, evaluated=False, would_withhold=False)


@pytest.mark.parametrize(("fit", "scenario"), (
    (False, "interior"), (False, "far"), (True, "far"), (True, "near"), (True, "failure"),
))
def test_guard_checks_selected_fit_and_preserves_nonveto_publication(fit, scenario):
    region = SearchRegion((32., 114.), WIDTH)
    prepared = {"tracks": object()}
    publications, score_calls = [], []
    bounded = scenario != "interior"

    def arms(boundary):
        return {
            arm: {"endpoint_east_north_km": [0., HALF if boundary and arm == "fitted_c" else 0.]}
            for arm in ARMS
        }

    signed = {"arms": arms(not bounded if fit else bounded)}
    selected = {"policy_arms": arms(bounded)} if fit else None
    original = dict(status="ok", metrics={"science": 1},
                    arms={arm: {"latlon": (32., 114.)} for arm in ARMS})

    def infer(prepared, offered, bound, stages, *, selected_evidence):
        assert offered is region
        selected_evidence(prepared, signed, selected)
        return original

    def score(tracks, offered):
        assert tracks is prepared["tracks"] and offered is region
        score_calls.append(True)
        if scenario == "failure":
            raise ValueError("no past TLE")
        rows = list(probes(region))
        winner = [WIDTH * (2.5 if scenario == "far" else .625), 0.]
        for row in rows:
            value = 2. if row["xy_km"] == winner else 1. if row["side"] == "inside" else 0.
            row["receiver_scores"] = {"1": value, "2": value}
        return rows

    result = guard_inference(infer, score)(
        prepared, region, None, {}, selected_evidence=lambda *args: publications.append(args),
    )
    assert bool(score_calls) == bounded
    if scenario == "far":
        assert not publications
        assert result["status"] == "withheld"
        assert result["reason"] == "both_receivers_support_far_exterior"
        assert all(row["latlon"] is None for row in result["arms"].values())
    else:
        assert publications == [(prepared, signed, selected)]
        assert result["status"] == original["status"]
        assert result["arms"] is original["arms"]
    diagnostic = result["metrics"]["regional_bound_guard"]
    assert diagnostic["bound_arms"] == (["fitted_c"] if bounded else [])
    if scenario == "failure":
        assert diagnostic["diagnostic_error"] == "no past TLE"


def test_scope_restores_inference_on_exception():
    original = v5_core.infer
    with pytest.raises(RuntimeError, match="caller failed"):
        with bound_exterior_veto(object()):
            assert v5_core.infer is not original
            raise RuntimeError("caller failed")
    assert v5_core.infer is original


def test_guard_leaves_an_upstream_withholding_unchanged():
    region = SearchRegion((32., 114.), WIDTH)
    withheld = {"status": "withheld", "reason": "no_active_curvature"}
    guarded = guard_inference(lambda *args, **kwargs: withheld, lambda *_: pytest.fail("score"))
    assert guarded({}, region, None, {}) is withheld


def test_guard_preserves_a_bound_initial_selector():
    region = SearchRegion((32., 114.), WIDTH)
    selector = object()
    withheld = {"status": "withheld", "reason": "no_tracks"}

    def infer(*args, select_initial, selected_evidence):
        assert select_initial is selector
        return withheld

    guarded = guard_inference(partial(infer, select_initial=selector), lambda *_: pytest.fail("score"))
    assert guarded({}, region, None, {}) is withheld


def test_archive_read_failure_keeps_a_boundary_fix():
    class Unreadable:
        def list_snapshots(self, provider):
            raise TleArchiveError("unreadable")

    region = SearchRegion((32., 114.), WIDTH)
    tracks = {"metadata": {"causal_cutoff_utc_ns": 1}}
    endpoints = {"c0": [HALF, 0.], "fitted_c": [0., 0.]}
    decision = inspect_boundary(endpoints, WIDTH, lambda: causal_probes(tracks, Unreadable(), region))
    assert decision["bound_arms"] == ["c0"]
    assert not decision["would_withhold"]
    assert decision["diagnostic_error"] == "Causal archive unavailable for exterior diagnostic"


def test_catalogue_handoff_binds_the_archive_cutoff_and_prepared_scan(monkeypatch, tmp_path):
    from sgp4 import api

    from leo.operations import localization_v3_inputs
    from tools import algo08_position
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    archive = TleArchiveReader(tmp_path / "archive")
    other = TleArchiveReader(tmp_path / "other")
    materialized, scored = [], []

    def build(reader, cutoff, *, element_parser):
        catalogue = object()
        materialized.append((reader.root, cutoff, catalogue))
        return catalogue

    def prepare(native, reader):
        cutoff = native["cutoff"]
        localization_v3_inputs.causal_catalogue(reader, native.get("catalogue_cutoff", cutoff),
                                                element_parser=object())
        return dict(status="inputs_prepared", sky={"bank": None},
                    tracks={"metadata": {"causal_cutoff_utc_ns": cutoff}})

    def score(tracks, reader, region, *, catalogue=None):
        scored.append((tracks, reader, region, catalogue))
        return {"points": []}

    def infer(prepared, region, bound, stages, *, selected_evidence):
        arms = {arm: {"endpoint_east_north_km": [HALF, 0.]} for arm in ARMS}
        selected_evidence(prepared, {"arms": arms}, None)
        return dict(status="ok", metrics={})

    monkeypatch.setattr(api, "accelerated", True)
    monkeypatch.setattr(localization_v3_inputs, "causal_catalogue", build)
    monkeypatch.setattr(algo08_position, "prepare_native_scan", prepare)
    monkeypatch.setattr(regional_bound_guard, "causal_probes", score)
    monkeypatch.setattr(v5_core, "infer", infer)
    northern = SearchRegion((52., 12.), WIDTH)
    southern = SearchRegion((-36., 145.), WIDTH)

    def run(reader, region, **native):
        ready = algo08_position._prepared_values(algo08_position.prepare_native_scan(native, reader))
        v5_core.infer(ready, region, None, {})
        return ready

    with bound_exterior_veto(archive):
        first = run(TleArchiveReader(archive.root), northern, cutoff=1)
        second = run(TleArchiveReader(archive.root), southern, cutoff=2)
        v5_core.infer(first, southern, None, {})
        different_archive = run(other, northern, cutoff=2)
        different_cutoff = run(archive, northern, cutoff=3, catalogue_cutoff=2)
        prepared = algo08_position.prepare_native_scan({"cutoff": 4}, archive)
        changed = algo08_position._prepared_values(prepared)
        changed["tracks"]["metadata"]["causal_cutoff_utc_ns"] = 5
        v5_core.infer(changed, northern, None, {})

    assert scored == [
        (first["tracks"], archive, northern, materialized[0][2]),
        (second["tracks"], archive, southern, materialized[1][2]),
        (first["tracks"], archive, southern, None),
        (different_archive["tracks"], archive, northern, None),
        (different_cutoff["tracks"], archive, northern, None),
        (changed["tracks"], archive, northern, None),
    ]
    assert algo08_position.prepare_native_scan is prepare
    assert v5_core.infer is infer
