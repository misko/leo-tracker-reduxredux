"""Bounded saved-IQ specificity test for a new relative-receiver observable."""

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from ds23_cross_receiver_carrier import circular_delta,cross_carrier
from fast_local_pilot_refinement import FastPilotWorkspace
from local_pilot_refinement import pilot_wave
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_cross_receiver_carrier"
PANELS=[ROOT/"reports/2026_10_19_ds23_raw_pilot_refinement"/(case+"_tracks_panel.npz") for case in ("DS23-0202","DS23-0274")]
SOURCE=ROOT/"reports/2026_10_19_algo02_ds23_full"


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/"protocol.json"
    if path.exists():raise FileExistsError("preserve RF-only selection")
    pool=[]
    for panel in PANELS:
        with np.load(panel,allow_pickle=False) as z:metadata=json.loads(str(z["metadata_json"]))
        case=metadata["case"];document=read(SOURCE/case/"tracking.json");source=document.get("source",document)
        lookup={(p["visit_index"],p["receiver_id"]):p for p in source["probes"]}
        seen=set()
        for point in metadata["points"]:
            key=point["window_key"]
            if key in seen:continue
            seen.add(key);probes=[lookup.get((point["visit_index"],rx)) for rx in (0,1)]
            if any(p is None for p in probes):continue
            if any(p["channel"]!=point["channel"] or p["actual_rf_hz"]!=point["rf_hz"] for p in probes):raise ValueError("paired receiver RF differs")
            candidates=[[p for p in row["candidates"] if p["passed_fractional_margin_gate"]] for row in probes]
            pairs=[];period=metadata["sample_rate_hz"]/750
            for a in candidates[0]:
                for b in candidates[1]:
                    ea=a["integer_epoch_sample"]+a["fractional_epoch_offset_samples"]
                    eb=b["integer_epoch_sample"]+b["fractional_epoch_offset_samples"]
                    delta=circular_delta(eb,ea,period)
                    if abs(delta)<=2.:pairs.append((min(a["fractional_margin"],b["fractional_margin"]),a,b,ea,ea+delta))
            if not pairs:continue
            score,a,b,ea,eb=max(pairs,key=lambda p:p[0])
            pool.append(dict(case=case,panel=str(panel.relative_to(ROOT)),window_key=key,channel=point["channel"],
                edge=point["edge"],rf_hz=point["rf_hz"],sample_rate_hz=metadata["sample_rate_hz"],visit_index=point["visit_index"],
                sample_counter=point["sample_counter"],epochs=[ea,eb],peaks=[a,b],minimum_native_margin=score))
    # Two strongest eligible windows per channel, selected before any coherence
    # measurement. Every selected window retains both synchronized RX streams.
    groups=defaultdict(list)
    for row in pool:groups[row["case"],row["channel"]].append(row)
    selected=[]
    for key,rows in sorted(groups.items()):selected+=sorted(rows,key=lambda r:(-r["minimum_native_margin"],r["visit_index"]))[:2]
    if len(selected)>32:raise ValueError("bounded two-case/eight-channel panel exceeded")
    write(path,dict(selected=selected,eligible_same_epoch_pairs=len(pool),selection="two maximum minimum-margin same-epoch dual-RX windows per case/channel",
        epoch_proximity_samples=2.,no_GPS_TLE_or_satellite_label_used=True,no_new_RF_or_raw_recording_read=True,
        raw_IQ_is_preexisting_local_panel_only=True,workers=8,
        specificity_controls="opposite receiver from different saved window of same case/channel, pilot component projected out",
        no_coherence_threshold_selected_from_position_accuracy=True,no_calibration_or_position_update=True,
        panel_sha256={str(p.relative_to(ROOT)):sha(p) for p in PANELS},source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/"tools/ds23_cross_receiver_carrier.py")))
    print("selected",len(selected),"from",len(pool),"RF-only same-epoch pairs",flush=True)


