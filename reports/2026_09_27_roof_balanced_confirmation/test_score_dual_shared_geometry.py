import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import score_dual_shared_geometry as subject


SESSIONS=("s0","s1","s2","s3")
PRIORS={"sacramento":(1.,2.,3.),"reno":(4.,5.,6.)}
CODE_FILES=("run_dual_shared_geometry.py","dual_shared_effect_evaluator.py",
            "shared_effect_evaluator.py","ratio_random_intercept.py",
            "detection_random_intercept_refined.py","mixture_geometry_models.py",
            "paired_reception_evaluator.py","run_shared_geometry_replay.py",
            "run_consistent_replay.py")


def digest(payload): return "sha256:"+hashlib.sha256(payload).hexdigest()
def write(path,value): path.write_text(json.dumps(value)); return digest(path.read_bytes())


def setup_fake(monkeypatch,tmp_path,corrupt=False):
    entries=[{"session_id":sid,"cache_sha256":"c"+sid,"input_manifest_sha256":"i"+sid,
              "analysis_manifest_sha256":"a"+sid} for sid in SESSIONS]
    monkeypatch.setattr(subject,"HERE",tmp_path)
    monkeypatch.setattr(subject.runner.balanced,"inputs",lambda:(entries,{}))
    monkeypatch.setattr(subject.runner.base,"PRIORS",PRIORS)
    monkeypatch.setattr(subject.runner.base,"digest",digest)
    monkeypatch.setattr(subject.runner.base,"atomic",lambda p,v:p.write_text(json.dumps(v)))
    bundle=SimpleNamespace(calibration_sha256="cal",calibration_sessions=("x",),
        source_hashes={"s":"h"},artifact_sha256={"a":"b"})
    monkeypatch.setattr(subject.runner.mixture_geometry_models,"load_geometry_bundle",lambda:bundle)
    ratio={"aggregate_sha256":"ratio"};detect={"aggregate_sha256":"detect"}
    monkeypatch.setattr(subject.runner,"ratio_effect_binding",lambda:(ratio,.25))
    monkeypatch.setattr(subject.runner.source_runner,"random_effect_binding",lambda:(detect,2.5))
    for name in CODE_FILES+("score_dual_shared_geometry.py","dual_shared_geometry_reporting.py",
                            "shared_geometry_reporting.py","score_consistent_replay.py"):
        (tmp_path/name).write_text(name)
    contract=write(tmp_path/"contract.json",{"x":1})
    protocol=write(tmp_path/"DUAL_SHARED_GEOMETRY_PROTOCOL.md",{"x":1})
    grid_report=write(tmp_path/"local-grid-distances.json",{"complete":True})
    audit=write(tmp_path/"audit_source_topology.json",{})
    source_report={"complete":True,"replay_sha256":{}}; sources={}
    for sid in SESSIONS:
        grid={"finished":True,"session_id":sid,"deduplicate_reception":False,
              "branches":{p:{"grid":p} for p in PRIORS}}
        grid_sha=write(tmp_path/f"local-grid-{sid}.json",grid)
        source={"finished":True,"session_id":sid,"source_grid_sha256":grid_sha,
            "evidence_sha256":"e"+sid,"snapshot_digest":"n"+sid,
            "topology_receipt":{"sid":sid},"parameters":{"p":1},"model_hashes":{"m":1},
            "branches":{p:{"origin":list(PRIORS[p][:2])} for p in PRIORS}}
        source_sha=write(tmp_path/f"shared-geometry-replay-{sid}.json",source)
        source_report["replay_sha256"][sid]=source_sha;sources[sid]=source
    source_report_sha=write(tmp_path/"shared-geometry-distances.json",source_report)
    common={"contract_sha256":contract,"dual_shared_geometry_protocol_sha256":protocol,
        "ratio_effect_binding":ratio,"detection_effect_binding":detect,
        "calibration_sha256":"cal","calibration_sessions":["x"],
        "calibration_source_hashes":{"s":"h"},"calibration_artifact_sha256":{"a":"b"},
        "source_replay_report_sha256":source_report_sha,
        "source_grid_report_sha256":grid_report,"topology_audit_sha256":audit}
    code={name:digest((tmp_path/name).read_bytes()) for name in CODE_FILES}
    for number,entry in enumerate(entries):
        sid=entry["session_id"];source=sources[sid]
        result={**common,**entry,"session_id":sid,"finished":True,
            "source_replay_sha256":source_report["replay_sha256"][sid],
            "source_grid_sha256":source["source_grid_sha256"],
            "evidence_sha256":source["evidence_sha256"],"snapshot_digest":source["snapshot_digest"],
            "topology_receipt":source["topology_receipt"],"parameters":source["parameters"],
            "model_hashes":source["model_hashes"],"code_sha256":code,
            "branches":{p:{"origin":list(PRIORS[p][:2]),"parity":{"ok":True},
                           "point_components":[],"selected":{}} for p in PRIORS}}
        if corrupt and number==0:result["ratio_effect_binding"]={"changed":True}
        write(tmp_path/f"dual-shared-geometry-replay-{sid}.json",result)
    write(tmp_path/"manifest.json",{"sessions":[{"pose":{"session_id":sid,
        "pose_authority":{"latitude_deg":10.,"longitude_deg":20.}}} for sid in SESSIONS]})
    monkeypatch.setattr(subject.reporting,"validate_branch",lambda saved,result:{"selected":result["selected"]})
    monkeypatch.setattr(subject.runner,"parity_report",lambda source,rows:{"ok":True})
    monkeypatch.setattr(subject.reporting,"distance_row",lambda sid,p,*args:{"session_id":sid,"prior":p,
        "errors_km":{"D":1.,"old":1.,"detection":1.,"dual":1.}})
    monkeypatch.setattr(subject.reporting,"summarize",lambda rows,sessions:{"rows":len(rows),"sessions":len(sessions)})


def test_complete_fake_eight_case_report(monkeypatch,tmp_path):
    setup_fake(monkeypatch,tmp_path);subject.main()
    out=json.loads((tmp_path/"dual-shared-geometry-distances.json").read_text())
    assert out["complete"] and len(out["rows"])==8
    assert out["summary"]=={"rows":8,"sessions":4}
    assert set(out["replay_sha256"])==set(SESSIONS)


def test_reporter_code_inventory_exactly_matches_live_producer_receipt():
    tree = ast.parse(Path(subject.runner.__file__).read_text())
    receipts = [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "output"
                        and isinstance(target.slice, ast.Constant)
                        and target.slice.value == "code_sha256"
                        for target in node.targets)]
    assert len(receipts) == 1 and isinstance(receipts[0], ast.DictComp)
    producer_files = ast.literal_eval(receipts[0].generators[0].iter)
    assert subject.PRODUCER_CODE_FILES == producer_files == CODE_FILES


def test_binding_failure_precedes_reference_open(monkeypatch,tmp_path):
    setup_fake(monkeypatch,tmp_path,True);original=Path.read_bytes;opened=[]
    def guarded(path):
        if path.name=="manifest.json":opened.append(path);raise AssertionError("reference opened early")
        return original(path)
    monkeypatch.setattr(Path,"read_bytes",guarded)
    with pytest.raises(ValueError,match="binding changed"):subject.main()
    assert opened==[]
