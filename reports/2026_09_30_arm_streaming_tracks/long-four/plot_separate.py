"""Separate measured-point panels to avoid hiding rolling points under hybrid."""
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent.parent
BASE=REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
PREV=REPORTS/'2026_09_30_arm_curvature_tracks'
sys.path.insert(0,str(PREV/'evaluation'))
import compare_membership as m


def main():
    so=m.read_observations(BASE/'server-observations.tsv')
    ao=m.read_observations(BASE/'arm-observations.tsv')
    refs=m.read_tracks(BASE/'server-tracks.tsv',so).values
    banks={'rolling':m.read_tracks(HERE.parent/'qualification/rolling/arm-0.tsv',ao).values,
           'hybrid':m.read_tracks(PREV/'hybrid-v1/host/arm-a250-v2.tsv',ao).values}
    audit=json.loads((HERE/'audit.json').read_text())
    origin=min(o.start_ns for o in so.values())
    fig,axes=plt.subplots(4,2,figsize=(15,15),layout='constrained')
    for row,record in enumerate(audit['rows']):
        ref=refs[record['reference']]
        reference=sorted(((so[p.candidate].center_ns-origin)/1e9,p.dealiased_cfo_hz/1000)
                         for p in ref.points)
        t,f=np.array(reference).T
        spacing=11.2e9/ref.lane.rf_hz/4.4e-6/1000
        plotted=[]
        for col,(name,color,title) in enumerate([('rolling','#df710d','Rolling linear'),
                                                ('hybrid','#168457','Coarse-seeded curvature')]):
            ax=axes[row,col]
            ax.plot(t,f,'o-',ms=4,mfc='none',mec='#b3b3b3',color='#c4c4c4',lw=.8,
                    zorder=1,label='Server reference')
            track=banks[name][record[name]['track']]
            points=sorted(((ao[p.candidate].center_ns-origin)/1e9,p.dealiased_cfo_hz/1000)
                          for p in track.points if ref.start_ns<=ao[p.candidate].center_ns<=ref.end_ns)
            tt,ff=np.array(points).T
            ff+=np.round((np.interp(tt,t,f)-ff)/spacing)*spacing
            ax.plot(tt,ff,'o-',ms=3.7,lw=1.4,color=color,zorder=3,label=title)
            plotted.extend(ff)
            if name=='rolling':
                begin=record['hybrid']['matching_time_range_s'][0]
                end=record['rolling']['matching_time_range_s'][0]
                ax.axvspan(begin,end,color=color,alpha=.10,zorder=0)
                ax.text((begin+end)/2,.04,'Omitted\nprefix',ha='center',va='bottom',
                        transform=ax.get_xaxis_transform(),fontsize=9,color='#a34d00')
            ax.set_title(f'Ref #{ref.index} · {title}\n'
                         f'{record[name]["coverage_count"]}/{record["reference_points"]} matching points '
                         f'({record[name]["coverage"]:.1%})')
            ax.set_xlim(t[0]-1,t[-1]+1)
            ax.set_xlabel('Seconds from first projected observation')
            ax.set_ylabel('Alias-aligned CFO (kHz)')
            ax.grid(alpha=.2)
            if row==0:
                ax.legend(fontsize=9)
        lo=min(min(f),min(plotted));hi=max(max(f),max(plotted));padding=(hi-lo)*.07
        for ax in axes[row]:
            ax.set_ylim(lo-padding,hi+padding)
    fig.suptitle('Rolling and coarse-seeded tracking shown separately\n'
                 'Identical axes within each row; colored measurements drawn above the gray server reference',fontsize=14)
    fig.savefig(HERE/'comparison-separated.png',dpi=150)
    fig.savefig(HERE/'comparison-separated.pdf')
    plt.close(fig)


if __name__=='__main__':
    main()
