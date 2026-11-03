"""Known membership stress fixture independent of server labels or tracker code."""
import hashlib
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def identity(text):
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def main():
    out = HERE / "synthetic"
    out.mkdir(exist_ok=True)
    rng = np.random.default_rng(20261001)
    origin = 1700000000000000000
    spacing = 1 / 4.4e-6
    rows, mappings, members = [], [], [[], []]
    curves = [(-30000, -1800, 20), (60000, -3800, -10)]
    for visit, time in enumerate(np.arange(0., 60.01, .5)):
        source = identity(f"source:{visit}")
        center = origin + round(time*1e9)
        for rank, (intercept, rate, acceleration) in enumerate(curves):
            if (rank == 0 and 42 <= visit <= 45) or (rank == 1 and 72 <= visit <= 75):
                continue
            expected = intercept + rate*time + .5*acceleration*time*time
            measured = expected + rng.normal(0,75)
            raw = (measured+spacing/2)%spacing-spacing/2
            cid = identity(f"candidate:{visit}:{rank}")
            rows.append([cid,source,0,1,"lower",11200000000,center-10000000,
                         center,center+10000000,raw,.6,.05,.55])
            mappings.append([cid,source,visit,0,0,rank,"synthetic","truth"])
            members[rank].append({"candidate_id":cid,"source_group_id":source,
                                  "time_s":float(time),"measured_dealiased_hz":float(measured),
                                  "raw_hz":float(raw)})
        if visit % 4 == 0:
            cid = identity(f"clutter:{visit}")
            rows.append([cid,source,0,1,"lower",11200000000,center-10000000,
                         center,center+10000000,rng.uniform(-spacing/2,spacing/2),.13,.05,.08])
            mappings.append([cid,source,visit,0,0,2,"synthetic","clutter"])
    header = "candidate_id source_group_id receiver_id channel edge actual_rf_hz support_start_utc_ns support_center_utc_ns support_end_utc_ns measured_cfo_hz exact_score control_score margin".split()
    (out/"observations.tsv").write_text("\t".join(header)+"\n"+
        "".join("\t".join(map(str,row))+"\n" for row in rows))
    (out/"candidate-map.tsv").write_text(
        "candidate_id\tsource_group_id\tvisit\treceiver_id\tprobe_index\tcandidate_rank\tepoch_kind\tdetector_side\n"+
        "".join("\t".join(map(str,row))+"\n" for row in mappings))
    (out/"truth.json").write_text(json.dumps({"seed":20261001,"curves":curves,
        "model":"intercept + rate*t + 0.5*acceleration*t^2",
        "noise_std_hz":75,"members":members,"clutter_count":31,
        "scope":"Known synthetic membership, two crossing curved tracks, frequency aliases, two missing-data gaps; no target-scan labels."},indent=2)+"\n")
    print(json.dumps({"observations":len(rows),"track_lengths":list(map(len,members)),
                      "observations_sha256":hashlib.sha256((out/"observations.tsv").read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
