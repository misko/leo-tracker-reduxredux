from copy import deepcopy
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import held_cfo_features as feature


def sample():
    probes = []
    for visit in range(5):
        for receiver in (0, 1):
            gain = 1 if receiver == 0 else -1
            peak = dict(fractional_tracking_cfo_hz=gain*(visit*15 + 30*(visit % 2)),
                        integer_epoch_sample=33, fractional_epoch_offset_samples=.25,
                        passed_fractional_margin_gate=True, fractional_margin=.2, candidate_rank=0)
            probes.append(dict(receiver_id=receiver, edge="falling", channel=1, actual_rf_hz=11_900_000_000,
                               visit_index=visit, valid_start_counter=visit*2_500_000, candidates=[peak]))
    return dict(source=dict(session_id="arbitrary", sample_rate_hz=10_000_000, probes=probes,
                            raw_recording_authority_digest="sha256:raw", input_manifest_sha256="sha256:manifest",
                            analysis_manifest_sha256="sha256:analysis"),
                provenance=dict(detector_sha256="sha256:detector", excluded_windows=[], window_count=5, processed_windows=5))


def mock_graph(masked, config):
    assert config.alias_spacing_hz == feature.ALIAS
    rows = masked["source"]["probes"]
    assert all(not row["candidates"] for row in rows if row["visit_index"] % 2)
    session = masked["source"]["session_id"]
    tracks = []
    for rx in (0, 1):
        used = [r for r in rows if r["receiver_id"] == rx and r["candidates"]]
        tracks.append(dict(key=f"radio{rx}", indices=[0, 1, 2],
                           observation_ids=[feature.tag(f"{session}:{rx}:{r['valid_start_counter']}".encode()) for r in used],
                           pieces=[dict(indices=[0, 1, 2])], values=[r["candidates"][0][feature.HERTZ] for r in used]))
    return dict(tracks=tracks, graph_points=6, curved_indices=[])


def test_stage_is_target_masked_and_overlay_preserves_packet_and_other_evidence(monkeypatch):
    native = sample()
    unchanged = deepcopy(native)
    monkeypatch.setattr(feature, "prepare_tracks", mock_graph)
    config = SimpleNamespace(alias_spacing_hz=feature.ALIAS)
    sidecar = feature.derive(native, config)
    assert native == unchanged
    assert len(sidecar.edits) == 4 and sidecar.gates == {"eligible": 4}
    assert all(abs(edit["updated_hz"]-edit["original_hz"]) == 15 for edit in sidecar.edits.values())
    _, held, retained = feature.masked_stereo(native)
    winners = [dict(observation_id=oid, measured_cfo_hz=feature.winner(row["row"])[feature.HERTZ],
                    native_receiver_id=row["row"]["receiver_id"], actual_rf_hz=row["row"]["actual_rf_hz"],
                    time_s=row["counter"]/1e7) for oid, row in (held | retained).items()]
    restored = feature.apply_to_winners(native, winners, sidecar)
    assert [r["observation_id"] for r in winners] == [r["observation_id"] for r in restored]
    for old, new in zip(winners, restored, strict=True):
        oid = old["observation_id"]
        assert new == (dict(old, measured_cfo_hz=sidecar.edits[oid]["updated_hz"]) if oid in sidecar.edits else old)
    with pytest.raises(ValueError, match="different authenticated"):
        feature.apply_to_winners(native | {"source": native["source"] | {"session_id": "other"}}, winners, sidecar)
    absent_id = next(iter(sidecar.edits))
    with pytest.raises(ValueError, match="absent"):
        feature.apply_to_winners(native, [r for r in winners if r["observation_id"] != absent_id], sidecar)
    with pytest.raises(ValueError, match="original winning"):
        feature.apply_to_winners(native, restored, sidecar)
    assert native == unchanged


def test_released_donor_adaptor_discards_all_pieces_with_duplicate_members():
    item = {"a": dict(id="a", factor={feature.HERTZ: 8.}),
            "b": dict(id="b", factor={feature.HERTZ: 20.})}
    track = dict(key="t", indices=[0, 1], observation_ids=["a", "b"], values=[8., 20.],
                 pieces=[{"indices": [0]}, {"indices": [0, 1]}])
    assert feature.released_donors({"tracks": [track]}, item) == {}
