"""Check native-winner parity and future-sample independence at the first deadline."""
import json
import hashlib
import numpy as np

from winner_to_fix import cold, winners, track_document, OUTPUT


def main():
    case="DS26-0002"
    doc=cold.read(cold.INPUT/case/"native.json")
    source=doc["source"]
    obs,meta,half_probe=winners(doc)
    expected=cold.read(cold.GRAPHS/f"{case}.json")
    official=sorted(expected["observations"],key=lambda r:(r["time_s"],r["receiver"],r["channel"]))
    keys=["receiver","channel","actual_rf_hz","time_s","measured_cfo_hz"]
    diff=np.max(np.abs(np.array([x[1:] for x in obs])-np.array([[x[k] for k in keys] for x in official])),axis=0)
    assert np.max(diff[:4]) < 1e-7 and diff[4]<1e-5
    assert all(meta[key]==expected["metadata"][key] for key in meta)
    deadline=60
    prefix=[r for r in obs if r[4]+half_probe<=deadline]
    src0=dict(source,probes=[p for p in source["probes"] if
              (p["valid_start_counter"]-doc["clock_anchor"]["sample_counter"])/source["sample_rate_hz"]+2*half_probe <= deadline])
    pruned=dict(doc,source=src0,last_sample_counter=doc["clock_anchor"]["sample_counter"]+int(deadline*source["sample_rate_hz"]))
    truncated,m0,half0=winners(pruned)
    assert half0==half_probe and m0["duration_s"]==60 and truncated==prefix
    a,ac=track_document(prefix)
    b,bc=track_document(truncated)
    assert ac==bc and a["curved_indices"]==b["curved_indices"]
    for x,y in zip(a["tracks"],b["tracks"],strict=True):
        assert all(np.array_equal(x[k],y[k]) for k in x)
    P=lambda n: {r["case"]:r["arms"] for r in cold.read(OUTPUT/f"winner-positions-{n}.json")["rows"] if r.get("deadline")=="full"}
    a,b=P(12),P(32)
    assert all(b[c]==a[c] for c in a)
    plan_path=cold.WORK/"plans/science.json"
    members=cold.read(plan_path)["cohorts"]["DS26"]["members"]
    verified=0
    for member in members:
        label=member["dataset_label"]
        if member["availability"]!="available":
            continue
        native_path=cold.INPUT/label/"native.json"
        track_path=cold.GRAPHS/(label+".json")
        receipt=cold.read(cold.GRAPHS/(label+"-receipt.json"))
        assert hashlib.sha256(native_path.read_bytes()).hexdigest()==member["input_sha256"].removeprefix("sha256:")
        assert hashlib.sha256(track_path.read_bytes()).hexdigest()==receipt["output_sha256"].removeprefix("sha256:")
        verified+=1
    output=dict(case=case,official_winners=len(official),max_parity_difference=dict(zip(keys,diff.tolist(),strict=True)),
                future_removed=dict(deadline_s=deadline,original_probes=len(source["probes"]),kept_probes=len(src0["probes"]),
                                    kept_winners=len(truncated),track_and_curvature_arrays_equal=True),
                repeated_12_panel_full_arms_exact=len(a),
                ds26_frozen_fast_members=len(members),matching_native_and_track_artifact_hashes=verified,
                science_manifest_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest())
    print(json.dumps(output,indent=2))
    (OUTPUT/"input-controls.json").write_text(json.dumps(output,allow_nan=False,indent=2))


if __name__=="__main__":
    main()
