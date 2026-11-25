import json
from types import SimpleNamespace

import masked_cfo_0218 as held
import masked_cfo_saved as saved
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
    assert held.causal_view(files, 3, expected, {"2-bbbb.tle"}) == selected
    with pytest.raises(ValueError, match="missing"):
        held.causal_view(files, 2, expected, {"2-bbbb.tle"})


def test_campaign_offer_retains_original_bytes_and_matches_the_normalized_field_request(tmp_path):
    offer = tmp_path / "offer.json"
    body = b'{ "width_km":18, "center":[51, 12] }\n'
    offer.write_bytes(body)
    authority = {"region_sha256": saved.signed.tag(body)}
    region = dict(center=[51., 12.], screen_center=[51., 12.], width_km=18.)
    request = {"offered_region": region}
    assert held.authenticated_offer(tmp_path, authority, request) == body
    with pytest.raises(ValueError, match="original field request"):
        held.authenticated_offer(tmp_path, authority, {"offered_region": dict(region, screen_center=[51., 13.])})
    offer.write_bytes(body.rstrip())
    with pytest.raises(ValueError, match="signed regional digest"):
        held.authenticated_offer(tmp_path, authority, request)


@pytest.mark.parametrize(("change", "verified"), [
    ({}, True),
    ({"verified_pair": False}, False),
    ({"acquisition_verified": None}, False),
    ({"attempt_result_sha256": "sha256:" + "f" * 64}, False),
    ({"attempt_result_sha256": None}, False),
])
def test_official_status_requires_each_rows_verification_and_pair_pin(tmp_path, monkeypatch, change, verified):
    admitted = dict(case=held.CASE, case_id="original", assigned_rank=63)
    monkeypatch.setattr(held, "enrollment", lambda _: admitted)
    case = tmp_path / "cases" / held.CASE
    case.mkdir(parents=True)
    pins = {arm: saved.signed.tag(arm.encode()) for arm in ("installed", "successor")}
    pair = dict(verified_pair=True, state="observed_pair", attempt_result_sha256=pins)
    (case / "pair.json").write_text(json.dumps(pair))
    rows = [dict(admitted, algorithm=arm, verified_pair=True, acquisition_verified=True, attempt_result_sha256=pin)
            for arm, pin in pins.items()]
    rows[0].update(change)
    (tmp_path / "rows.jsonl").write_text("\n".join(map(json.dumps, rows)))
    status = held.status(tmp_path)
    assert status["verified_pair"] is verified
    assert status["pair_sha256"] == saved.signed.tag((case / "pair.json").read_bytes())
    assert status["roles"]["installed"]["acquisition_verified"] is rows[0]["acquisition_verified"]
