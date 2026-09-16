"""Report the corrected coherent pilot phase extension, without geometry claims."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).parent


def runs(rows,key):
    result=[]; first=None
    for i,row in enumerate(rows):
        if key(row) and first is None:first=i
        if first is not None and (not key(row) or i==len(rows)-1):
            last=i if key(row) else i-1
            result.append({'first_center_s':rows[first]['center_s'],'last_center_s':rows[last]['center_s'],'center_span_s':rows[last]['center_s']-rows[first]['center_s'],'count':last-first+1})
            first=None
    return sorted(result,key=lambda r:r['count'],reverse=True)


def main():
    coarse=json.loads((ROOT/'105915-coherent-pilot-20s.json').read_text())
    dense=json.loads((ROOT/'105915-coherent-pilot-20ms.json').read_text())
    cw=coarse['windows'];dw=dense['windows']
    qualified=[w for w in dw if w['both_qualified']]
    summary={'capture':coarse['capture'],'scanned_interval_s':[20,40],'coarse_windows':len(cw),'coarse_joint_qualified':sum(w['both_qualified'] for w in cw),'coarse_joint_runs':runs(cw,lambda w:w['both_qualified']),'dense_window_s':dense['window_s'],'dense_stride_s':dense['stride_s'],'dense_windows':len(dw),'dense_joint_qualified':len(qualified),'dense_joint_runs':runs(dw,lambda w:w['both_qualified']),'geometry_verified':False,'supersedes_previous_geometric_interpretation':True}
    summary['tracks']=[]
    for j in range(2):
        q=[w['tracks'][j] for w in cw if w['tracks'][j]['qualified']]
        summary['tracks'].append({'name':'AB'[j],'qualified_windows':len(q),'median_phase_concentration':float(np.median([v['resultant_length'] for v in q])),'median_coherent_pilot_control_power_ratios':np.median([v['ungated_coherent_exact_control_ratios'] for v in q],axis=0).tolist(),'runs':runs(cw,lambda w:w['tracks'][j]['qualified'])})
    # Compare circular phases only; no inferred cycles across missing windows.
    validcoarse=[w for w in cw if w['both_qualified']]
    ct=np.array([w['center_s'] for w in validcoarse]);cy=np.array([w['differential_phase_deg'] for w in validcoarse])
    errors=[]
    for w in qualified:
        i=np.argmin(abs(ct-w['center_s']))
        if abs(ct[i]-w['center_s'])<=.04:
            errors.append(float(np.degrees(np.angle(np.exp(1j*np.radians(w['differential_phase_deg']-cy[i]))))))
    summary['dense_vs_nearest_coarse_circular_rms_deg']=float(np.sqrt(np.mean(np.square(errors))))
    # Descriptive robust line, not an orbital model or an uncertainty estimate.
    ft=np.array([w['center_s'] for w in qualified])
    fy=np.array([w['differential_phase_deg'] for w in qualified])
    design=np.column_stack((np.ones(len(ft)),ft-ft.mean()))
    beta=np.linalg.lstsq(design,fy,rcond=None)[0]
    for _ in range(20):
        residual=fy-design@beta
        scale=1.4826*np.median(abs(residual-np.median(residual)))
        weight=np.minimum(1,1.345*scale/np.maximum(abs(residual),1e-12))
        beta=np.linalg.lstsq(design*np.sqrt(weight[:,None]),fy*np.sqrt(weight),rcond=None)[0]
    residual=fy-design@beta
    summary['descriptive_robust_line']={
        'slope_deg_per_s':float(beta[1]),
        'fitted_change_deg':float(beta[1]*(ft[-1]-ft[0])),
        'residual_mad_sigma_deg':float(1.4826*np.median(abs(residual-np.median(residual)))),
        'median_dense_phase_concentration':np.median([[w['tracks'][j]['resultant_length'] for j in range(2)] for w in qualified],axis=0).tolist(),
        'geometry_model':False,
    }
    (ROOT/'105915-coherent-extension-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    fig,ax=plt.subplots(3,1,figsize=(11,9),layout='constrained')
    fig.suptitle('Longer pilot phase tracks — corrected upper-edge, coherent extraction')
    for j in range(2):
        q=[w for w in cw if w['tracks'][j]['qualified']]
        ax[0].scatter([w['center_s'] for w in q],[j]*len(q),s=12,label=f'Track {"AB"[j]} passes pilot/phase checks')
    ax[0].set_yticks([0,1],['A','B']);ax[0].set_ylim(-.6,1.6);ax[0].set_xlim(20,40)
    ax[0].set_ylabel('RX0/RX1 track');ax[0].set_xlabel('Time from first sample (s)');ax[0].legend(fontsize=9)
    ax[1].scatter([w['center_s'] for w in qualified],[w['differential_phase_deg'] for w in qualified],s=6,alpha=.45,color='C0',label='20 ms windows, 10 ms cadence')
    ax[1].scatter(ct,cy,s=14,color='C1',label='150 ms windows, 75 ms cadence')
    ax[1].axvspan(25.8,28.225,color='grey',alpha=.13,label='Original interval')
    ax[1].set_ylabel('(RX1−RX0)A − (RX1−RX0)B (deg)');ax[1].set_xlabel('Time from first sample (s)');ax[1].legend(fontsize=8,ncol=2)
    for j in range(2):
        q=[w for w in dw if 'resultant_length' in w['tracks'][j]]
        ax[2].scatter([w['center_s'] for w in q],[w['tracks'][j]['resultant_length'] for w in q],s=5,alpha=.45,label=f'Track {"AB"[j]}, 20 ms')
    ax[2].axhline(.5,color='grey',ls='--',lw=1);ax[2].set_ylim(0,1.02)
    ax[2].set_ylabel('Phase concentration');ax[2].set_xlabel('Time from first sample (s)');ax[2].legend(fontsize=9)
    for a in ax:a.grid(alpha=.2)
    fig.savefig(ROOT/'105915-coherent-extension.png',dpi=160)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    fig.suptitle('Pilot specificity and descriptive phase residuals')
    for j in range(2):
        selected=[w for w in cw if w['tracks'][j]['qualified']]
        for rx in range(2):
            axes[0].plot([w['center_s'] for w in selected],
                [w['tracks'][j]['ungated_coherent_exact_control_ratios'][rx] for w in selected],
                '.',ms=3,label=f'{"AB"[j]} RX{rx}')
    axes[0].axhline(2,color='grey',ls='--',lw=1,label='Window threshold')
    axes[0].set_yscale('log');axes[0].set_xlabel('Time from first sample (s)')
    axes[0].set_ylabel('Exact / scrambled coherent power')
    axes[0].legend(fontsize=8,ncol=2)
    axes[1].hist(residual,bins=35,color='C0',alpha=.8)
    axes[1].set_xlabel('Phase minus robust linear trend (deg)')
    axes[1].set_ylabel('Accepted 20 ms windows (overlapping)')
    for a in axes:a.grid(alpha=.2)
    fig.savefig(ROOT/'105915-pilot-controls-and-residuals.png',dpi=160)
    plt.close(fig)
    print(json.dumps({k:v for k,v in summary.items() if k!='dense_joint_runs'},indent=2))


if __name__=='__main__':main()
