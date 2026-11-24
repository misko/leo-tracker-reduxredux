import pytest

from reports.ALGO08.v3 import three_quarter_members as trial


def accession(*segments):
    raw = dict(segments=[], chunks=[])
    for i, counts in enumerate(segments):
        path = f"segment-{i}/manifest.json"
        raw["segments"].append(dict(path=path, sha256=f"signed-{i}"))
        local = 0
        for index, count in enumerate(counts):
            raw["chunks"].append(dict(chunk_index=index, first_sequence=local, window_count=count, segment_manifest=path,
                                     index_sha256="index", observed_index_sha256="index", compressed_bytes=1024,
                                     observed_payload_bytes=1024))
            local += count
    return dict(raw_recording=raw, window_count=sum(map(sum, segments)))


def tape(count, invalid=()):
    rows = [dict(visit_index=v, receiver_id=r, edge="upper", channel=1, actual_rf_hz=5.0, candidates=[])
            for v in range(count) if v not in invalid for r in (0, 1)]
    return dict(clock_anchor={"before": {"realtime_ns": 10}}, delivery_clocks=list(range(count)),
                source=dict(probes=rows, raw_recording_authority_digest="authority", input_manifest_sha256="inventory"),
                provenance=dict(processed_windows=count-len(invalid), window_count=count, invalid_capture=len(invalid),
                                excluded_windows=[dict(visit=v) for v in invalid]))


def test_fixed_selection_resets_segment_and_preserves_short_tails():
    original = accession([64, 64, 64, 64, 7], [64, 64, 64, 64, 64, 64, 64, 64, 8])
    spans = trial.membership(original)
    assert [s["ordinal"] for s in spans if s["omit"]] == [3, 8, 12]
    assert [s["first_visit"] for s in spans if s["omit"]] == [192, 455, 711]
    assert [(s["window_count"], s["omit"]) for s in spans if s["window_count"] < 64] == [(7, False), (8, False)]
    original["raw_recording"]["chunks"][0]["observed_index_sha256"] = "changed"
    with pytest.raises(ValueError, match="signed member"):
        trial.membership(original)


def test_replay_advances_original_admitted_anchors_and_never_inserts_omitted_rows():
    spans = trial.membership(accession([64, 64, 64, 64, 3]))
    original = tape(259, [197, 258])
    original_admitted, _ = trial.anchors(original)
    actual, recipe, omitted = trial.project(original, {}, spans, original_admitted, scope="synthetic")
    assert omitted == set(range(192, 256)) and set(row["visit_index"] for row in actual["source"]["probes"]).isdisjoint(omitted)
    assert actual["delivery_clocks"] == original["delivery_clocks"] and actual["clock_anchor"] == original["clock_anchor"]
    assert actual["provenance"]["excluded_windows"] == [{"visit": 258}]
    assert actual["provenance"]["processed_windows"] == 194
    assert actual["provenance"]["research_sampling"]["skipped_acquisition_windows"] == sorted(omitted)
    assert original_admitted[256][1:] == (255, False) and original_admitted[257][1:] == (256, True)
    assert actual["source"]["raw_recording_authority_digest"] == "authority"
    assert trial.digest(recipe) == actual["provenance"]["detector_sha256"]


def test_saved_history_requires_exact_measured_unfiltered_parent(monkeypatch):
    recipe = dict(aperture_samples=[200_000, 80_000], shortened_sha256=trial.SPARSE,
                  rule=["full"]+["short_primary"]*7)
    output_recipe = dict(recipe, held_native_8ms={
        "measurement": "original signed 8 ms native CFO, no subsequent fixed-epoch 20 ms remeasurement"})
    native = tape(2)
    probes = native["source"]["probes"]
    parent = trial.rebinding(native, probes, recipe)
    final = trial.rebinding(parent, probes, output_recipe)
    monkeypatch.setattr(trial, "HELD", trial.digest(output_recipe))
    witness = dict(receiver_recipe=output_recipe, choice={"route": "unfiltered"}, refinement_calls=0,
                   native_sha256=trial.digest(final), parent_native_sha256=trial.digest(parent),
                   detector_recipe_sha256=trial.HELD, parent_detector_sha256=trial.digest(recipe), observed=0, selected=0)
    assert trial.preheld(final, witness) == (parent, recipe)
    with pytest.raises(ValueError, match="strongest-margin tape"):
        trial.preheld(final, dict(witness, choice={"route": "history"}))
    with pytest.raises(ValueError, match="handoff"):
        trial.preheld(final, dict(witness, parent_native_sha256="incorrect"))
