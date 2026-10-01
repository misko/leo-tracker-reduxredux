"""Separate measured-point panels for the four targeted DS9 prefixes."""
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
OLD=REPORTS/'2026_09_30_arm_streaming_tracks'
BASE=REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0,str(REPORTS/'2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m


def main():
    so=m.read_observations(BASE/'server-observations.tsv')
    ao=m.read_observations(BASE/'arm-observations.tsv')
    refs=m.read_tracks(BASE/'server-tracks.tsv',so).values
    banks=[m.read_tracks(OLD/f'qualification/{name}/arm-0.tsv',ao).values
           for name in ['rolling','rolling-backfill']]
    audit=json.loads((OLD/'long-four/audit.json').read_text())
    evaluation=json.loads((OLD/'qualification/rolling-backfill/arm-evaluation.json').read_text())
    matches={r['reference_track_index']:r for r in evaluation['primary']['matches']}
    origin=min(o.start_ns for o in so.values())
    fig,axes=plt.subplots(4,2,figsize=(14,14),layout='constrained')
    for row,record in enumerate(audit['rows']):
        ref=refs[record['reference']]
        t,f=np.array(sorted(((so[p.candidate].center_ns-origin)/1e9,
                            p.dealiased_cfo_hz/1000) for p in ref.points)).T
        match=matches[ref.index]
        indexes=[record['rolling']['track'],match['output_track_index']]
        counts=[record['rolling']['coverage_count'],match['consistent_source_count']]
        spacing=11.2e9/ref.lane.rf_hz/4.4e-6/1000
        plotted=list(f)
        for col,(title,color) in enumerate([('Original rolling','#df710d'),
                                           ('Rolling + bounded backfill','#168457')]):
            ax=axes[row,col]
            ax.plot(t,f,'o-',ms=4,mfc='none',color='#bbbbbb',lw=.8,label='Server reference')
            track=banks[col][indexes[col]]
            tt,ff=np.array(sorted(((ao[p.candidate].center_ns-origin)/1e9,
                                  p.dealiased_cfo_hz/1000) for p in track.points
                                 if ref.start_ns<=ao[p.candidate].center_ns<=ref.end_ns)).T
            ff+=np.round((np.interp(tt,t,f)-ff)/spacing)*spacing
            plotted.extend(ff)
            ax.plot(tt,ff,'o-',ms=3.4,lw=1,color=color,label=title)
            ax.set_title(f'Ref #{ref.index}: {title}\n{counts[col]}/{record["reference_points"]} matching sources')
            ax.set(xlim=(t[0]-1,t[-1]+1),xlabel='Seconds from first observation',
                   ylabel='Alias-aligned CFO (kHz)')
            ax.grid(alpha=.2)
            if row==0: ax.legend(fontsize=8)
        lo,hi=min(plotted),max(plotted)
        for ax in axes[row]: ax.set_ylim(lo-(hi-lo)*.07,hi+(hi-lo)*.07)
    fig.suptitle('ARM GLRT observations: original rolling vs bounded backfill\n'
                 'Separate panels, identical axes within each row; measured points, not fitted lines')
    fig.savefig(HERE/'target-comparison.png',dpi=140)
    fig.savefig(HERE/'target-comparison.pdf')
    plt.close(fig)


if __name__=='__main__':
    main()
