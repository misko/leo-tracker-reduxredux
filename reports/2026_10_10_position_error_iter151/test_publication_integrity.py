"""Fake filesystem receipts only; no models or evaluation ports."""

import json

from publication_integrity import build, canonical_digest


def fixture(tmp_path):
    def put(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    plan = dict(members=[dict(label=f"member-{i}") for i in range(12)])
    digest = canonical_digest(plan)
    protocol, raw, pub = tmp_path / "protocol.json", tmp_path / "raw", tmp_path / "pub"
    put(protocol, plan)
    pub.mkdir()
    labels = [m["label"] for m in plan["members"]]
    for label in labels:
        for phase in ("search", "native", "zero"):
            put(raw / label / phase / "result.json", dict(protocol_sha256=digest,
                label=label, branch=phase, status="complete"))
        put(raw / label / "search/case.json", dict(protocol_sha256=digest,
            label=label, identity={"observation_signature": "fake"}))
    for shard in (0, 1):
        base = dict(protocol_sha256=digest, shard=shard)
        put(raw / f"batch-{shard}.claim.json", base)
        put(raw / f"batch-{shard}.json", dict(**base, members=[dict(label=label,
            phases=dict(search="complete", native="complete", zero="complete"))
            for label in labels[shard::2]]))
    put(pub / "SUMMARY.json", dict(protocol_sha256=digest, all_terminal=True,
                                  rows=[dict(label=label) for label in labels]))
    for name in ("RESULTS.md", "position_errors.png", "PUBLICATION_POLICY.md", "source.py"):
        (pub / name).write_bytes(b"synthetic artifact")
    return protocol, raw, pub, [pub / "source.py"]


def test_complete_binds_cases_batches_and_distinct_protocol_digests(tmp_path):
    args = fixture(tmp_path)
    result = build(*args)
    assert result["status"] == "complete"
    assert result["terminal_phase_count"] == 36
    assert result["terminal_batch_count"] == 2
    assert result["protocol_file_sha256"] != result["receipt_protocol_canonical_digest"]
    assert str(args[1] / "member-0/search/case.json") in result["artifact_sha256"]
    assert str(args[1] / "batch-1.claim.json") in result["artifact_sha256"]


def test_missing_artifacts_and_claimed_crash_remain_failed(tmp_path):
    args = fixture(tmp_path)
    (args[1] / "batch-1.json").unlink()
    (args[1] / "member-0/search/case.json").unlink()
    (args[2] / "position_errors.png").unlink()
    result = build(*args)
    assert result["status"] == "incomplete"
    paths = {r["path"] for r in result["failures"]}
    assert str(args[1] / "batch-1.json") in paths
    assert str(args[1] / "member-0/search/case.json") in paths
    assert str(args[2] / "position_errors.png") in paths


def test_foreign_phase_and_controller_failure_block_sealing(tmp_path):
    args = fixture(tmp_path)
    path = args[1] / "member-0/native/result.json"
    row = json.loads(path.read_text()); row["protocol_sha256"] = "foreign"
    path.write_text(json.dumps(row))
    path = args[1] / "batch-1.json"
    row = json.loads(path.read_text()); row["members"][0] = dict(label="member-1", controller_failure="crash")
    path.write_text(json.dumps(row))
    result = build(*args)
    assert result["status"] == "incomplete"
    assert result["terminal_phase_count"] == 35
    assert result["terminal_batch_count"] == 0
