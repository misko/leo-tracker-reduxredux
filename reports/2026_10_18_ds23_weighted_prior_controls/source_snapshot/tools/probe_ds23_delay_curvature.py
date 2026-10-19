"""Qualify archived GLRT frame-epoch curvature as independent position evidence.

No pseudorange claim is made. Phase integers and clock-affine fits are diagnostic.
"""

import argparse
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from investigate_algo01_ds23_0217 import problem
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,read,write,final_scan,sha
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km

OUT=ROOT/"reports/2026_10_18_ds23_delay_curvature"


def detrend(times,values):
    t=np.asarray(times)
    x=np.column_stack((np.ones(len(t)),t-t.mean()))
    a=np.linalg.lstsq(x,values,rcond=None)[0]
    return values-x@a,a


def epoch_rows(document,observations):
    fs=document["sample_rate_hz"]
    origin=document["timing"]["session_start_device_sample_counter"]
    lookup={(o["native_receiver_id"],o["valid_start_counter"]):o for o in observations}
    result={}
    for probe in document["probes"]:
        eligible=[c for c in probe["candidates"] if c["passed_fractional_margin_gate"]]
        if not eligible:continue
        peak=max(eligible,key=lambda c:(c["fractional_margin"],-c["candidate_rank"]))
        start=probe["valid_start_counter"]+round(probe["probe_start_ms"]*fs/1000)
        o=lookup[probe["receiver_id"],start]
        assert abs(o["measured_cfo_hz"]-peak["fractional_tracking_cfo_hz"])<1e-8
        epoch=peak["integer_epoch_sample"]+peak["fractional_epoch_offset_samples"]
        result[o["observation_id"]]=(start-origin+epoch)/fs
    return result


def run(case):
    scan=final_scan(case)
    document=read(SOURCE/case/"tracking.json")
    if "source" in document or "timing" not in document:
        raise ValueError("this first qualification uses the public adaptive tracking snapshot only")
    observations=read(SOURCE/case/"observations.json")
    epochs=epoch_rows(document,observations)
    baseline=read(SOURCE/case/"result.json")
    node,keep=baseline["final_node"],np.array(baseline["final_mask"],bool)
    saved=baseline["arms"]["c0"]["record"]
    xy=np.array(saved["endpoint_east_north_km"])
    p=problem(scan,node,"c0",keep,np.array(saved["phase_reference"]))
    state=p.state(xy)
    receiver=geodetic_to_ecef_km(*latlon(xy),0)
    epoch=np.concatenate([[epochs[oid] for oid in scan.tracks[i]["observation_ids"]] for i in p.members])
    phase=state["phases"][p.labels]
    position,_=paired_phase_states(p.sky,epoch,p.flat_labels,phase)
    result=p.calculate(xy)
    start=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
    for mode in range(3):
        dp,_=paired_phase_states(p.mode_bank,epoch,p.flat_labels*3+mode,np.repeat(phase,3))
        for k,local in enumerate(p.supported_local):
            use=p.flat_labels==local
            position[use]+=dp[use]*result["coefficient"][start+3*k+mode]
    range_delay=np.linalg.norm(position-receiver,axis=1)/299792.458
    period=1/750
    tracks=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        active=keep[sl]
        if not active.any():continue
        t=epoch[sl][active];delay=range_delay[sl][active]
        residual=np.unwrap((t-delay)*2*np.pi/period)*period/(2*np.pi)
        residual-=residual[0]
        difference,clock=detrend(t,residual)
        observed,_=detrend(t,residual+delay)
        expected,_=detrend(t,delay)
        tracks.append(dict(component=row["component"],norad=int(scan.norads[row["candidate_index"]]),
            receiver=scan.tracks[i]["receiver"],channel=scan.tracks[i]["channel"],points=len(t),
            time_s=t,observed_delay_curvature_us=observed*1e6,expected_delay_curvature_us=expected*1e6,
            residual_us=difference*1e6,clock_slope_ppm=float(clock[1]*1e6),
            residual_RMS_us=float(np.sqrt(np.mean(difference**2))*1e6),
            negative_range_descriptive_RMS_us=float(np.sqrt(np.mean((observed+expected)**2))*1e6),
            observed_to_range_curvature_scale=float(observed@expected/max(expected@expected,1e-30)),
            expected_curvature_RMS_us=float(np.sqrt(np.mean(expected**2))*1e6)))
    folder=OUT/case;folder.mkdir(parents=True,exist_ok=True)
    write(folder/"qualification.json",dict(case=case,tracks=tracks,radio_selected_endpoint=xy,
        uses_supplied_GPS=False,position_not_refit=True,frame_period_s=period,
        timing_is_not_validated_pseudorange=True,unwrap_conditioned_on_existing_RF_satellite_hypotheses=True,
        positive_arrival_epoch_semantics=True,negative_range_relation_is_not_a_sign_convention=True,
        prior_audit="reports/2026_10_17_dsx01_iteration6/frame_phase_audit/README.md",
        per_track_affine_clock_removed_for_diagnosis_only=True,retarded_geometry_not_yet_applied=True,
        source_sha256=sha(Path(__file__)),tracking_sha256=sha(SOURCE/case/"tracking.json")))
    fig,axes=plt.subplots(3,2,figsize=(14,10),constrained_layout=True)
    chosen=sorted(tracks,key=lambda r:-r["expected_curvature_RMS_us"])[:6]
    for ax,r in zip(axes.ravel(),chosen,strict=True):
        t=np.array(r["time_s"])
        ax.plot(t,r["observed_delay_curvature_us"],".-",label="Observed frame epochs, affine removed")
        ax.plot(t,r["expected_delay_curvature_us"],label="Causal orbit range/c, affine removed")
        ax.plot(t,-np.array(r["expected_delay_curvature_us"]),"--",label="−range/c: descriptive control only")
        ax.set(xlabel="Device time (s)",ylabel="Delay curvature (µs)",
            title=r["component"].split(case+'-')[1].split('-RF')[0]+f" · {r['norad']}\nresidual RMS {r['residual_RMS_us']:.2f} µs")
        ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle(case+": archived frame-epoch qualification at RF endpoint; no GPS selection")
    fig.savefig(folder/"frame_epoch_curvature.png",dpi=150);plt.close(fig)
    print(case,"tracks",len(tracks),"median residual µs",np.median([r['residual_RMS_us'] for r in tracks]),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
