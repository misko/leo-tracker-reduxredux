"""Explicit research adapter to the unchanged production trajectory functions."""

import argparse
import dataclasses
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path

from run import ROOT, SID, sha, write

PERIOD = 1 / 4.4e-6
RF = 11_200_000_000.0


def canonical(frequency):
    return (frequency + PERIOD / 2) % PERIOD - PERIOD / 2


def panel():
    return [r for r in json.loads((ROOT / "spec.json").read_text())["rows"] if r["end_s"] <= 30]


def products(arm):
    result = []
    for row in panel():
        directory = "baseline" if arm == 120 else "dense"
        p = json.loads((ROOT / f"local/{directory}/{row['visit_index']:04}.json").read_text())
        if arm == 20:
            p["probes"] = [q for q in p["probes"] if q["probe_start_ms"] % 20 == 0]
            for q in p["probes"]:
                q["probe_index"] = q["probe_start_ms"] // 20
            p["configuration"]["probe_stride_ms"] = 20
        result.append(p)
    return result


def inputs(arm, partition=None):
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
    from leo.contracts.digests import canonical_digest

    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    try:
        capture = store.inspect(SID)
    finally:
        store.close()
    manifest, receipt = capture.manifest, capture.manifest.receipt
    spec = json.loads((ROOT / "spec.json").read_text())
    assert capture.manifest_sha256 == spec["source_manifest_sha256"]
    offsets, cursor = {}, 0
    for e in receipt.events:
        offsets[e.visit_index] = cursor
        cursor += e.valid_end_counter_exclusive - e.valid_start_counter
    allowed = {r["visit_index"] for r in panel() if partition is None or r["partition"] == partition}
    values = [p for p in products(arm) if p["visit_index"] in allowed]
    probes = []
    for p in values:
        e = receipt.events[p["visit_index"]]
        for q in p["probes"]:
            probes.append(TrackingProbe(p["visit_index"], q["receiver_id"], q["probe_index"],
                q["probe_start_ms"], p["target"]["channel"], p["target"]["edge"],
                float(p["target"]["rf_center_hz"]-e.actual_if_offset_hz),
                int(p["valid_start_counter"]), offsets[p["visit_index"]],
                tuple(TrackingCandidate(**{k:c[k] for k in TrackingCandidate.__dataclass_fields__})
                      for c in q["candidates"])))
    return TrackingInput(SID, "adaptive", receipt.plan.geometry.sample_rate_hz,
        receipt.radio_id, f"adaptive-iio-{receipt.stream_generation:016x}",
        capture.manifest_sha256, canonical_digest(values),
        canonical_digest({"capture":capture.manifest_sha256,"iq":manifest.uncompressed_sha256}),
        manifest.timing, receipt.terminal.state == "completed" and receipt.source_span_attested,
        tuple(probes), capture_start_utc_ns=manifest.timing.first_sample_estimate_utc_ns)


def reference_choice(candidates):
    """Complete-link, fixed-interval clusters; never consult a fitted prediction."""
    ordered = sorted(candidates, key=lambda c:canonical(c.measured_cfo_hz))
    clusters = []
    for c in ordered:
        if not clusters or canonical(c.measured_cfo_hz)-canonical(clusters[-1][0].measured_cfo_hz) > 2500:
            clusters.append([])
        clusters[-1].append(c)
    if len(clusters) != 1:
        return None, "no-passing-candidate" if not clusters else "multiple-frequency-clusters"
    return max(clusters[0], key=lambda c:(c.margin,-c.candidate_rank)), "eligible"