def project_pilot(samples,fs,edge,epoch,center):
    workspace=FastPilotWorkspace(samples,fs,edge,epoch)
    fit=workspace.fast_joint_fit(center)
    template=workspace.replica(fit["offset_samples"],fit["modulation_ppm"])*np.exp(2j*np.pi*fit["CFO_hz"]*(workspace.t-workspace.mid))
    residual=np.zeros_like(samples,dtype=complex);frames=[]
    for ix in workspace.frames:
        s=template[ix]-template[ix].mean();y=samples[ix]-samples[ix].mean()
        coefficient=np.vdot(s,y)/np.vdot(s,s).real
        residual[ix]=y-coefficient*s;frames.append(coefficient)
    return residual,fit


def run():
    protocol=read(OUT/"protocol.json")
    if protocol["source_sha256"]!=sha(Path(__file__)):raise ValueError("selection code changed")
    if (OUT/"results.json").exists():raise FileExistsError("preserve observable test")
    panels={p:np.load(ROOT/p,allow_pickle=False) for p in protocol["panel_sha256"]}
    for path,digest in protocol["panel_sha256"].items():
        if sha(ROOT/path)!=digest:raise ValueError("saved IQ panel changed")
    for edge in ("lower","upper"):pilot_wave(2500000,edge)
    def one(index,row):
        values=panels[row["panel"]][row["window_key"]]
        if values.shape!=(50000,2,2):raise ValueError("same 20ms dual receiver support required")
        samples=[values[:,k,0].astype(float)+1j*values[:,k,1].astype(float) for k in (0,1)]
        residuals=[];fits=[]
        for k in (0,1):
            residual,fit=project_pilot(samples[k],row["sample_rate_hz"],row["edge"],row["epochs"][k],row["peaks"][k]["fractional_tracking_cfo_hz"])
            residuals.append(residual);fits.append(fit)
        raw=cross_carrier(*samples,row["sample_rate_hz"])
        projected=cross_carrier(*residuals,row["sample_rate_hz"])
        native_delta=row["peaks"][1]["fractional_tracking_cfo_hz"]-row["peaks"][0]["fractional_tracking_cfo_hz"]
        return index,dict(entry=row,raw=raw,pilot_projected=projected,fits=fits,
            native_differential_CFO_hz=native_delta,
            projected_minus_native_alias_wrapped_hz=circular_delta(projected["differential_CFO_hz"],native_delta,1/4.4e-6)),residuals
    results={};residuals={};started=time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=protocol["workers"]) as executor:
            for future in as_completed([executor.submit(one,k,row) for k,row in enumerate(protocol["selected"])]):
                k,result,r=future.result();results[k]=result;residuals[k]=r
                print("measured",k,result["entry"]["case"],result["entry"]["channel"],"coherence",result["pilot_projected"]["coherent_fraction"],flush=True)
        for k,result in results.items():
            entry=result["entry"]
            controls=[j for j,r in results.items() if j!=k and (r["entry"]["case"],r["entry"]["channel"])==(entry["case"],entry["channel"])]
            result["different_window_controls"]=[dict(other_window=results[j]["entry"]["window_key"],
                **cross_carrier(residuals[k][0],residuals[j][1],entry["sample_rate_hz"])) for j in controls]
        write(OUT/"results.json",dict(rows=[results[k] for k in sorted(results)],seconds=time.monotonic()-started,
            protocol_sha256=sha(OUT/"protocol.json"),no_GPS_TLE_or_satellite_label_used=True,
            no_position_or_receiver_calibration_updated=True,
            coherence_is_not_DOA_or_satellite_identity_proof=True,
            common_hardware_leakage_or_unmodeled_pilots_need_separate_qualification=True))
    finally:
        for panel in panels.values():panel.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--stage",choices=["prepare","measure"],required=True)
    args=parser.parse_args();prepare() if args.stage=="prepare" else run()
