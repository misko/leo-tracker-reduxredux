"""Read-only, frozen roof dual-RX opportunity and proxy evaluation."""
from __future__ import annotations

import hashlib, json, math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import zstandard as zstd

HERE = Path(__file__).resolve().parent
ANALYSIS = Path("/srv/bulk/leo/scanner-adaptive-analysis")
POSE = Path("/srv/bulk/leo/capture-pose/gauss-r20-roof-20260926-v1")
SESSIONS = ["scan-fw-2e6b78f0cd0cbbbc","scan-fw-3221795d82a1c7ec","scan-fw-195bdbb87ad09b7f","scan-fw-60d9d1e77c14da0a","scan-fw-cd6a029d633dcc0e","scan-fw-c78fb2dba2465361","scan-fw-c7e37f65ae9e08b0","scan-fw-5eaaa2a8f8c995b3"]
CAL=set(SESSIONS[:5]); HOLD=set(SESSIONS[5:]); FRAME=1/750; ALIAS=1/4.4e-6

def canonical(x): return json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(x): return "sha256:"+hashlib.sha256(x).hexdigest()
def circ(x,p): return x-round(x/p)*p
def read_zst(p): return json.loads(zstd.ZstdDecompressor().decompress(p.read_bytes()))["document"]

def load():
    rows=[]; inventory=[]
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    store=AdaptiveHopIqStore(Path("/srv/bulk/leo"),read_only=True)
    for si,sid in enumerate(SESSIONS):
        pose=json.loads((POSE/f"{sid}.json").read_text()); content={k:v for k,v in pose.items() if k!="binding_digest"}
        authority=pose["pose_authority"]
        authority_ok=digest(canonical(authority))==pose["pose_authority_digest"]
        inspected=store.inspect(sid)
        roots=list((ANALYSIS/sid).glob("*")); binds=sum((list(r.glob("binding.v*.json")) for r in roots),[])
        if len(binds)!=1: raise RuntimeError(f"{sid}: expected one binding, got {len(binds)}")
        binding=json.loads(binds[0].read_text()); files=sorted(binds[0].parent.glob("visit-*.json.zst"))
        expected=binding["document"]["receipt"]["complete_visit_count"]
        expected_ids={e["visit_index"] for e in binding["document"]["receipt"]["events"]}
        actual_ids={int(p.name.split("-")[1].split(".")[0]) for p in files}
        if len(expected_ids)!=expected or not actual_ids<=expected_ids: raise RuntimeError(f"invalid visit inventory: {sid}")
        source_ok=(inspected.manifest_sha256==pose["manifest_sha256"]==binding["document"]["input_manifest_sha256"])
        if not (authority_ok and digest(canonical(content))==pose["binding_digest"] and source_ok): raise RuntimeError(f"digest verification failed: {sid}")
        inventory.append(dict(session_id=sid,split="calibration" if sid in CAL else "holdout",capture_start_utc_ns=pose["capture_start_earliest_utc_ns"],capture_end_utc_ns=pose["capture_end_utc_ns"],manifest_sha256=pose["manifest_sha256"],store_inspect_manifest_sha256=inspected.manifest_sha256,pose_authority_digest=pose["pose_authority_digest"],pose_authority_digest_valid=authority_ok,binding_digest_valid=True,analysis_binding=binds[0].name,analysis_input_manifest_sha256=binding["document"]["input_manifest_sha256"],analysis_source_matches_pose=source_ok,expected_visit_ids_unique=len(expected_ids)==expected,published_visit_ids_unique=len(actual_ids)==len(files),sample_rate_hz=binding["document"]["configuration"]["sample_rate_hz"],complete_visits=expected,visit_files=len(files),missing_analysis_visits=len(expected_ids-actual_ids)))
        for p in files:
            d=read_zst(p); key=(sid,d["visit_index"],d["target"]["channel"],d["target"]["edge"])
            probe_keys=[(q["receiver_id"],q["probe_index"],q["probe_start_ms"]) for q in d["probes"]]
            if len(probe_keys)!=len(set(probe_keys)): raise RuntimeError(f"duplicate probe key: {sid} {d['visit_index']}")
            if len(d["probes"])!=2 or {q["receiver_id"] for q in d["probes"]}!={0,1}: raise RuntimeError(f"non-single paired probes: {sid} {d['visit_index']}")
            probes={q["receiver_id"]:q for q in d["probes"]}
            row=dict(key=key,session=sid,scan_index=si,visit=d["visit_index"],channel=d["target"]["channel"],edge=d["target"]["edge"],available=(0 in probes and 1 in probes),rx={})
            for rx in (0,1):
                q=probes.get(rx); cs=[] if q is None else [c for c in q["candidates"] if c["passed_fractional_margin_gate"]]
                row["rx"][rx]=dict(available=q is not None,detected=bool(cs),candidates=cs,best=max((c["fractional_margin"] for c in cs),default=None))
            rows.append(row)
    store.close()
    return inventory,rows

def possible_edges(row,bias=None):
    out=[]
    for i,a in enumerate(row["rx"][0]["candidates"]):
      for j,b in enumerate(row["rx"][1]["candidates"]):
        dt=circ(b["fractional_time_s"]-a["fractional_time_s"],FRAME)
        df=circ(b["fractional_tracking_cfo_hz"]-a["fractional_tracking_cfo_hz"],ALIAS)
        if abs(dt)<=2.2e-6 and (bias is None or abs(circ(df-bias,ALIAS))<=10000): out.append((i,j,dt,df,min(a["fractional_margin"],b["fractional_margin"])))
    return out

