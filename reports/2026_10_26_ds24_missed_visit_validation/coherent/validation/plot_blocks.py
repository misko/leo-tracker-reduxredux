"""Per-block CFO evidence with both native receivers and exact owner sidecars."""
import collections
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from integrate import read,write,sha,PRED
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
PERIOD=227272.72727272726


def native_curve_segments(track,piece,observations,lo,hi):
    """Graph coefficients are Legendre in alias-lifted space, not raw CFO."""
    a,b=max(lo,piece['start_s']),min(hi,piece['end_s'])
    if a>b:return []
    bindings={i:(oid,float(value)) for i,oid,value in zip(track['indices'],track['observation_ids'],track['values'],strict=True)}
    data=sorted((observations[bindings[i][0]]['time_s'],round((bindings[i][1]-observations[bindings[i][0]]['measured_cfo_hz'])/PERIOD)) for i in piece['indices'])
    times=np.asarray([d[0] for d in data]);lifts=np.asarray([d[1] for d in data]);ts=np.linspace(a,b,200)
    ys=np.polynomial.legendre.legval((ts-piece['reference_time_s'])/piece['time_scale_s'],piece['coefficients_hz'])
    near=np.argmin(abs(ts[:,None]-times[None,:]),axis=1);selected=lifts[near]
    boundaries=np.r_[0,np.flatnonzero(np.diff(selected))+1,len(ts)]
    return [(ts[x:y],ys[x:y]-selected[x]*PERIOD) for x,y in zip(boundaries[:-1],boundaries[1:])]


def main():
    output=HERE/'figures';output.mkdir(exist_ok=False);blocks=read(PRED/'blocks.json')['blocks'];summary=[]
    plt.rcParams.update({'font.size':9,'axes.grid':True,'grid.alpha':.2})
    for block in blocks:
        case=block['case'];ch=block['channel'];center=block['seed_native']['time_s'];lo,hi=center-12,center+12
        ledger=read(HERE/(case+'_additions.json'));original=read(SOURCE/case/'observations.json')
        tracks=read(HERE/'graphs'/case/'tracks.json');audit=read(HERE/'graphs'/case/'graph_audit.json')
        g=set(audit['new_graph_ids']);curved=set(audit['new_curved_ids']);added=[a for a in ledger['staged'] if block['block_id'] in a['block_ids']]
        old=[o for o in original if o['channel']==ch and lo<=o['time_s']<=hi]
        allrows={o['observation_id']:o for o in ledger['observations']};graph_by_id={oid:t['key'] for t in tracks for oid in t['observation_ids']}
        points=[];fig,axes=plt.subplots(3,2,figsize=(13,9),sharex=True,layout='constrained')
        for rx in (0,1):
            ax=axes[0,rx];lane=[o for o in old if o['native_receiver_id']==rx];new=[a for a in added if a['native_receiver_id']==rx]
            ax.scatter([o['time_s']-center for o in lane],[o['measured_cfo_hz']/1000 for o in lane],s=22,c='#475569',label=f'Original GLRT ({len(lane)})',zorder=3)
            for kind,color,marker in (('curved','#059669','o'),('graph','#2563eb','s'),('outside','#dc2626','x')):
                selected=[a for a in new if ('curved' if a['target_observation_id'] in curved else 'graph' if a['target_observation_id'] in g else 'outside')==kind]
                ax.scatter([a['time_s']-center for a in selected],[a['measured_cfo_hz']/1000 for a in selected],s=42,c=color,marker=marker,label=f'Added {kind} ({len(selected)})',zorder=5)
            first=True
            for track in tracks:
                if track['channel']!=ch or track['receiver']!=rx+1:continue
                for piece in track['pieces']:
                    for ts,ys in native_curve_segments(track,piece,allrows,lo,hi):
                        ax.plot(ts-center,ys/1000,c='#7c3aed',lw=1.2,alpha=.8,label='Rebuilt RF graph' if first else None);first=False
            ax.set_title(f'Native RX{rx} / model RX{rx+1}');ax.set_ylabel('Measured CFO (kHz)');ax.legend(fontsize=7,loc='best')
            pred=axes[1,rx];innov=axes[2,rx]
            pred.scatter([a['time_s']-center for a in new],[a['predicted_cfo_hz']/1000 for a in new],marker='x',s=32,c='#d97706',label='Earlier selected donor forecast')
            pred.scatter([a['time_s']-center for a in new],[a['measured_cfo_hz']/1000 for a in new],marker='o',s=20,c='#0f766e',label='Later confirmation FFT')
            pred.set_ylabel('Added-owner CFO (kHz)');pred.legend(fontsize=7,loc='best')
            for a in new:
                oid=a['target_observation_id'];color='#059669' if oid in curved else '#2563eb' if oid in g else '#dc2626'
                innov.scatter(a['time_s']-center,a['innovation_hz']/1000,c=color,s=32)
                points.append(dict(observation_id=oid,native_receiver_id=rx,time_s=a['time_s'],
                    predicted_cfo_hz=a['predicted_cfo_hz'],measured_cfo_hz=a['measured_cfo_hz'],innovation_hz=a['innovation_hz'],
                    zero_fft_bin=a['zero_fft_bin'],donor_count=a['donor_count'],donor_ids=[d['native_observation_id'] for d in a['donors']],
                    graph_key=graph_by_id.get(oid),curved_RF_graph=oid in curved,
                    satellite_membership='pending fresh causal association; RF graph is not satellite identity'))
            innov.axhline(0,c='#64748b',lw=.7);innov.set_ylabel('FFT − forecast (kHz)');innov.set_xlabel('Seconds from frozen seed midpoint')
            innov.set_xlim(-12.3,12.3)
            if not new:
                for row in (1,2):axes[row,rx].text(.5,.5,'No admitted new native owners',transform=axes[row,rx].transAxes,ha='center',va='center',color='#64748b')
        fig.suptitle(f'{case} CH{ch}: fixed 24 s block at {center:.6f} s\nOriginal GLRT + expansion only; donor predictions and target FFT innovations shown separately',fontsize=12)
        stem=block['block_id'];fig.savefig(output/(stem+'.png'),dpi=170);fig.savefig(output/(stem+'.pdf'));plt.close(fig)
        sidecar=dict(block_id=stem,case=case,channel=ch,seed_observation_id=block['seed_observation_id'],center_time_s=center,
            original_count=len(old),added_count=len(added),added_in_graph=sum(a['target_observation_id'] in g for a in added),
            added_curved=sum(a['target_observation_id'] in curved for a in added),added_outside_graph=sum(a['target_observation_id'] not in g for a in added),
            original_native_observation_ids=[o['observation_id'] for o in old],added_native_owners=points,
            graph_source_sha256=sha(HERE/'graphs'/case/'tracks.json'),
            graph_curve_coordinates='Legendre model projected back to native CFO with per-owner alias lifts; split at lift changes',GPS_used=False)
        write(output/(stem+'.json'),sidecar);summary.append({k:v for k,v in sidecar.items() if k not in ('original_native_observation_ids','added_native_owners')})
    write(HERE/'block_figure_manifest.json',dict(blocks=summary,exact_owner_sidecars=True,both_native_receivers=True,
        graph_membership_separate_from_causal_satellite_membership=True,GPS_used=False))
    print(summary)


if __name__=='__main__':main()
