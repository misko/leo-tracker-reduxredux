"""Posthoc illustrations of both success and failure of held-visit phase prediction."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent

def main():
    summary=json.loads((HERE/'summary.json').read_text());data=json.loads((HERE/'plot-data.json').read_text());controls=summary['random_visit_controls']
    selected=[min([c for c in controls if c['session_id']=='scan-fw-4c56320fb5ca6994'],key=lambda c:c['linear_held_rms_deg']),next(c for c in controls if c['session_id']=='scan-fw-851486cc2a1acd99'),max([c for c in controls if c['session_id']=='scan-fw-da2858f6cd2521b7'],key=lambda c:c['linear_held_rms_deg'])]
    fig,axes=plt.subplots(1,3,figsize=(15,4.8));rows=[]
    for ax,c,title in zip(axes,selected,['02:42: smooth held-visit prediction','03:25: slow phase segment','02:35: wrong phase-rate branch']):
        ds=next(s for s in data if s['session_id']==c['session_id']);points=[r for r in ds['dwell_double_differences'] if r['group']==c['group']];tr=[r for r in points if r['partition']=='train'];he=[r for r in points if r['partition']=='held'];t=np.array([r['time_s'] for r in tr]);y=np.array([r['train_phase_rad'] for r in tr]);t0=t.mean();f=c['fitted_rate_hz'];intercept=np.angle(np.mean(np.exp(1j*(y-2*np.pi*f*(t-t0)))));constant=np.angle(np.mean(np.exp(1j*y)));first=min(r['time_s'] for r in points);last=max(r['time_s'] for r in points)
        grid=np.linspace(first,last,800);curve=np.degrees(np.angle(np.exp(1j*(intercept+2*np.pi*f*(grid-t0)))));curve[1:][abs(np.diff(curve))>180]=np.nan
        ax.plot(grid-first,curve,'--',color='#D55E00',label='Training-fitted linear phase');ax.axhline(np.degrees(constant),color='gray',ls=':',label='Training-fitted constant')
        ax.scatter(t-first,np.degrees(y),marker='s',color='#0072B2',label='Training visits');ax.scatter([r['time_s']-first for r in he],np.degrees([r['phase_rad'] for r in he]),facecolors='none',edgecolors='#009E73',s=65,linewidth=1.8,label='Held visits')
        ax.set(title=title,xlabel='Time within selected track-pair segment (s)',ylabel='Double difference (degrees)',ylim=(-185,185));ax.grid(alpha=.2);ax.text(.03,.03,f"Held RMS: constant {c['constant_held_rms_deg']:.1f}°\nlinear {c['linear_held_rms_deg']:.1f}°",transform=ax.transAxes,fontsize=9)
        rows.append(c)
    axes[0].legend(fontsize=7,loc='upper left');fig.suptitle('Random whole-visit holdouts — illustrative cases selected after scoring, not satellite geometry');fig.tight_layout();fig.savefig(HERE/'held-visit-examples.png',dpi=170)
    (HERE/'illustration-selection.json').write_text(json.dumps(dict(selection='Posthoc illustration: best linear case at02:42; sole eligible03:25 group; worst linear case at02:35. Does not tune reported scores.',cases=rows),indent=2)+'\n')

if __name__=='__main__':main()
