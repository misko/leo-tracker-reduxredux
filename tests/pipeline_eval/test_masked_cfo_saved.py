from types import SimpleNamespace

import masked_cfo_saved as saved
from masked_cfo_0218 import causal_view
import pytest


def _harness(*, edits, status="tracks_prepared"):
    rows = [dict(observation_id="r1", measured_cfo_hz=1., time_s=2., fractional_margin=9.)]
    metadata = {"detector_sha256": "native"}
    tracks = SimpleNamespace(winning_observations=lambda native: (rows, metadata))
    calls = []

    def prepare(native, config):
        winners, native_metadata = tracks.winning_observations(native)
        assert native_metadata is metadata
        return dict(observations=winners, status=status, graph_points=len(winners), tracks=[])

    def derive(native, config):
        calls.append((native, config))
        return SimpleNamespace(edits=edits, masked_graph={}, gates={}, eligibility={})

    def apply(native, winners, features):
        if not features.edits:
            return winners
        return [dict(winners[0], measured_cfo_hz=features.edits["r1"]["updated_hz"])]

    stage = SimpleNamespace(derive=derive, apply_to_winners=apply, identity=lambda _: ("native",))
    return SimpleNamespace(prepare_tracks=prepare), tracks, stage, rows, calls


def test_only_signed_cfo_changes_and_derived_features_are_reused_across_retry():
    before = {"raw": 1}
    config, audit = object(), {}
    app, tracks, stage, rows, calls = _harness(edits={"r1": {"updated_hz": 2.}})
    with saved.bind_graph(app, tracks, stage, config, before, audit):
        for _ in range(2):
            assert app.prepare_tracks(dict(before), config)["observations"] == [dict(rows[0], measured_cfo_hz=2.)]
        assert tracks.winning_observations(before)[0] is rows and rows[0]["measured_cfo_hz"] == 1.
    assert len(calls) == audit["feature_calls"] == 1
    assert [row["edited_winners"] for row in audit["attempts"]] == [1, 1]
    assert set(audit["derive"]) == {"wall_ns", "cpu_ns"}


def test_no_edits_preserves_rows_and_ordinary_graph_withholds():
    app, tracks, stage, rows, _ = _harness(edits={}, status="no_active_curvature")
    config, audit = object(), {}
    native = {"raw": 1}
    with saved.bind_graph(app, tracks, stage, config, native, audit):
        result = app.prepare_tracks(native, config)
    assert result["observations"] is rows
    assert result["status"] == "no_active_curvature" and audit["attempts"][0]["edited_winners"] == 0
    assert saved.validate_exit(audit, {"decision":"withheld"}, saved.signed.canonical(native), enabled=True)["decision"] == "withheld"


def test_early_withholding_has_zero_features_and_changed_config_fails_closed():
    app, tracks, stage, _, calls = _harness(edits={})
    config, audit = object(), {}
    native = {"raw": 1}
    with saved.bind_graph(app, tracks, stage, config, native, audit):
        with pytest.raises(ValueError, match="approved configuration"):
            app.prepare_tracks(native, object())
    assert calls == []
    assert saved.validate_exit(audit, {"decision":"withheld"}, saved.signed.canonical(native), enabled=True)["feature_calls"] == 0
    with pytest.raises(ValueError, match="skipped"):
        saved.validate_exit(audit, {"decision":"complete"}, saved.signed.canonical(native), enabled=True)


def test_causal_view_requires_complete_signed_digest_and_cutoff():
    files = {"1-aaaa.tle": None, "2-bbbb.tle": None, "9-cccc.tle": None}
    selected = {"1-aaaa.tle": "aaaa", "2-bbbb.tle": "bbbb"}
    expected = saved.signed.canonical(selected)
    assert causal_view(files, 3, expected, {"2-bbbb.tle"}) == selected
    with pytest.raises(ValueError, match="missing"):
        causal_view(files, 2, expected, {"2-bbbb.tle"})
