"""Plot selected residual-audit findings from the saved diagnostics only."""
import csv
import json
from pathlib import Path

import numpy as np

from residual_trend_audit import COLORS, OUTPUT, file_digest

SELECTED=[('A',64361,0),('A',68299,0),('A',64013,0),('A',66186,1),
          ('A',58622,1),('A',64767,1),('B',65804,0),('B',65745,0)]
NOTES={
    ('A',64361,0):'CH2 alone: +2.82 Hz/s; timing alone leaves the slope',
    ('A',68299,0):'Curvature persists within channels; RX1 is less curved',
    ('A',64013,0):'Linear + curved structure; channel offsets also matter',
    ('A',66186,1):'Timing + channel biases: 28.1 Hz held-out RMS',
    ('A',58622,1):'Channel offsets alone: 22.2 Hz held-out RMS',
    ('A',64767,1):'Within-channel drift: about +6 Hz/s',
    ('B',65804,0):'RX0 drift is much stronger than matched RX1',
    ('B',65745,0):'Channel-controlled slope: +7.06 Hz/s',
}


def run():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    source=OUTPUT/'points-and-diagnostic-corrections.csv'
    receipt=OUTPUT/'receipt.json';d=json.loads(receipt.read_text())
    if file_digest(source)!=d['outputs'][str(source)]:raise ValueError('point data changed')
    with source.open() as stream:rows=list(csv.DictReader(stream))
    fig,axes=plt.subplots(4,2,figsize=(15,14.5))
    for ax,key in zip(axes.flat,SELECTED,strict=True):
        label,number,rx=key
        rr=[r for r in rows if r['scan']==label and int(r['catalog_number'])==number and int(r['receiver'])==rx]
        x=np.array([float(r['time_s']) for r in rr]);y=np.array([float(r['residual_hz']) for r in rr]);ch=np.array([int(r['channel']) for r in rr])
        for c in np.unique(ch):
            mask=ch==c;ax.scatter(x[mask],y[mask],s=15,color=COLORS[c-1],alpha=.85,zorder=4)
        if key==('A',58622,1):
            for c in np.unique(ch):
                mask=ch==c
                values=np.array([float(r['channel_offsets_correction_hz']) for r in rr])[mask]
                ax.plot([x[mask].min(),x[mask].max()],[values[0]]*2,color=COLORS[c-1],linewidth=2)
        else:
            for model,color,style in [('line','#222222','--'),('quadratic','#CC3311','-')]:
                ax.plot(x,[float(r[model+'_correction_hz']) for r in rr],color=color,linestyle=style,linewidth=1.8,zorder=5)
        for v in (-150,150):ax.axhline(v,color='.6',linewidth=.7,linestyle=':')
        ax.axhline(0,color='.6',linewidth=.7)
        ax.set_ylim(-180,180);ax.set_xlim(x.min()-2,x.max()+2);ax.grid(alpha=.15)
        ax.set_title(f'Scan {label} · {number} / RX{rx}\n{NOTES[key]}',fontsize=10)
        ax.set_xlabel('Receive time (s)');ax.set_ylabel('GLRT − sealed orbit (Hz)')
    handles=[Line2D([],[],color=COLORS[i],marker='o',linestyle='',label=f'CH{i+1}') for i in range(4)]
    handles.extend([Line2D([],[],color='#222222',linestyle='--',label='Fitted line'),Line2D([],[],color='#CC3311',label='Fitted quadratic')])
    fig.suptitle('DS13 residual audit · strongest structures and channel controls',y=.989,fontsize=15)
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.969),ncol=6,fontsize=10)
    fig.text(.5,.013,'These are diagnostic fits to frozen final memberships. No correction has been applied to the original orbit fits.\n'
             'Residuals normalized to 11.085 GHz; selection was conditioned on ±150 Hz. Held-out scores use contiguous time blocks.',ha='center',fontsize=9)
    fig.tight_layout(rect=(.01,.045,.99,.936),h_pad=2.0)
    artifacts=[]
    for ext in ('png','svg'):
        path=OUTPUT/f'key-findings.{ext}'
        if path.exists():raise FileExistsError(path)
        fig.savefig(path,dpi=170);artifacts.append(path)
    plt.close(fig)
    (OUTPUT/'key-findings-receipt.json').write_text(json.dumps({'source_hashes':{str(source):file_digest(source),str(receipt):file_digest(receipt),str(Path(__file__)):file_digest(__file__)},'outputs':{str(p):file_digest(p) for p in artifacts}},indent=2)+'\n')


if __name__=='__main__':run()
