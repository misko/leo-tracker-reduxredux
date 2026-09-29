"""Shared source-window checks and production artifact health; no writes to production."""
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from run import ROOT, SID, write, sha
from evaluate import inputs, panel, scientific


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
    from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
    from leo.scanner.adaptive_hop_analysis import analyze_adaptive_hop_visit
    from leo.application.scanner_trajectory import project_scanner_candidates

    checks = dict(shared_windows=0,exact_shared_candidate_equality=True,fresh_replays=[])
    spec=json.loads((ROOT/"spec.json").read_text())
    for name,digest in spec["code_hashes"].items():
        assert sha((Path(spec["release"])/"src/leo"/name).read_bytes()) == digest
    checks["pinned_detector_hashes_unchanged"]=True
    for row in panel():
        baseline=ROOT/f"local/baseline/{row['visit_index']:04}.json"
        assert sha(baseline.read_bytes()) == row["baseline_sha256"]
        a=json.loads(baseline.read_text())
        b=json.loads((ROOT/f"local/dense/{row['visit_index']:04}.json").read_text())
        assert a["input_manifest_sha256"] == b["input_manifest_sha256"] == spec["source_manifest_sha256"]
        assert a["valid_start_counter"] == b["valid_start_counter"]
        assert {k:v for k,v in a["configuration"].items() if k != "probe_stride_ms"} == {
            k:v for k,v in b["configuration"].items() if k != "probe_stride_ms"}
        for p in a["probes"]:
            q=next(q for q in b["probes"] if q["receiver_id"]==p["receiver_id"] and q["probe_start_ms"]==p["probe_start_ms"])
            assert p["candidates"] == q["candidates"], (row["visit_index"],p["receiver_id"])
            checks["shared_windows"]+=1
    store=AdaptiveHopIqStore(Path("/srv/bulk/leo"),read_only=True)
    try:
        capture=store.inspect(SID)
        with AdaptiveHopAnalysisInputStore(store).source(SID) as source:
            for stride in (120,20):
                cfg=bind_actual_visit_analysis(capture.manifest.receipt,
                    input_manifest_sha256=capture.manifest_sha256,probe_stride_ms=stride).configuration
                start=time.monotonic()
                result=analyze_adaptive_hop_visit(source,0,configuration=cfg).model_dump(mode="json")
                seconds=time.monotonic()-start
                dense=json.loads((ROOT/"local/dense/0000.json").read_text())
                for p in result["probes"]:
                    q=next(q for q in dense["probes"] if q["receiver_id"]==p["receiver_id"] and q["probe_start_ms"]==p["probe_start_ms"])
                    assert p["candidates"] == q["candidates"]
                checks["fresh_replays"].append(dict(stride_ms=stride,wall_seconds=seconds,probes=len(result["probes"]),exact_equality=True))
    finally:
        store.close()
    dense=project_scanner_candidates(inputs(10))
    control=project_scanner_candidates(inputs(20))
    a=[scientific(c) for c in dense]
    b=[scientific(c) for c in control]
    assert a == b
    checks["dense_control_projected_scientific_equality"]=True
    checks["projected_candidates_per_dense_control_arm"]=len(a)
    checks["projected_scientific_sha256"]=sha(json.dumps(a,sort_keys=True).encode())
    checks["http_checks"]=http_checks()
    write(ROOT/"validation.json",checks)
    print(json.dumps(checks))


def http_checks():
    old=json.loads((ROOT.parent/"2026_09_29_adaptive_glrt_audit/evidence.json").read_text())
    previous=next((s for s in old["sessions"] if s["session_id"]==SID),None)
    spec=json.loads((ROOT/"spec.json").read_text())
    checked=[]
    for stage,base,key,digestkey in (
        ("glrt",f"/api/v2/scanner/adaptive-sessions/{SID}/analysis","overview","binding_sha256"),
        ("phase",f"/api/v1/scanner/adaptive-sessions/{SID}/analysis/relative-phase","manifest","binding_sha256"),
    ):
        with urlopen("http://127.0.0.1:8090"+base+"?probe_stride_ms=120",timeout=20) as response:
            status=json.load(response)
        prior=(previous["analysis"]["120"] if stage=="glrt" else previous["relative_phase"]) if previous else None
        if stage=="glrt":
            assert status[digestkey]==spec["baseline_binding"]
        if prior:
            assert status[digestkey]==prior[digestkey]
        for artifact in status[key]["artifacts"]:
            if prior:
                prior_artifact=next(a for a in prior[key]["artifacts"] if a["name"]==artifact["name"])
                assert artifact["sha256"]==prior_artifact["sha256"]
            url="http://127.0.0.1:8090"+base+"/"+artifact["name"]+".png?"+urlencode(dict(
                probe_stride_ms=120,binding_sha256=status[digestkey],artifact_sha256=artifact["sha256"]))
            with urlopen(url,timeout=20) as response:
                payload=response.read()
                assert response.status==200 and response.headers.get_content_type()=="image/png"
                assert payload.startswith(b"\x89PNG\r\n\x1a\n")
                assert "sha256:"+sha(payload)==artifact["sha256"] and len(payload)==artifact["byte_count"]
            checked.append(dict(stage=stage,name=artifact["name"],url=url,status=200,manifest_digest_verified=True,
                                compared_with_prior_snapshot=prior is not None))
    base=f"http://127.0.0.1:8090/api/v1/scanner/tracking/{SID}"
    with urlopen(base,timeout=20) as response:
        tracking=json.load(response)
    prior=previous["tracking"]["product"] if previous else None
    assert tracking["state"] == "complete"
    if prior:
        assert tracking["product"]["analysis_manifest_sha256"] == prior["analysis_manifest_sha256"]
    for artifact in tracking["product"]["artifacts"]:
        if prior:
            old_artifact=next(a for a in prior["artifacts"] if a["name"]==artifact["name"])
            assert old_artifact["sha256"] == artifact["sha256"]
        url=base+"/"+artifact["name"]+".png"
        with urlopen(url,timeout=20) as response:
            payload=response.read()
            assert response.status == 200 and response.headers.get_content_type()=="image/png"
            assert payload.startswith(b"\x89PNG\r\n\x1a\n") and "sha256:"+sha(payload)==artifact["sha256"]
            assert len(payload)==artifact["byte_count"]
        checked.append(dict(stage="tracking",name=artifact["name"],url=url,status=200,manifest_digest_verified=True,
                            compared_with_prior_snapshot=prior is not None))
    return checked


if __name__ == "__main__":
    main()