def prepare():
    from leo.application.scanner_trajectory import project_scanner_candidates
    if (ROOT / "references.json").exists():
        raise RuntimeError("Reference table already frozen")
    source = inputs(120, "evaluation")
    candidates = project_scanner_candidates(source)
    refs = []
    for row in panel():
        if row["partition"] != "evaluation":
            continue
        for rx in (0,1):
            subset = [c for c in candidates if c.visit_index == row["visit_index"] and c.receiver_id == rx]
            chosen, reason = reference_choice(subset)
            ref = dict(visit_index=row["visit_index"],receiver_id=rx,reason=reason,
                       hypotheses=[dataclasses.asdict(c) for c in subset])
            if chosen:
                ref.update(candidate_id=chosen.candidate_id,lane=list(chosen.lane_key),
                    utc_ns=chosen.support_center_utc_ns,
                    time_s=(chosen.support_center_utc_ns-source.capture_start_utc_ns)/1e9,
                    normalized_frequency_hz=canonical(chosen.measured_cfo_hz)*RF/chosen.actual_rf_hz)
            refs.append(ref)
    rows = panel()
    for left,right in zip(rows,rows[1:]):
        assert left["end_counter"] <= right["start_counter"], "Visit sample spans overlap"
    write(ROOT / "references.json",dict(rows=refs,partition_sha256=sha((ROOT/"spec.json").read_bytes()),
        amendment_sha256=sha((ROOT/"protocol-amendment.md").read_bytes()),
        origin_utc_ns=source.capture_start_utc_ns))
    print(json.dumps(dict(visits=len(rows),partitions=dict(Counter(r["partition"] for r in rows)),
                         references=dict(Counter(r["reason"] for r in refs)))))


def scientific(c):
    return {k:v for k,v in dataclasses.asdict(c).items()
            if k not in ("candidate_id","source_group_id","probe_index")}


def predict(track, utc_ns):
    return track["normalized_intercept_hz"] + track["normalized_rate_hz_per_s"] * (utc_ns-track["reference_utc_ns"])/1e9


