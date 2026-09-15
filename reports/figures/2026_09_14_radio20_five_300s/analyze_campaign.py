"""Review and summarize the bounded radio .20 five-recording campaign."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

FW = Path("/home/mouse9911/gits/plutosdr-fw-radio20-tracking")
sys.path.insert(0, str(FW))
from tests.starlink_glrt.test_cpu_coarse import bank, integer_grid, sorted_peak_oracle
from tests.starlink_glrt.test_native_solver import dense_fit
from tools.review_glrt_cpu_live_epochs import review_epochs
from tools.starlink_glrt_native_replay import coefficients
from tools.starlink_glrt_tracking_abi import TrackingSnapshot
from tools.starlink_glrt_tracking_journal import review as review_native

EVIDENCE = Path("/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912")
CAMPAIGN = EVIDENCE / "five-300s-30ms-scan64-v1"
HERE = Path(__file__).parent
PRIMARY = [f"recording-{n}" for n in range(1, 6)]
ORDER = ["recording-1", "recording-2", "recording-3", "recording-4-initial-clean-loss",
         "recording-4", "recording-5-initial-source-loss", "recording-5"]
PROBES = {
    "recording-1": "5939c896ec2864b5c0899120709d9ec8f6b0a2392ce624797f3b8dc1bc5074a7",
    "recording-2": "6cee8f7291ea927a8671b606fc48d72906f70448df1a60ce794bd463acee2617",
    "recording-3": "6cee8f7291ea927a8671b606fc48d72906f70448df1a60ce794bd463acee2617",
    "recording-4-initial-clean-loss": "6cee8f7291ea927a8671b606fc48d72906f70448df1a60ce794bd463acee2617",
    "recording-4": "78586a05d935f494c30eb70c057f60cb61edc923ea52e7e9e27f523ae82207b3",
    "recording-5-initial-source-loss": "78586a05d935f494c30eb70c057f60cb61edc923ea52e7e9e27f523ae82207b3",
    "recording-5": "78586a05d935f494c30eb70c057f60cb61edc923ea52e7e9e27f523ae82207b3",
}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def percentile(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def native_basis(rate: int):
    path = FW / "hdl/library/starlink_glrt/native_cubic_60000000_upper.mem"
    raw = np.asarray(coefficients(path.read_bytes(), rate_hz=rate), dtype=np.float64)
    n = len(raw); ref = raw[:, 0] + 1j * raw[:, 1]; derivative = raw[:, 2] + 1j * raw[:, 3]
    basis = np.column_stack((ref, -derivative,
        1j*np.pi*1000/rate*(2*np.arange(n)-(n-1))*ref))
    return basis, basis.conj().T @ basis, sha(path)


def review_native_episode(checked, terminal, basis, gram, rate):
    complete=[]; incomplete=[]
    for head, estimate in zip(checked["heads"], checked["estimates"], strict=True):
        if head.fault or head.count != rate*33//25000:
            assert terminal["result"] == -3 and estimate["rejection"] & 3
            assert estimate["coherence"] == estimate["linearized_coherence"] == 0
            incomplete.append(dict(sequence=head.sequence, frame=estimate["frame"],
                count=head.count, fault=head.fault, rejection=estimate["rejection"]))
            continue
        head.require_complete(); n=len(basis)
        center=[(n-1)*r-2*p for r,p in zip(head.reference_sum,head.reference_prefix_integral,strict=True)]
        p=np.array([complex(*head.reference_sum),complex(*head.delay_sum),
            -1j*np.pi*1000/rate*complex(*center)])
        projected=basis @ np.linalg.solve(gram,p)
        correction,_,_=dense_fit(basis,np.column_stack((projected.real,projected.imag)))
        coherence=float(abs(p[0])**2/(gram[0,0].real*head.observed_energy))
        direction=np.r_[1,np.clip(correction,-.25,.25)];model=basis@direction
        improved=float(abs(direction@p)**2/(np.vdot(model,model).real*head.observed_energy))
        step=head.phase_step if head.phase_step<2**31 else head.phase_step-2**32
        expected=[direction[1]*1e-6,direction[2]*1000,step*rate/2**32+direction[2]*1000,coherence,improved]
        np.testing.assert_allclose([estimate[k] for k in
            ("delay_s","residual_hz","cfo_hz","coherence","linearized_coherence")],expected,
            rtol=2e-10,atol=2e-12)
        rejection=(32 if np.any(abs(correction)>=.25) else 0)|(64 if coherence<.05 else 0)
        assert estimate["rejection"]==rejection
        complete.append(dict(sequence=head.sequence,frame=estimate["frame"],coherence=coherence,
            cfo_hz=estimate["cfo_hz"],delay_ns=estimate["delay_s"]*1e9,rejection=rejection))
    return complete,incomplete


def review_run(name: str) -> dict:
    root=CAMPAIGN/name;op=json.loads((root/"operator.json").read_text())
    status=json.loads((root/"stdout.json").read_text());rows=[json.loads(x) for x in (root/"worker.jsonl").read_text().splitlines()]
    assert op["rate"]==status["rate"]==30_000_000 and op["blocks"]==45_000
    assert op["profile"]=="45000-selected-observer3-scan64"
    assert op["candidate_budget"]==64 and op["ranking_fft"]==4096
    assert op["payload_sha256"]["probe"]==PROBES[name]
    assert op["rf_sample_limit"]==737_280_000 and op["rf_duration_limit_s"]==294.912
    assert op["temporary_files_removed"] is True
    assert op["after"]["remote"]["serial"]=="1040005e0b100007100010000bf33a5d4d"
    assert op["after"]["remote"]["firmware"]=="glrt-iq-tracking-r30000000-v1"
    assert op["after"]["remote"]["all_buffer_enable"]=="0"
    assert op["rf_after"]==op["configured"]["rf_state"]
    assert op["rf_after"]["tx_powerdown"]=="1" and op["rf_after"]["sampling_frequency"]=="30000000"
    for artifact, receipt in op["artifacts"].items():
        path=root/artifact
        if receipt is None:
            assert not path.exists()
        else:
            assert path.stat().st_size==receipt["bytes"] and sha(path)==receipt["sha256"]
    snapshots=[]
    for line in (root/"capture.txt").read_text().splitlines():
        if line.startswith("tracking_snapshot "):
            snapshots.append(TrackingSnapshot.from_sysfs(line.split(" ",1)[1]))
    assert snapshots
    for snap in snapshots:
        snap.require_drained();assert snap.rate==30_000_000
    assert max(s.cdc_drops for s in snapshots)==max(s.pacer_drops for s in snapshots)==0
    scans=[r for r in rows if r.get("kind")=="scan"]
    ranks=[r for r in rows if r.get("kind")=="candidate_order"]
    terminals=[r for r in rows if r.get("kind")=="worker_terminal"]
    assert len(ranks)==len(terminals)
    if status["stage"]=="finite_source_complete" and not status["worker_complete"]:
        assert status["attempts"]-len(terminals) in (0,1) and len(scans)-len(terminals) in (0,1)
    else:
        assert len(scans)==len(terminals)==status["attempts"]
    assert [r["attempt"] for r in scans]==list(range(1,len(scans)+1))
    selected=np.fromfile(root/"scan.iq.ci16",dtype="<i2").reshape(-1,2)
    grids=np.fromfile(root/"grids.u32",dtype="<u4").reshape(len(scans),11,3333)
    assert len(selected)==status["retained_scan_samples"]==len(scans)*14000
    sample_indexes={0,len(ranks)//2,len(ranks)-1}
    sample_indexes.update(i for i,t in enumerate(terminals) if t["status"]==1)
    numerical=0;ranking_fft=0
    refs=np.fromfile(EVIDENCE/"direct-references.ci16",dtype="<i2").reshape(4,3300,4)
    ref=refs[0,:,0].astype(float)+1j*refs[0,:,1];ref_energy=float(np.vdot(ref,ref).real)
    for i in sorted(sample_indexes):
        cut=selected[i*14000:(i+1)*14000]
        expected=integer_grid(cut,bank());np.testing.assert_array_equal(grids[i],expected)
        peaks=sorted_peak_oracle(expected,64);assert scans[i]["peaks"]==[list(p) for p in peaks]
        powers=[];zall=cut[:,0].astype(float)+1j*cut[:,1]
        for epoch,frequency,score in peaks:
            z=zall[epoch+22:epoch+3322]
            powers.append(float(max(abs(np.fft.fft(z*np.conj(ref),4096))**2)/max(float(np.vdot(z,z).real)*ref_energy,1)))
        np.testing.assert_allclose(ranks[i]["single_pilot_power"],powers,rtol=2e-12,atol=2e-15)
        assert ranks[i]["selected_rank"]==int(np.argmax(powers));numerical+=grids[i].size;ranking_fft+=len(powers)
    journals={artifact:(root/artifact).read_bytes() for artifact,receipt in op["artifacts"].items()
        if receipt is not None and artifact.startswith("native") and artifact.endswith(".journal")}
    epoch_review=review_epochs((root/"capture.txt").read_text(),rows,journals,status)
    basis,gram,reference_sha=native_basis(30_000_000);native_rows=[];incomplete=[];episode_summaries=[]
    for ep in epoch_review["episodes"]:
        if not ep["results"]:
            episode_summaries.append(ep);continue
        artifact="native.journal" if ep["episode"]==0 else f"native-{ep['episode']}.journal"
        checked=review_native(journals[artifact],epoch=ep["epoch"],rate=30_000_000)
        terminal=next(r for r in rows if r.get("kind")=="native_terminal" and r["native_episode"]==ep["episode"])
        complete,bad=review_native_episode(checked,terminal,basis,gram,30_000_000)
        native_rows.extend(dict(x,episode=ep["episode"]) for x in complete);incomplete.extend(dict(x,episode=ep["episode"]) for x in bad)
        episode_summaries.append(dict(ep,complete_results=len(complete),incomplete_results=len(bad)))
    observer=[json.loads(x) for x in (root/"observer.jsonl").read_text().splitlines()]
    observations=[r for r in observer if r.get("kind")=="measurement"]
    accepted=sum(r.get("accepted",0) for r in rows if r.get("kind")==3)
    scan_ms=[(ranks[i]["completed_ns"]-scans[i]["started_ns"])/1e6 for i in range(len(ranks))]
    worker_ms=[(terminals[i]["completed_ns"]-ranks[i]["completed_ns"])/1e6 for i in range(len(ranks))]
    max_power=[max(r["single_pilot_power"]) for r in ranks]
    return dict(name=name,primary=name in PRIMARY,operator_status=op["status"],probe_status=status["status"],stage=status["stage"],
        completed_refills=status["completed_refills"],rf_seconds=status["completed_refills"]*16384/2_500_000,
        attempts=status["attempts"],handoffs=status["handoffs"],reacquisitions=status["reacquisitions"],
        native_results=status["native_results"],native_supported=sum(x["rejection"]==0 for x in native_rows),
        native_completed_runs=status["native_completed_runs"],native_incomplete_results=len(incomplete),
        native_episodes=episode_summaries,native_complete=native_rows,native_incomplete=incomplete,
        observer_measurements=len(observations),observer_supported=sum(r.get("accepted",0) for r in observations),
        accepted_startup_measurements=accepted,max_refill_gap_ms=status["max_refill_gap_ns"]/1e6,
        scan_rank_ms=dict(median=statistics.median(scan_ms),p95=percentile(scan_ms,95),maximum=max(scan_ms)),
        worker_ms=dict(median=statistics.median(worker_ms),p95=percentile(worker_ms,95),maximum=max(worker_ms)),
        max_candidate_power=dict(median=statistics.median(max_power),p95=percentile(max_power,95),maximum=max(max_power)),
        sampled_grid_values_checked=numerical,sampled_ranking_ffts_checked=ranking_fft,
        native_reference_sha256=reference_sha,cdc_drops=0,pacer_drops=0,
        artifact_sha256={p.name:sha(p) for p in root.iterdir() if p.is_file() and p.name in op["artifacts"]},
        plot=dict(max_power=max_power,native=native_rows,observer=observations))


def main():
    runs=[review_run(name) for name in ORDER];primary=[r for r in runs if r["primary"]]
    result=dict(status="pass",scope="five_bounded_30_msps_fpga_tracking_recordings",
        nominal_recording_seconds=300,exact_sample_ceiling_seconds=294.912,
        serial="1040005e0b100007100010000bf33a5d4d",source_rate=30_000_000,acquisition_rate=2_500_000,
        primary_recordings=PRIMARY,diagnostic_partial_recordings=[n for n in ORDER if n not in PRIMARY],
        primary_rf_seconds=sum(r["rf_seconds"] for r in primary),all_rf_seconds=sum(r["rf_seconds"] for r in runs),
        primary_handoffs=sum(r["handoffs"] for r in primary),primary_reacquisitions=sum(r["reacquisitions"] for r in primary),
        primary_native_results=sum(r["native_results"] for r in primary),primary_native_supported=sum(r["native_supported"] for r in primary),
        primary_completed_native_runs=sum(r["native_completed_runs"] for r in primary),
        sampled_grid_values_checked=sum(r["sampled_grid_values_checked"] for r in runs),
        sampled_ranking_ffts_checked=sum(r["sampled_ranking_ffts_checked"] for r in runs),
        native_complete_estimates_checked=sum(len(r["native_complete"]) for r in runs),
        native_incomplete_heads_checked=sum(r["native_incomplete_results"] for r in runs),runs=[])
    for r in runs:
        result["runs"].append({k:v for k,v in r.items() if k not in ("plot","native_complete")})
    result["script_sha256"]=sha(Path(__file__))
    (HERE/"campaign-summary.json").write_text(json.dumps(result,indent=2)+"\n")

    colors=["#0072B2" if r["probe_status"]==0 else "#D55E00" for r in primary]
    fig,axes=plt.subplots(2,1,figsize=(10,7),layout="constrained")
    x=np.arange(1,6);axes[0].bar(x,[r["rf_seconds"] for r in primary],color=colors)
    axes[0].axhline(294.912,color="black",ls="--",lw=1,label="exact 737,280,000-sample ceiling")
    axes[0].set(ylabel="RF seconds",title="Five nominal 300-second recordings at 30 MS/s");axes[0].set_xticks(x);axes[0].legend();axes[0].grid(axis="y",alpha=.2)
    width=.26;axes[1].bar(x-width,[r["handoffs"] for r in primary],width,label="handoffs",color="#009E73")
    axes[1].bar(x,[r["reacquisitions"] for r in primary],width,label="reacquisitions",color="#E69F00")
    axes[1].bar(x+width,[r["native_completed_runs"] for r in primary],width,label="1,500-result completions",color="#CC79A7")
    axes[1].set(xlabel="Recording",ylabel="Count");axes[1].set_xticks(x);axes[1].legend();axes[1].grid(axis="y",alpha=.2)
    fig.savefig(HERE/"campaign-overview.png",dpi=180);plt.close(fig)

    fig,ax=plt.subplots(figsize=(11,5),layout="constrained");offset=0
    for r in runs:
        power=r["plot"]["max_power"];step=r["rf_seconds"]/max(len(power),1)
        xx=offset+(np.arange(len(power))+.5)*step
        ax.plot(xx,power,lw=.8,label=r["name"]);offset+=r["rf_seconds"]
        ax.axvline(offset,color="0.75",lw=.6)
    ax.set(xlabel="Cumulative RF seconds (including preserved partials)",ylabel="Maximum single-pilot ranking power",
        title="Acquisition opportunity varies sharply across the campaign")
    ax.grid(alpha=.2);ax.legend(fontsize=7,ncol=2)
    fig.savefig(HERE/"acquisition-power.png",dpi=180);plt.close(fig)

    native=[];observer=[];offset=0
    for r in runs:
        for index,row in enumerate(r["plot"]["native"]):
            native.append((offset+index/750,row["coherence"],r["name"]))
        for index,row in enumerate(r["plot"]["observer"]):
            observer.append((offset+index*3/750,row["coherence"],r["name"]))
        offset+=r["rf_seconds"]
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True,layout="constrained")
    if native:axes[0].scatter([x for x,_,_ in native],[y for _,y,_ in native],s=6,alpha=.55,color="#0072B2")
    if observer:axes[1].scatter([x for x,_,_ in observer],[y for _,y,_ in observer],s=10,alpha=.7,color="#009E73")
    for ax,title in zip(axes,("Native FPGA retained estimates","Simultaneous 2.5-MS/s ARM observer"),strict=True):
        ax.axhline(.05,color="black",ls="--",lw=1,label="unchanged 0.05 coherence gate");ax.set_ylabel("Coherence");ax.set_title(title);ax.grid(alpha=.2);ax.legend()
    axes[1].set_xlabel("Campaign-relative frame time (separate epochs concatenated)")
    fig.savefig(HERE/"tracking-support.png",dpi=180);plt.close(fig)
    print(json.dumps({k:v for k,v in result.items() if k!="runs"}))


if __name__=="__main__":
    main()
