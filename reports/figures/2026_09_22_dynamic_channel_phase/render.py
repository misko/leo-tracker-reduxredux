import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    root=Path('/tmp/dynamic-channel-phase');x=json.loads((root/'results.json').read_text());p=json.loads(Path('/tmp/postfix-phase-methods-authority/results.json').read_text())
    fig,ax=plt.subplots(3,1,figsize=(12,10),constrained_layout=True)
    for key,color,label in [('original','gray','Original frozen response'),('revised','tab:blue','Phase-normalized training response')]:
        r=x[key]['rows'];t=np.array([31.8+a['center_sample']/2500000 for a in r]);phase=np.degrees([a['held_band_residual_phase_rad'] for a in r]);ax[0].plot(t,phase,'.',ms=2,color=color,label=label)
    ax[0].set_ylabel('Held B residual phase (°)');ax[0].legend();ax[0].set_title('Independent-band alignment after current A-band phase correction')
    for key in ['original','revised']:
        h=x[key]['rows'];r=np.array([a['held_band_residual_phase_rad'] for a in h]);print(key,'B phase RMS deg',np.degrees(np.sqrt(np.mean(r*r))))
    w=p['windows'];t=np.array([r['time_s'] for r in w]);phase=np.unwrap(np.radians([r['phase_deg'] for r in w]));summary=[]
    for name,color in [('pilot_branch_lifted','tab:red'),('pilot_common_authority','tab:blue'),('pilot_shared_residual','tab:green')]:
        rows=[r for r in p['pilots'] if r['method']==name];tt=np.array([r['time_s'] for r in rows]);pp=np.radians([r['phase_deg'] for r in rows]);d=np.angle(np.exp(1j*(pp-np.interp(tt,t,phase))));training=tt<32.3;offset=np.angle(np.mean(np.exp(1j*d[training])));res=np.angle(np.exp(1j*(d-offset)))
        ax[1].plot(tt,np.degrees(res),'o',ms=3,color=color,label=name)
        summary.append(dict(method=name,training_phase_offset_deg=float(np.degrees(offset)),held_out_circular_rms_difference_deg=float(np.degrees(np.sqrt(np.mean(res[~training]**2))))))
    ax[1].axvline(32.3,c='gray',ls='--');ax[1].legend(fontsize=8);ax[1].set_ylabel('Pilot − scalar phase (°)');ax[1].set_title('One constant reference offset learned before 32.3 s; later differences withheld')
    ax[2].bar(['Original support','Normalized response support'],[x['original_bin_count']*2500000/4096/1e6,x['revised_bin_count']*2500000/4096/1e6],color=['gray','tab:blue']);ax[2].set_ylabel('Qualified spectral support (MHz)')
    for a in ax[:2]:a.grid(alpha=.2);a.set_xlabel('Elapsed device sample time (s)')
    fig.suptitle('Two estimation fixes: coherent response fitting and a shared pilot frequency reference')
    fig.savefig(root/'estimator-fixes.png',dpi=160)
    (root/'pilot-comparison.json').write_text(json.dumps(summary,indent=2)+'\n')
if __name__=='__main__':main()