def match_tracks(left,right):
    choices=[]
    for i,a in enumerate(left):
        period = PERIOD*RF/a["lane_key"][3]
        for j,b in enumerate(right):
            if a["lane_key"] != b["lane_key"]:
                continue
            lo=max(a["start_utc_ns"],b["start_utc_ns"])
            hi=min(a["end_utc_ns"],b["end_utc_ns"])
            if hi-lo < 4e9:
                continue
            shift=round((predict(a,(lo+hi)//2)-predict(b,(lo+hi)//2))/period)*period
            discrepancy=max(abs(predict(a,t)-predict(b,t)-shift) for t in (lo,hi))
            if discrepancy <= 2500:
                choices.append(dict(left=i,right=j,shift_hz=shift,max_difference_hz=discrepancy))
    nl=Counter(c["left"] for c in choices)
    nr=Counter(c["right"] for c in choices)
    accepted=[c for c in choices if nl[c["left"]] == nr[c["right"]] == 1]
    return dict(accepted=accepted,compatible=choices,
        unmatched_left=[i for i in range(len(left)) if not any(c["left"]==i for c in accepted)],
        unmatched_right=[j for j in range(len(right)) if not any(c["right"]==j for c in accepted)])


def fit(arm,partition):
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import reconstruct_persistent_hop_trajectories
    destination=ROOT / f"local/tracks-{arm}-{partition}.json"
    if destination.exists():
        raise RuntimeError("Track models are already frozen")
    source = inputs(arm, partition if partition == "training" else None)
    candidates = project_scanner_candidates(source)
    start=time.monotonic()
    result=reconstruct_persistent_hop_trajectories(candidates)
    output=dict(arm=arm,partition=partition,analysis_manifest_sha256=source.analysis_manifest_sha256,
                input_probes=len(source.probes),projected_candidates=len(candidates),
                fitting_seconds=time.monotonic()-start,result=dataclasses.asdict(result))
    # Episode graphs are Pydantic contracts nested in the dataclass result.
    output=json.loads(json.dumps(output, default=lambda x:x.model_dump(mode="json")))
    write(destination,output)
    print(json.dumps({k:v for k,v in output.items() if k != "result"}),flush=True)


def score():
    reference=json.loads((ROOT/"references.json").read_text())
    assert reference["amendment_sha256"] == sha((ROOT/"protocol-amendment.md").read_bytes())
    data={a:json.loads((ROOT/f"local/tracks-{a}-training.json").read_text()) for a in (120,10,20)}
    tracks={a:d["result"]["tracklets"] for a,d in data.items()}
    matches={a:match_tracks(tracks[120],tracks[a]) for a in (10,20)}
    ledger=[]
    for ref in reference["rows"]:
        row={k:v for k,v in ref.items() if k != "hypotheses"}
        row["predictions"]={}
        if ref["reason"] != "eligible":
            ledger.append(row)
            continue
        active=[i for i,t in enumerate(tracks[120]) if t["lane_key"]==ref["lane"]
                and t["start_utc_ns"]<=ref["utc_ns"]<=t["end_utc_ns"]]
        if len(active) != 1:
            row["reason"]="no-baseline-span" if not active else "ambiguous-baseline-span"
            ledger.append(row)
            continue
        i=active[0]
        a=tracks[120][i]
        period=PERIOD*RF/a["lane_key"][3]
        anchor=(a["start_utc_ns"]+a["end_utc_ns"])//2
        branch_shift=-round(predict(a,anchor)/period)*period
        row["baseline_track_index"]=i
        for arm in (120,10,20):
            if arm == 120:
                track,shift=a,branch_shift
            else:
                matched=[m for m in matches[arm]["accepted"] if m["left"]==i]
                if len(matched)!=1:
                    row["predictions"][str(arm)]={"reason":"unmatched-or-ambiguous-track"}
                    continue
                m=matched[0]
                track=tracks[arm][m["right"]]
                shift=branch_shift+m["shift_hz"]
            if not track["start_utc_ns"]<=ref["utc_ns"]<=track["end_utc_ns"]:
                row["predictions"][str(arm)]={"reason":"outside-training-span"}
                continue
            value=predict(track,ref["utc_ns"])+shift
            if not -period/2<=value<period/2:
                row["predictions"][str(arm)]={"reason":"outside-fixed-canonical-branch","prediction_hz":value}
                continue
            row["predictions"][str(arm)]={"reason":"scored","prediction_hz":value,
                "error_hz":ref["normalized_frequency_hz"]-value}
        ledger.append(row)
    common=[r for r in ledger if all(r["predictions"].get(str(a),{}).get("reason")=="scored" for a in (120,10,20))]
    eligible=sum(r["reason"]=="eligible" for r in reference["rows"])
    summary={}
    for a in (120,10,20):
        errors=[r["predictions"][str(a)]["error_hz"] for r in common]
        available=sum(r["predictions"].get(str(a),{}).get("reason")=="scored" for r in ledger)
        summary[a]=dict(eligible_references=eligible,available=available,
            availability_fraction=available/eligible if eligible else None,common_count=len(errors),
            common_rms_hz=math.sqrt(sum(e*e for e in errors)/len(errors)) if errors else None,
            per_track=[dict(baseline_track_index=i,count=len(es),rms_hz=math.sqrt(sum(e*e for e in es)/len(es)))
                for i in sorted({r["baseline_track_index"] for r in common})
                if (es:=[r["predictions"][str(a)]["error_hz"] for r in common if r["baseline_track_index"]==i])])
        abs_errors=sorted(abs(e) for e in errors)
        summary[a]["median_absolute_error_hz"]=statistics.median(abs_errors) if abs_errors else None
        if abs_errors:
            position=.95*(len(abs_errors)-1)
            low,high=math.floor(position),math.ceil(position)
            summary[a]["p95_absolute_error_hz"]=abs_errors[low]+(position-low)*(abs_errors[high]-abs_errors[low])
        else:
            summary[a]["p95_absolute_error_hz"]=None
        summary[a]["common_unique_visits"]=len({r["visit_index"] for r in common})
    write(ROOT/"scores.json",dict(summary=summary,matches=matches,ledger=ledger,
        reference_sha256=sha((ROOT/"references.json").read_bytes()),
        frozen_models_sha256={a:sha((ROOT/f"local/tracks-{a}-training.json").read_bytes()) for a in (120,10,20)}))
    print(json.dumps(summary),flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("prepare","fit","score"))
    parser.add_argument("--arm",type=int,choices=(120,10,20),default=120)
    parser.add_argument("--partition",choices=("operational","training"),default="training")
    args=parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "fit":
        fit(args.arm,args.partition)
    else:
        score()
