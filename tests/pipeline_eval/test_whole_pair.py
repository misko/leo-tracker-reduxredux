import gzip
import json
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import whole_pair as pair


@pytest.fixture
def archived_pair(tmp_path, monkeypatch):
    original, full, paired = (tmp_path / name for name in ("cavity", "recovery", "pair"))
    for folder in (original, full, paired):
        folder.mkdir()

    def save(folder, name, data):
        payload = json.dumps(data).encode()
        if name.endswith(".gz"):
            payload = gzip.compress(payload)
        (folder / name).write_bytes(payload)

    inherited = dict(
        inputs={case: {"native_sha256": case} for case in pair.CASES},
        sources={},
        runtime_max_s=pair.worker.LIMIT,
        memory_bytes=pair.worker.MEMORY,
        swap_bytes=0,
        cpus=list(pair.worker.CPUS),
    )
    first, second = pair.CASES
    save(original, "source-lock.json", inherited)
    save(original, "prediction-lock.json", {})
    save(original, "comparison.json", {"exact": True})
    stages = {
        first: {"position": {"end": {"memory.max": pair.worker.MEMORY, "memory.swap.max": 0}}}
    }
    save(original, "stages.json.gz", stages)
    save(
        original,
        "positions.jsonl.gz",
        {"id": first, "method": pair.worker.METHOD, "result": {"status": "ok"}},
    )
    save(full, "positions.jsonl.gz", {"id": second, "result": {"status": "ok"}})
    (paired / "PROTOCOL.md").write_text("fixture")
    monkeypatch.setattr(pair, "REPORT", paired)
    monkeypatch.setattr(pair.cavity, "REPORT", original)
    monkeypatch.setattr(pair.apparatus, "REPORT", full)
    monkeypatch.setattr(pair.apparatus, "PRIOR", full)
    monkeypatch.setattr(pair.apparatus, "sealed", Path.joinpath)
    monkeypatch.setattr(pair.cavity, "plan", lambda: inherited)
    monkeypatch.setattr(pair.cavity, "PREVIOUS_PLAN", lambda: inherited)

    def control(case):
        return {"native_sha256": case, "method": "v5_secant_fit", "result": {"status": "ok"}}

    monkeypatch.setattr(pair.cavity, "control", control)
    return stages, original


def test_pair_pins_only_a_fresh_ds29_on_the_original_cap(archived_pair):
    plan = pair.preseal()
    assert plan["fresh"] == "DS29-0082"
    assert list(plan["inputs"]) == ["DS26-0036", "DS29-0082"]
    assert plan["runtime_max_s"] == 300
    assert plan["cpus"] == [18, 19]
    assert plan["memory_bytes"] == 512 * 1024**2
    assert plan["swap_bytes"] == 0


def test_pair_rejects_a_prior_cavity_without_the_same_memory_control(archived_pair):
    stages, folder = archived_pair
    stages["DS26-0036"]["position"]["end"]["memory.swap.max"] = 4096
    (folder / "stages.json.gz").write_bytes(gzip.compress(json.dumps(stages).encode()))
    with pytest.raises(ValueError, match="paired control"):
        pair.preseal()
