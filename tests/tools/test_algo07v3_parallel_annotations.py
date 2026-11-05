import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import check_algo07v3_parallel_annotations as tool
import pytest


@pytest.mark.parametrize("change", [None, "nominations", "attempts", "protocol", "result"])
def test_fixture_runner_uses_parallel_port_and_rejects_changed_losing_evidence(
    tmp_path, monkeypatch, change
):
    value = {k: {"losing_score": 2} for k in ("nominations", "attempts", "protocol", "result")}
    value["result"].update(annotation={"status": "unchanged_winner"}, folds=[{"proposals": [100]}])
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps(value))
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            dict(
                source=str(tmp_path),
                output=dict(
                    path=str(reference), sha256=hashlib.sha256(reference.read_bytes()).hexdigest()
                ),
                scan_identities=["scan"],
                track_id="track",
            )
        )
    )
    (tmp_path / "observations.json").write_text("{}")
    monkeypatch.setattr(tool, "source_bindings", lambda: {})
    monkeypatch.setattr(tool, "owned_context", lambda *a: {"scan": SimpleNamespace(tracks=[])})
    monkeypatch.setattr(tool, "baseline_pair", lambda *a: ({}, {}))
    monkeypatch.setattr(tool, "inventory", lambda *a, **k: {})
    monkeypatch.setattr(
        tool, "select_targets", lambda *a: ([dict(track_id="track", inactive_fragment=False)], 1)
    )
    monkeypatch.setattr(tool.serial, "annotate", lambda *a, **k: deepcopy(value))
    calls = []

    def parallel(*args, **kwargs):
        assert kwargs["map_folds"] is tool.map_predictive_folds
        calls.append(True)
        result = deepcopy(value)
        if change:
            result[change]["losing_score"] = 3
        return result

    monkeypatch.setattr(tool, "annotate", parallel)
    args = SimpleNamespace(fixture_receipt=[receipt], output=tmp_path / "output.json")
    if change:
        with pytest.raises(ValueError, match="Complete annotation differs"):
            tool.run(args)
        assert not args.output.exists()
    else:
        tool.run(args)
        result = json.loads(args.output.read_bytes())
        assert result["exact_all_annotation_fields"]
        assert result["rows"][0]["proposal_count"] == 1
        assert result["whole_pipeline_speedup"] is None
    assert calls == [True]
