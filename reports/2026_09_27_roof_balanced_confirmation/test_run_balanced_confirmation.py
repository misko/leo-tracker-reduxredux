import json
import pytest
import run_balanced_confirmation as runner


def test_inputs_refuses_changed_bound_file(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'HERE',tmp_path)
    bound=tmp_path/'bound';bound.write_text('changed')
    (tmp_path/'contract.json').write_text(json.dumps(dict(files={str(bound):'sha256:old'},session_ids=[])))
    with pytest.raises(ValueError,match='contract mismatch'):runner.inputs()


def test_inputs_refuses_reordered_cohort(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'HERE',tmp_path)
    (tmp_path/'contract.json').write_text(json.dumps(dict(files={},session_ids=['a','b','c','d'])))
    (tmp_path/'inventory.json').write_text(json.dumps([dict(session_id=x) for x in ['b','a','c','d']]))
    with pytest.raises(ValueError,match='membership'):runner.inputs()
