import json

import pytest

from leo.contracts.digests import canonical_digest
from reports.ALGO08.v3.held_anchor_route_publication import prepare


def empty_pair(recipe):
    digest = canonical_digest(recipe)
    stream = dict(visit_index=0, edge="lower", channel=1, actual_rf_hz=111e8, valid_start_counter=100, candidates=[])
    probes = [dict(stream, receiver_id=radio) for radio in (0, 1)]
    raw = "sha256:"+"a"*64
    return dict(source=dict(raw_recording_authority_digest=raw, input_manifest_sha256="inventory", session_id="session",
                            qualified=True, probes=probes,
                            analysis_manifest_sha256=canonical_digest(["cancellation", raw, digest[7:], probes])),
                provenance=dict(detector_sha256=digest, processed_windows=1, window_count=1, invalid_capture=0))


def test_incomplete_tiny_packet_keeps_its_genuine_recipe_without_history(tmp_path):
    from full_short_run import RECIPE_SHA, checked_recipe

    original = checked_recipe()
    packet = empty_pair(original)
    decision = tmp_path / "decision.json"
    selected, recipe, detector, result = prepare(packet, original, "session", "inventory", decision)
    assert selected is packet and recipe is original and detector == RECIPE_SHA
    assert result["choice"] == dict(route="unfiltered", log_score_gain_by_radio={0: 0, 1: 0})
    assert result["original_history_replay"] is None
    assert result["original_native_sha256"] == result["selected_native_sha256"] == canonical_digest(packet)
    assert json.loads(decision.read_bytes())["original_recipe_sha256"] == "sha256:"+RECIPE_SHA
    with pytest.raises(FileExistsError):
        prepare(packet, original, "session", "inventory", decision)


def test_recipe_or_original_authority_failure_seals_no_choice(tmp_path):
    from full_short_run import checked_recipe

    source = checked_recipe()
    packet = empty_pair(source)
    target = tmp_path / "rejected.json"
    with pytest.raises(ValueError, match="authentic.*unfiltered"):
        prepare(packet, {"wrong": "recipe"}, "session", "inventory", target)
    with pytest.raises(ValueError, match="original receiver or raw authority"):
        prepare(packet, source, "session", "different-inventory", target)
    assert not target.exists()
