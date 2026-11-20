import gzip
import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from leo import application
from tools.pipeline_eval.qualification import causal_startup_replay as experiment
from tools.pipeline_eval.qualification import causal_startup_results as scorer
from tools.pipeline_eval.variants import v5_causal_startup as startup

ANCHOR = {"before": {"realtime_ns": 10}, "after": {"realtime_ns": 20}}
SCREEN = (37.0, -122.0)


class FirstPacket:
    def __getitem__(self, name):
        if name not in ANCHOR:
            raise AssertionError("future-only field accessed during startup")
        return ANCHOR[name]


def test_startup_uses_only_first_clock_and_nominal_horizon(monkeypatch):
    archive = object()
    sky = {"nominal_elements": {"A": object()}, "bank": "geometry"}
    history = {"past_versions": "causal"}
    checked = []

    def initial(reader, tracks, metadata, **kwargs):
        assert reader is archive and tracks == ({"times": (300.0,)},)
        assert metadata == {"anchor_utc_ns": 15, "causal_cutoff_utc_ns": 10}
        checked.append(kwargs["element_parser"])
        assert (kwargs["screen_latitude_deg"], kwargs["screen_longitude_deg"]) == SCREEN
        return sky

    def phase(reader, elements, metadata, *, element_parser):
        assert reader is archive and elements is sky["nominal_elements"]
        assert metadata["anchor_utc_ns"] == 15 and element_parser is checked[0]
        return history

    monkeypatch.setattr(
        application,
        "localization_v3",
        SimpleNamespace(
            prepare_initial_sky=initial,
            prepare_phase_history=phase,
            forecast=lambda value: {"from": value},
        ),
        raising=False,
    )
    monkeypatch.setitem(
        sys.modules, "leo.analysis.localization_v3.elements", SimpleNamespace(ElementParser=object)
    )
    state = startup.prepare(archive, FirstPacket(), SCREEN)
    assert state.sky is sky and state.forecast == {"from": history}


def test_future_fit_tail_clock_or_archive_change_disables_reuse():
    archive = object()
    state = startup.Startup(startup.metadata(ANCHOR), SCREEN, archive, {}, {}, {}, {})
    exact = {"tracks": [{"times": [22.0, 299.9]}], "metadata": dict(state.authority)}
    assert startup.reuse_authorized(state, exact, SCREEN, archive) == (True, 300)
    longer = dict(exact, tracks=[{"times": [22.0, 300.001]}])
    assert startup.reuse_authorized(state, longer, SCREEN, archive) == (False, 300.001)
    shifted = dict(exact, metadata=dict(state.authority, anchor_utc_ns=16))
    assert not startup.reuse_authorized(state, shifted, SCREEN, archive)[0]
    assert not startup.reuse_authorized(state, exact, SCREEN, object())[0]


def test_longer_postrelease_track_rebuilds_original_sky(monkeypatch):
    archive = object()
    state = startup.Startup(
        startup.metadata(ANCHOR),
        SCREEN,
        archive,
        {"old": 1},
        {"old": 2},
        {"old": 3},
        {},
    )
    document = object()
    later = {
        "tracks": [{"times": [22.0, 300.001]}],
        "metadata": state.authority,
        "status": "tracks_prepared",
    }
    seen = []

    def prepare_final(raw, reader, config, **options):
        assert raw is document and reader is archive and not state.sky
        seen.append(options)
        return {"status": "new full preparation"}

    monkeypatch.setattr(
        application,
        "localization_v3",
        SimpleNamespace(
            prepare_tracks=lambda raw, config: later,
            prepare_native_scan=prepare_final,
        ),
        raising=False,
    )
    monkeypatch.setitem(
        sys.modules,
        "leo.application.localization_v3_engine",
        SimpleNamespace(_prepared_values=lambda x: x),
    )
    monkeypatch.setattr(startup.orbit_projector, "Projector", lambda lib: SimpleNamespace(calls=1))
    monkeypatch.setattr(startup.direct, "numerical_bindings", lambda projector: nullcontext())
    monkeypatch.setattr(
        startup.direct,
        "infer",
        lambda prepared, *args: {"status": prepared["status"], "metrics": {}},
    )
    result = startup.finish(
        document,
        state,
        archive=archive,
        track_config=None,
        screen_center=SCREEN,
        region=None,
        library=None,
        bound=None,
    )
    assert result["status"] == "new full preparation"
    assert not result["metrics"]["early_orbit_reused"]
    assert seen == [{"screen_latitude_deg": 37.0, "screen_longitude_deg": -122.0}]


def test_invalid_first_bracket_is_rejected():
    with pytest.raises(ValueError, match="UTC bracket"):
        startup.metadata({"before": {"realtime_ns": 20}, "after": {"realtime_ns": 10}})


def test_published_source_reproduces_the_two_measured_arm_pairs(tmp_path):
    report = experiment.REPORT
    attempts = [
        row
        for file in scorer.FILES.values()
        for row in map(json.loads, gzip.decompress((report / file).read_bytes()).splitlines())
    ]
    assert scorer.publish(report / "source-lock.json", attempts, tmp_path) == {"ok": 4}
    for name in ("timing.csv", "scores.csv", "comparison.json", "prediction-lock.json"):
        assert (report / name).read_bytes() == (tmp_path / name).read_bytes()
    for item in attempts:
        if item["mode"] == "early":
            assert item["result"]["metrics"]["early_orbit_reused"]
