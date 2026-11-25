from copy import deepcopy

import pytest

from leo.analysis.localization_v3.tracks import graph_tracks, winning_observations
from leo.analysis.polynomial_tracklets import TrackConfig
from reports.ALGO08.v3 import held_cfo_features as frozen
from reports.ALGO08.v3 import held_cfo_ingress as ingress


def native_packet():
    probes = []
    for visit in (0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12):
        channel = 1 + visit % 2
        for radio in (0, 1):
            peak = dict(fractional_tracking_cfo_hz=visit*15 + radio*10, integer_epoch_sample=33,
                        fractional_epoch_offset_samples=.25, passed_fractional_margin_gate=True,
                        fractional_margin=.2, candidate_rank=0)
            candidates = [dict(peak, candidate_rank=1, fractional_tracking_cfo_hz=5), peak]
            if (visit, radio) in {(2, 0), (4, 1), (8, 0)}:
                candidates = [dict(peak, passed_fractional_margin_gate=False)]
            probes.append(dict(receiver_id=radio, edge="falling" if channel == 1 else "rising", channel=channel,
                               actual_rf_hz=11_900_000_000+channel*25_000_000,
                               visit_index=visit, valid_start_counter=1000+visit*2_500_000+37, candidates=candidates))
    clock = dict(realtime_ns=25234540000, monotonic_ns=1975000)
    return dict(
        clock_anchor=dict(before=clock, after=clock, sample_counter=1000),
        last_sample_counter=31_000_000, delivery_clocks=[],
        source=dict(session_id="valid", sample_rate_hz=10_000_000, probe_ms=20, probes=probes,
                    raw_recording_authority_digest="sha256:raw", input_manifest_sha256="sha256:manifest",
                    analysis_manifest_sha256="sha256:analysis"),
        provenance=dict(detector_sha256="sha256:detector", excluded_windows=[{"visit": 3}],
                        window_count=13, processed_windows=12),
    )


def test_ingress_filters_actual_released_rows_and_keeps_opportunities(monkeypatch):
    native = native_packet()
    before = deepcopy(native)
    config = TrackConfig(alias_spacing_hz=frozen.ALIAS)
    winners, _ = winning_observations(native)
    masked, held, retained = frozen.masked_stereo(native)
    expected, _ = winning_observations(masked)
    rows, new_held, new_retained = ingress.bind_ingress(native, winners)
    assert (rows, new_held, new_retained) == (expected, held, retained)
    assert new_held and any(lane["factor"] is None for lane in new_retained.values())
    assert all(row["measured_cfo_hz"] != 5 for row in rows)
    by_id = {row["observation_id"]: row for row in winners}
    assert all(row is by_id[row["observation_id"]] for row in rows)

    def check(paid, cfg, *, source_id):
        assert paid == expected and cfg is config and source_id == "SCAN"
        return graph_tracks(paid, cfg, source_id=source_id)

    monkeypatch.setattr(ingress, "graph_tracks", check)
    actual = ingress.derive(native, config, winners)
    reference = frozen.derive(native, config)
    assert actual == reference
    assert frozen.apply_to_winners(native, winners, actual) == frozen.apply_to_winners(native, winners, reference)
    assert native == before


def test_one_shot_winners_retain_nonempty_released_graph_and_edits():
    native = native_packet()
    for probe in native["source"]["probes"]:
        probe.update(edge="falling", channel=1, actual_rf_hz=11_925_000_000)
        if probe["visit_index"] == 1:
            probe["candidates"][-1][frozen.HERTZ] += 30
    config = TrackConfig(min_points=4, points_per_coefficient=2, min_span_s=.5, max_degree=1)
    winners, _ = winning_observations(native)
    masked, _, _ = frozen.masked_stereo(native)
    masked_winners, _ = winning_observations(masked)
    retained, _, _ = ingress.bind_ingress(native, (row for row in winners))
    assert retained == masked_winners

    expected = frozen.derive(native, config)
    actual = ingress.derive(native, config, (row for row in winners))
    assert expected.masked_graph["tracks"] > 0 and expected.edits
    assert actual == expected
    assert frozen.apply_to_winners(native, (row for row in winners), actual) == frozen.apply_to_winners(
        native, winners, expected)


@pytest.mark.parametrize("field,new_value", [
    ("native_receiver_id", 2), ("receiver", 3), ("channel", 8), ("time_s", -.1),
    ("measured_cfo_hz", 999.), ("actual_rf_hz", 11_000_000_000.), ("fractional_margin", .3),
])
def test_ingress_rejects_a_different_row(field, new_value):
    native = native_packet()
    rows, _ = winning_observations(native)
    # Mutate the last supplied row without confounding the match with ordinary order.
    rows[-1] = dict(rows[-1], **{field: new_value})
    rows.sort(key=ingress.ingress_order)
    with pytest.raises(ValueError, match="differs from the signed winning probe"):
        ingress.bind_ingress(native, rows)


def test_ingress_rejects_missing_duplicate_reordered_and_nongated_rows():
    native = native_packet()
    rows, _ = winning_observations(native)
    for invalid in (rows[1:], [rows[0], *rows], [rows[1], rows[0], *rows[2:]]):
        with pytest.raises(ValueError, match="Ordinary Graph row differs|distinct winning rows"):
            ingress.bind_ingress(native, invalid)
    original = native["source"]["probes"][0]
    original["candidates"] = []
    with pytest.raises(ValueError, match="no gated winning probe"):
        ingress.bind_ingress(native, rows)
    original["candidates"] = []
    with pytest.raises(ValueError, match="unknown signed observation"):
        ingress.bind_ingress(native, sorted([*rows[1:], dict(rows[0], observation_id="other")], key=ingress.ingress_order))


def test_ingress_with_all_empty_candidates_and_invalid_stereo():
    native = native_packet()
    config = TrackConfig(alias_spacing_hz=frozen.ALIAS)
    for probe in native["source"]["probes"]:
        probe["candidates"] = []
    assert ingress.derive(native, config, []) == frozen.derive(native, config)
    native["source"]["probes"].pop()
    with pytest.raises(ValueError, match="partition the signed"):
        ingress.derive(native, config, [])
