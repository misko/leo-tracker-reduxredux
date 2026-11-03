"""Render only genuine post-scan-epoch comparisons from verified saved refits."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from residual_trend_audit import COLORS, regress, polynomial, file_digest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'later-tle-timing-aligned-v2/receipt.json'
OUTPUT = ROOT / 'post-scan-tle-only'
KEYS = [('A',68299,0),('A',66186,1),('A',58622,1)]


def select_genuine(receipt):
    lookup = {(t['scan'],t['catalog_number'],t['receiver']):t for t in receipt['tracks']}
    selected=[]
    for key in KEYS:
        track=lookup[key]
        scan=next(s for s in receipt['scans'] if s['scan']==key[0])
        element=next(e for e in scan['elements'] if e['catalog_number']==key[1])
        if element['later']['epoch_utc_ns'] <= scan['origin_utc_ns']+300_000_000_000:
            raise ValueError('element epoch must be strictly after the scan')
        if not scan['later_fit']['success']:
            raise ValueError('refit is not converged')
        selected.append((track,element))
    return selected


def run():
    receipt=json.loads(SOURCE.read_text())
    for path,digest in receipt['outputs'].items():
        if file_digest(path)!=digest:
            raise ValueError(f'changed saved output: {path}')
    selected=select_genuine(receipt)
    OUTPUT.mkdir(exist_ok=False)
    fig,axes=plt.subplots(3,2,figsize=(15,11))
    for row,(track,element) in enumerate(selected):
        t=np.asarray(track['time_s']);ch=np.asarray(track['channel'])
        values=np.r_[track['old_residual_hz'],track['later_residual_hz']]
        bound=max(180.,np.ceil(np.max(np.abs(values))/25)*25+10)
        for col,variant in enumerate(('old','later')):
            ax=axes[row,col];y=np.asarray(track[variant+'_residual_hz'])
            for c in np.unique(ch):
                m=ch==c
                ax.scatter(t[m],y[m],s=17,color=COLORS[c-1],alpha=.85,zorder=4)
                if track['catalog_number']==58622:
                    ax.plot([t[m].min(),t[m].max()],[y[m].mean()]*2,color=COLORS[c-1],linewidth=2)
            if track['catalog_number']!=58622:
                for degree,color,style in ((1,'#222222','--'),(2,'#CC3311','-')):
                    _,line,_=regress(polynomial(t,degree),y)
                    ax.plot(t,line,color=color,linestyle=style,linewidth=1.8,zorder=5)
            for level in (-150,0,150):
                ax.axhline(level,color='.6',linewidth=.7,linestyle='-' if level==0 else ':')
            stats=track[variant+'_stats']
            label='Original pinned TLE' if col==0 else 'Post-scan TLE · backward propagated'
            ax.set_title(f"Scan A · {track['catalog_number']} / RX{track['receiver']} · {label}\n"
                         f"RMS {stats['rms_hz']:.1f} Hz; slope {stats['slope_hz_s']:+.2f} Hz/s; "
                         f"q {stats['quadratic_hz_s2']:+.4f} Hz/s²",fontsize=10)
            ax.set_ylim(-bound,bound);ax.set_xlim(t.min()-2,t.max()+2)
            ax.set_xlabel('Receive time (s)');ax.set_ylabel('GLRT − fitted orbit (Hz)')
            ax.grid(alpha=.15)
            if col==1:
                ax.text(.02,.035,f"TLE epoch {element['epoch_relative_to_scan_hours']:.2f} h after scan start",
                        transform=ax.transAxes,fontsize=9,bbox={'facecolor':'white','alpha':.8,'edgecolor':'none'})
    handles=[Line2D([],[],marker='o',linestyle='',color=COLORS[i],label=f'CH{i+1}') for i in range(4)]
    handles += [Line2D([],[],color='#222222',linestyle='--',label='Fitted line'),
                Line2D([],[],color='#CC3311',label='Fitted quadratic')]
    fig.suptitle('DS13 · genuine post-scan TLE comparison',y=.99,fontsize=16)
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,.968),ncol=6)
    fig.text(.5,.018,'Same GLRT points, aliases, joint timing/RX/RF fitting model and fixed reference position; matched axis scales.\n'
             'Post-scan epochs verified individually. Polynomial overlays are descriptive; none was subtracted.\n'
             'Original ±150 Hz selection retained without re-gating; RMS is descriptive, not held-out validation.',
             ha='center',fontsize=9)
    fig.tight_layout(rect=(.01,.08,.99,.935),h_pad=2.)
    for ext in ('png','svg'):fig.savefig(OUTPUT/f'before-after.{ext}',dpi=170)
    plt.close(fig)
    provenance={'source_sha256':{str(SOURCE):file_digest(SOURCE),str(Path(__file__)):file_digest(__file__)},
                'selection':KEYS,'refits_reused_without_change':True,
                'outputs':{str(p):file_digest(p) for p in OUTPUT.iterdir()}}
    (OUTPUT/'receipt.json').write_text(json.dumps(provenance,indent=2)+'\n')


if __name__=='__main__':run()
