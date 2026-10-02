"""Report every segmentation control and the selected pair's stability limits."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from check_receiver_curvature import save
HERE=Path(__file__).resolve().parent


def main():
    path=HERE/'radio-segmentation-v1.json';data=sealed(path);verify_sources(data['sources']);verify_sources(data['inputs'])
    rows=[]
    for scan in data['scans']:
        rows.append(dict(unit=scan['unit'],tracks=len(scan['tracks']),policies={name:dict(
            split_tracks=sum(len(r['results'][name]['segments'])>1 for r in scan['tracks']),
            total_segments=sum(len(r['results'][name]['segments']) for r in scan['tracks']))
            for name in ('primary','half_penalty','double_penalty','noise300')}))
    pair=[r for s in data['scans'] if s['unit']=='DS10-B01-S1' for r in s['tracks'] if r['track_index'] in (16,17)]
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True)
    for ax,row in zip(axes,sorted(pair,key=lambda r:-r['track_index'])):
        t=np.array(row['times_s']);y=np.array(row['frequencies_hz']);base=np.polyfit(t,y,2)
        ax.plot(t,y-np.polyval(base,t),'o',markersize=4,color='grey',label='Original samples')
        for i,s in enumerate(row['results']['primary']['segments']):
            a,b=s['start'],s['stop'];tt=t[a:b];poly=np.polyfit(tt,y[a:b],2)
            ax.plot(tt,np.polyval(poly,tt)-np.polyval(base,tt),linewidth=2,label=f'Segment {i+1}')
            if a:ax.axvline((t[a]+t[a-1])/2,color='grey',linestyle='--',alpha=.5)
        ax.set_title('RX'+str(0 if row['track_index']==17 else 1));ax.set_ylabel('Hz minus full-track quadratic');ax.legend(ncol=3);ax.grid(alpha=.2)
    axes[-1].set_xlabel('Seconds from track start');fig.suptitle('Penalized contiguous segmentation: lower residuals, unstable physical interpretation')
    fig.tight_layout();fig.savefig(HERE/'radio-segmentation-v1.png',dpi=160);plt.close(fig)
    rx0=next(r for r in pair if r['track_index']==17);rx1=next(r for r in pair if r['track_index']==16)
    gate=len(rx0['results']['primary']['segments'])==1 and all(len(rx1['results'][n]['segments'])>1 for n in ('primary','double_penalty'))
    save(HERE/'radio-segmentation-summary-v1.json',dict(rows=rows,outlier_gate=gate,
        inputs={str(path):digest(path)},sources={str(Path(__file__).resolve()):digest(__file__)},
        qualification='Descriptive SSE reductions on reused data, not predictive or geographic performance.'))
    print(rows,gate)


if __name__=='__main__':main()
