"""Measure artificial receiver-calibration jumps at the archived fold switches.

The original estimator switches fitted receiver curves every 10 s, cycling
through five held-out models. This audit compares those model curves at the
same epoch/RX, not measurements at unequal times. RF c is excluded exactly as
in the frozen receiver baseline used by T1-AT localization. No new fitting.
"""
import json
import csv
from pathlib import Path
import numpy as np
from leave_one_satellite_out import HERE,load
from full_data_calibration import INPUTS
from timing_bound_comparison import digest
from subset_positions import serial

OUT=HERE/'fold-splice-audit'
SCANS=tuple(f'N{i:02}' for i in range(1,17))


def receiver_curves(records,times,rx):
    times=np.asarray(times,float)
    if rx not in (0,1) or np.any(~np.isfinite(times)):
        raise ValueError('Invalid receiver or times')
    curves=[]
    for r in records:
        p=np.asarray(r['arms']['fitted-c']['parameters'])
        curves.append(p[2+2*rx]+p[3+2*rx]*(times-150.)+
            np.interp(times,r['spline_nodes_s'],r['correction_knots_hz'][rx]))
    return np.array(curves)


def selected_curve(curves,times):
    curves=np.asarray(curves);times=np.asarray(times)
    if curves.shape!=(5,len(times)):raise ValueError('Five fold curves required')
    fold=(np.floor(times/10).astype(int)%5)
    return curves[fold,np.arange(len(times))]


def boundary_jumps(records,rx):
    # Evaluate both neighboring model functions at the same exact boundary;
    # do not include the physical time derivative in this jump diagnostic.
    times=np.arange(10.,300.,10.)
    curves=receiver_curves(records,times,rx)
    after=(times/10).astype(int)%5
    before=(after-1)%5
    jumps=curves[after,np.arange(len(times))]-curves[before,np.arange(len(times))]
    return times,jumps


def main():
    OUT.mkdir(exist_ok=True)
    summaries=[];details=[];records_by_scan={};sources={}
    for scan in SCANS:
        data,meta,_=load(scan)
        records=[]
        for k in range(5):
            path=INPUTS/scan/'seed-timing-v6/calibration-v2'/f'fold-{k}.json'
            records.append(json.loads(path.read_text()));sources[str(path)]=digest(path)
        records_by_scan[scan]=records
        reconstructed=np.empty(len(data.times))
        for rx in (0,1):
            keep=data.receiver==rx
            curves=receiver_curves(records,data.times[keep],rx)
            reconstructed[keep]=selected_curve(curves,data.times[keep])
            times,jumps=boundary_jumps(records,rx)
            for t,jump in zip(times,jumps):
                details.append(dict(scan=scan,receiver=rx,time_s=float(t),jump_hz=float(jump)))
            summary=dict(scan=scan,receiver=rx,windows=int(sum(keep)),
                median_abs_jump_hz=float(np.median(abs(jumps))),max_abs_jump_hz=float(max(abs(jumps))),
                rms_jump_hz=float(np.sqrt(np.mean(jumps**2))),jumps_above_600hz=int(sum(abs(jumps)>600.)),
                fold_offset_range_hz=float(np.ptp([r['arms']['fitted-c']['parameters'][2+2*rx] for r in records])),
                fold_slope_range_hz_s=float(np.ptp([r['arms']['fitted-c']['parameters'][3+2*rx] for r in records])))
            summaries.append(summary)
        # Reconstruct the actual saved baseline, not only its description.
        np.testing.assert_allclose(reconstructed,data.fixed_receiver_hz,atol=1e-7,rtol=0)
    report=dict(status='passed',scope=__doc__,scans=SCANS,sources=sources,
        original_receiver_baseline_reconstructed=True,summaries=summaries,boundary_jumps=details,
        interpretation='These are jumps in the applied fitted calibration, not evidence that the hardware physically jumped. A causal position-error effect requires a matched rerun.')
    (OUT/'audit.json').write_text(json.dumps(report,default=serial,indent=2,allow_nan=False))
    for name,rows in [('summary.csv',summaries),('boundary-jumps.csv',details)]:
        with (OUT/name).open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    render(records_by_scan)
    print(json.dumps(summaries,indent=2))


def render(records_by_scan):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    times=np.linspace(0.,299.999,6001)
    fig,axes=plt.subplots(2,2,figsize=(13,7),sharex=True)
    colors=['#0072b2','#e69f00','#009e73','#cc79a7','#d55e00']
    for col,scan in enumerate(('N05','N06')):
        for rx in (0,1):
            ax=axes[rx,col];records=records_by_scan[scan]
            curves=receiver_curves(records,times,rx)
            for k,color in enumerate(colors):
                ax.plot(times,curves[k]/1000,c=color,lw=.8,alpha=.65,label=f'Fold {k}')
            ax.plot(times,selected_curve(curves,times)/1000,c='black',lw=1.15,label='Applied stitched correction')
            _,jumps=boundary_jumps(records,rx)
            ax.set_title(f'{scan} · RX{rx} · largest switch jump {max(abs(jumps))/1000:.2f} kHz')
            ax.set_ylabel('Frozen RX correction (kHz)');ax.grid(alpha=.15)
            if rx==1:ax.set_xlabel('Receive time (s)')
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,ncol=6,loc='upper center',bbox_to_anchor=(.5,.925),frameon=False,fontsize=9)
    fig.suptitle('Alternating calibration folds introduce artificial jumps into the observations',fontsize=15)
    fig.text(.5,.015,'Black = receiver correction actually applied, reconstructed against every saved input observation. No RF c term shown.\n'
        'Every 10 s a different independently fitted calibration is selected; the cycle repeats every 50 s. These are model switches, not measured hardware events.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.08,1,.88));fig.savefig(OUT/'N05-N06-calibration-switches.png',dpi=165);plt.close(fig)


if __name__=='__main__':main()
