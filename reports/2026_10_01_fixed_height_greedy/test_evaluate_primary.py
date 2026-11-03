import hashlib,importlib.util,json,sys
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("primary_eval",HERE/"evaluate_primary.py");assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=module;SPEC.loader.exec_module(module)


def test_direct_frozen_source_root_is_indexed_when_live_source_changed(tmp_path):
    helper=module.helpers();live=tmp_path/"live.py";live.write_text("changed\n")
    frozen=tmp_path/"snapshot-0.py";frozen.write_text("frozen\n")
    digest="sha256:"+hashlib.sha256(frozen.read_bytes()).hexdigest()
    (tmp_path/"bindings.json").write_text(json.dumps({str(live):{
        "sha256":digest,"snapshot":str(frozen)}}))
    verified=helper.verify_source_bindings({str(live):digest},helper.snapshot_index(tmp_path))
    assert verified==[{"source":str(live),"sha256":digest,
        "verified_via":"archived_snapshot","snapshot":str(frozen)}]


def test_publication_requires_exact_panel(monkeypatch):
    monkeypatch.setattr(module,"selected_units",lambda:[f"U{i}" for i in range(64)])
    with pytest.raises(ValueError,match="missing=1"):module.require_complete_panel({f"U{i}":{} for i in range(63)})
    module.require_complete_panel({f"U{i}":{} for i in range(64)})


def test_launch_only_failure_is_retained(monkeypatch):
    monkeypatch.setattr(module,"selected_units",lambda:["U"])
    records={"U":{"unit_id":"U","sealed":False,"launch_path":"launch.json",
        "launch":{"status":"timeout","wall_seconds":90}}}
    row=module.evaluate(records)["rows"][0]
    assert row["attempted"] and not row["sealed"] and row["status"]=="timeout"
    assert row["error_m"] is None and row["processing_complete"] is False


def test_acceptance_requires_seal_launcher_native_convergence_and_budget(monkeypatch):
    monkeypatch.setattr(module,"selected_units",lambda:["U"])
    receipt={"status":"converged_local_mode","best":{"mean":[1.,2.],"converged":True,
             "iterations":3,"associations":["1"]},"fits":[],"planned_factors":1}
    base={"unit_id":"U","sealed":True,"receipt":receipt,"receipt_path":"r","receipt_sha256":"sha256:x",
          "launch_path":"l","launch":{"status":"complete","returncode":0,"wall_seconds":89.}}
    row=module.evaluate({"U":base})["rows"][0]
    assert row["native_numerically_converged"] and row["accepted"] and row["error_m"] is not None
    for change,reason in [({"sealed":False},"unsealed"),
                          ({"launch":{"status":"error","returncode":1,"wall_seconds":20.}},"launcher_not_successful"),
                          ({"launch":{"status":"complete","returncode":0,"wall_seconds":91.}},"runtime_above_90s_or_missing")]:
        attempt={**base,**change};bad=module.evaluate({"U":attempt})["rows"][0]
        assert bad["native_numerically_converged"] and not bad["accepted"] and bad["error_m"] is None
        assert reason in bad["acceptance_failures"]
