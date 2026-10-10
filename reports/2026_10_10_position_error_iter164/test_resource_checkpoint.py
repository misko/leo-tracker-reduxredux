"""Execution-only checkpoint reporting tests."""

import json

import pytest

import resource_checkpoint


def test_build_matches_terminal_receipts_and_costs(tmp_path, monkeypatch):
    labels = [f"M{i:03d}" for i in range(193)]
    batches = [labels[:4]] + [labels[4 + i * 16:4 + (i + 1) * 16] for i in range(11)]
    batches.append(labels[180:])
    plan = {"members": [{"label": label} for label in labels], "execution_batches": batches}
    monkeypatch.setattr(resource_checkpoint, "canonical_digest", lambda _: "sha256:test")

    for shard in (0, 1):
        identity = dict(protocol_sha256="sha256:test", batch=0, shard=shard)
        members = []
        for label in batches[0][shard::2]:
            members.append(dict(label=label, phases={p: "complete" for p in ("search", "native", "zero")}))
        (tmp_path / f"batch-0-shard-{shard}.claim.json").write_text(json.dumps(identity))
        (tmp_path / f"batch-0-shard-{shard}.json").write_text(
            json.dumps(dict(identity, status="terminal", members=members))
        )
    for label in batches[0]:
        for phase, seconds in (("search", 6), ("native", 2), ("zero", 2)):
            directory = tmp_path / label / phase
            (directory / "slices").mkdir(parents=True)
            record = dict(protocol_sha256="sha256:test", label=label,
                          status="complete", elapsed_s=seconds)
            if phase != "search":
                record["branch"] = phase
            (directory / "result.json").write_text(json.dumps(record))
            (directory / "slices" / "01.started.json").write_text("{}")
            suffix = "finished" if phase == "search" else "done"
            (directory / "slices" / f"01.{suffix}.json").write_text("{}")

    report = resource_checkpoint.build(plan, tmp_path, 0)
    assert report["cumulative_members"] == 4
    assert report["batch_worker_seconds"] == 40
    assert report["all_phases_complete"]
    assert len(report["members"]) == 4

    phase_path = tmp_path / labels[0] / "native" / "result.json"
    wrong = json.loads(phase_path.read_text())
    wrong["status"] = "failed"
    phase_path.write_text(json.dumps(wrong))
    with pytest.raises(ValueError, match="disagrees"):
        resource_checkpoint.build(plan, tmp_path, 0)
