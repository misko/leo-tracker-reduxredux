import json

import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import full_receiver_comparison as compare
from tools.pipeline_eval.scoring import ARMS


def test_exact_roster_rejects_duplicates_or_recording_substitutions():
    ids = {"DS26-0004", "DS29-0082"}
    compare.roster_matches(sorted(ids), ids, "fixture")
    with pytest.raises(ValueError, match="entire bound roster"):
        compare.roster_matches(["DS26-0004", "DS26-0004"], ids, "fixture")
    with pytest.raises(ValueError, match="entire bound roster"):
        compare.roster_matches(["DS26-0004", "DS29-0083"], ids, "fixture")


def test_archive_seal_rejects_altered_record_bytes(tmp_path):
    source = tmp_path / "scores.jsonl"
    source.write_text("{}\n")
    receipt = tmp_path / "seal.json"
    receipt.write_text(json.dumps({"files": {source.name: compare.sha(source)}}))
    compare.seal(tmp_path, receipt.name, [source.name])
    source.write_text('{"forged": true}\n')
    with pytest.raises(ValueError, match="differs from its prediction seal"):
        compare.seal(tmp_path, receipt.name, [source.name])


def test_native_binding_checks_exact_request_region_and_matched_graph():
    ident = "DS26-0004"
    tile = {"id": "original", "center": [37.9, -122.5]}
    item = {
        "regions": [tile],
        "catalog": {"path": "catalogue", "sha256": "1" * 64},
        "catalog_timestamp_ns": 11,
        "cutoff_utc_ns": 12,
        "native": {"path": "native", "sha256": "2" * 64},
        "recording": {"window_count": 8},
        "track_config": {"path": "track", "sha256": "3" * 64},
    }
    packet, _ = compare.native_lean_eval.request(item, "native")
    job = dict(id=ident, recording=ident, packet=packet, cohort="roof")
    row = dict(
        id=ident,
        recording=ident,
        cohort="roof",
        tile=tile,
        method=compare.JOINT,
        input_sha256=compare.corpus._sha(encoded(packet)),
        native_sha256=item["native"]["sha256"],
        catalog_sha256=item["catalog"]["sha256"],
        address_space_limit_mib=512,
        observation_sha256="fresh-graph",
        proc_memory_kib={"VmPeak": 1},
        stages={stage: {} for stage in ("archive_and_peak_selection", "graph", "joint_backend")},
        result=dict(status="withheld", metrics={}, arms={arm: {"latlon": None} for arm in ARMS}),
    )
    plan, inputs = {"cases": [job]}, {ident: item}
    assert compare.native_roof(plan, {ident: row}, inputs, compare.JOINT) == {ident: row}
    for field, replacement in (("tile", {"id": "wrong"}), ("input_sha256", "other")):
        with pytest.raises(ValueError, match=field):
            compare.native_roof(
                plan, {ident: dict(row, **{field: replacement})}, inputs, compare.JOINT
            )
    with pytest.raises(ValueError, match="observation_sha256"):
        compare.native_roof(
            plan,
            {ident: row},
            inputs,
            compare.JOINT,
            matched={ident: dict(row, observation_sha256="other")},
        )


def test_withheld_endpoints_never_count_toward_paired_accuracy():
    assert not compare.paired_threshold(None, 1.0, 1.10)
    assert not compare.paired_threshold(1.08, 1.0, 1.05)
    assert compare.paired_threshold(1.08, 1.0, 1.10)
    assert compare.paired_threshold(0.0, 0.0, 1.10)
