"""Hold GLRT rows, orbit timing and RF c fixed; change only the RX baseline."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from full_data_calibration import FullCalibration,INPUTS,OUT as CALIBRATIONS
from full_data_localization import fold_baseline
from run import TopAbsoluteCalibration
from fold_splice_audit import OUT
from refinement import circular
from timing_bound_comparison import digest


def main():
    scan='N06';cal=FullCalibration(scan);data=cal.data
    receipt_path=CALIBRATIONS/scan/'associations/fitted-c.json'
    receipt=json.loads(receipt_path.read_text())
    satellite=max(receipt['final']['selected'],key=lambda s:s['count'])
    number=satellite['catalog_number'];j=int(np.flatnonzero(data.numbers==number)[0])
    assignments=[a for a in receipt['final']['assignments'] if a['catalog_number']==number]
    lookup={int(r):i for i,r in enumerate(data.original_rows)}
    rows=np.array([lookup[a['row_index']] for a in assignments])
    predicted=cal.predict('fitted-c',[j],satellite['offset_s'])[0][:,0]
    old=TopAbsoluteCalibration(INPUTS/scan/'seed-timing-v6');old.data.label=scan
    old_baseline,_=fold_baseline(old)
    np.testing.assert_array_equal(old.data.original_rows,data.original_rows)
    new_baseline=cal.receiver_baseline('fitted-c')
    previous_prediction=predicted-new_baseline+old_baseline
    residuals=[circular(data.measured-previous_prediction),circular(data.measured-predicted)]
    np.testing.assert_allclose(residuals[1][rows],[a['residual_hz'] for a in assignments],atol=1e-6,rtol=0)
    fig,axes=plt.subplots(2,2,figsize=(13,7),sharex=True)
    colors=['#0072b2','#e69f00','#009e73','#cc79a7'];stats=[]
    for rx in (0,1):
        keep=rows[data.receiver[rows]==rx]
        for col,e in enumerate(residuals):
            ax=axes[rx,col]
            for k,ch in enumerate(sorted(np.unique(data.channel))):
                rr=keep[data.channel[keep]==ch]
                ax.scatter(data.times[rr],e[rr],c=colors[k],s=15,alpha=.8)
            for a in range(30,300,50):ax.axvspan(a,a+10,color='.7',alpha=.18)
            ax.axhline(0,c='.4',lw=.8);ax.grid(alpha=.15)
            rms=float(np.sqrt(np.mean(e[keep]**2)))
            ax.set_title(f'RX{rx} · '+('Stitched fold RX baseline' if col==0 else 'Single full-scan RX baseline')+
                         f'\n{len(keep)} identical windows · residual RMS {rms:.1f} Hz')
            ax.set_ylabel('GLRT − predicted CFO (Hz)')
            if col==1:ax.set_ylim(-650,650)
            if rx==1:ax.set_xlabel('Receive time (s)')
            stats.append(dict(receiver=rx,model='fold' if col==0 else 'full',windows=len(keep),rms_hz=rms))
    from matplotlib.lines import Line2D
    handles=[Line2D([],[],marker='o',color=c,ls='none',label=f'CH{i+1}') for i,c in enumerate(colors)]
    fig.legend(handles=handles,ncol=4,loc='upper center',bbox_to_anchor=(.5,.92),frameon=False)
    fig.suptitle(f'N06 · satellite {number} · calibration-switch effect on the same GLRT track',fontsize=16)
    fig.text(.5,.015,'Orbit, absolute timing shift and RF c held fixed; only the receiver correction changes. Right panels use a tighter Hz scale.\n'
        'Shading: blocks using fold 3. All windows selected by the new full-data association are shown in both columns.\n'
        'In-sample calibration diagnostic, not independent proof of satellite identity or position accuracy.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.11,1,.87));fig.savefig(OUT/'N06-same-track-before-after.png',dpi=165);plt.close(fig)
    report=dict(scan=scan,satellite=number,selection='Most windows in the full-calibration fitted-c solution',
        total_windows=len(rows),original_rows=data.original_rows[rows].tolist(),stats=stats,
        calibration_sha256=digest(cal.path),association_sha256=digest(receipt_path),
        orbit_and_timing_and_rf_coefficient_held_fixed=True)
    (OUT/'N06-same-track-before-after.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(report['stats'],indent=2))


if __name__=='__main__':main()