def fit_bias(rows):
    vals=[]
    for r in rows:
      if r["session"] in CAL:
       vals += [e[3] for e in possible_edges(r)]
    bins=np.arange(-ALIAS/2,ALIAS/2+5000,5000); h,e=np.histogram(vals,bins); k=int(np.argmax(h)); core=[x for x in vals if e[k]<=x<e[k+1]]
    return float(np.median(core)),len(vals),len(core)

def classify(rows,bias):
    output=[]
    for r in rows:
      if not r["available"]: cat="missing"
      else:
       d0=r["rx"][0]["detected"]; d1=r["rx"][1]["detected"]
       if d0 and d1: cat="both_matched" if possible_edges(r,bias) else "both_unmatched"
       elif d0: cat="rx0_only"
       elif d1: cat="rx1_only"
       else: cat="neither"
      x=dict(r);x["category"]=cat;x["match_count"]=len(possible_edges(r,bias));output.append(x)
    return output

def rates(rows, sessions, inventory):
    z={}
    for sid in sessions:
      rr=[r for r in rows if r["session"]==sid]; c=Counter(r["category"] for r in rr)
      missing=next(x["missing_analysis_visits"] for x in inventory if x["session_id"]==sid)
      z[sid]={"analyzed_visits":len(rr),"missing_analysis_visits":missing,"categories":dict(c),"rx0_detection_rate_analyzed":sum(r["rx"][0]["detected"] for r in rr)/len(rr),"rx1_detection_rate_analyzed":sum(r["rx"][1]["detected"] for r in rr)/len(rr)}
    return z

def baseline(rows, train):
    p={}
    for ch in range(1,5):
      for rx in (0,1):
       x=[r["rx"][rx]["detected"] for r in rows if r["session"] in train and r["channel"]==ch and r["available"]]
       p[(ch,rx)]=(sum(x)+.5)/(len(x)+1)
    return p

def score(rows,p,sessions):
    loss=[]
    for r in rows:
      if r["session"] not in sessions or not r["available"]:continue
      for rx in (0,1):
       q=p[(r["channel"],rx)]; y=r["rx"][rx]["detected"];loss.append(-math.log(q if y else 1-q))
    return {"observations":len(loss),"mean_log_loss":float(np.mean(loss))}

def main():
    inv,raw=load(); bias,nedge,ncore=fit_bias(raw); rows=classify(raw,bias)
    full=baseline(rows,CAL); repaired={SESSIONS[3],SESSIONS[4]}; post=baseline(rows,repaired)
    eligible_hold={x["session_id"] for x in inv if x["split"]=="holdout" and x["missing_analysis_visits"]==0}
    # Null pairing: seeded channel-preserving derangement, rejecting near-time (<100 visit) pairings.
    rng=np.random.default_rng(20260927)
    null=[]
    for sid in SESSIONS:
      for ch in range(1,5):
       q=[r for r in rows if r["session"]==sid and r["channel"]==ch]
       perm=np.roll(rng.permutation(len(q)),max(100,len(q)//3))
       for i,r in enumerate(q):
        x=dict(r);x["rx"]={0:r["rx"][0],1:q[int(perm[i])]["rx"][1]};null.append(x)
    null=classify(null,bias)
    out={"protocol":"PROTOCOL.md","cutoff_utc":"2026-09-27T01:01:48Z","inventory":inv,"pairing":{"epoch_tolerance_us":2.2,"epoch_period_hz":750,"cfo_alias_hz":ALIAS,"cfo_bias_hz":bias,"cfo_tolerance_hz":10000,"calibration_epoch_compatible_edges":nedge,"calibration_modal_edges":ncore,"warning":"tentative proxy matches only; thresholds are fixed symbol/frame tolerances and calibration-estimated receiver CFO bias; match multiplicity is ambiguity"},"opportunities":{"by_session":rates(rows,SESSIONS,inv),"eligible_complete_holdout_sessions":sorted(eligible_hold),"excluded_incomplete_holdout_sessions":sorted(HOLD-eligible_hold),"aggregate_calibration":dict(Counter(r["category"] for r in rows if r["session"] in CAL)),"aggregate_complete_holdout":dict(Counter(r["category"] for r in rows if r["session"] in eligible_hold)),"holdout_missing_analysis":sum(x["missing_analysis_visits"] for x in inv if x["split"]=="holdout"),"seeded_channel_shuffle_complete_holdout":dict(Counter(r["category"] for r in null if r["session"] in eligible_hold))},"m0":{"full_calibration_probabilities":{f"ch{k[0]}_rx{k[1]}":v for k,v in full.items()},"postrepair_sensitivity_probabilities":{f"ch{k[0]}_rx{k[1]}":v for k,v in post.items()},"complete_holdout_full":score(rows,full,eligible_hold),"complete_holdout_postrepair_sensitivity":score(rows,post,eligible_hold)},"gates":{"m1":"not attempted: proxy pairing has substantial ambiguity/null matches and only one analysis-complete holdout; candidate direction modeling cannot yet be trusted independently of reception outcome","m2":"unavailable: phase centers, elevation, beamwidth and world tilt not identified","position":"not run because M1 evidence gate failed"},"hardware_regimes":{"pre_repair":[SESSIONS[0],SESSIONS[1],SESSIONS[2]],"verified_postrepair_calibration":[SESSIONS[3],SESSIONS[4]],"holdout":"postrepair","note":"frozen pre-repair scans retained; RX0 broadband floor failure is a measured confound, not directional evidence"}}
    (HERE/"results.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({"bias":bias,"cal":out["opportunities"]["aggregate_calibration"],"hold":out["opportunities"]["aggregate_complete_holdout"],"null":out["opportunities"]["seeded_channel_shuffle_complete_holdout"],"scores":out["m0"]},indent=2))

if __name__=="__main__": main()
