"""All canonical GLRT peaks and modeled orbit curves in wrapped CFO space.

One plotted point per canonical peak, no displayed alias copies. Wrapping model
and measurements to the same interval avoids implying an unassigned alias or
satellite identity. These are full-data development decoder results.
"""
import argparse,copy,json,sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest


def wrapped_curve(values):
    wrapped=(np.asarray(values)+ALIAS_HZ/2)%ALIAS_HZ-ALIAS_HZ/2
    wrapped=wrapped.copy();wrapped[1:][np.abs(np.diff(wrapped))>ALIAS_HZ/2]=np.nan
    return wrapped


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True)
    parser.add_argument('--method',choices=['tracklet','activity','history'],default='tracklet');args=parser.parse_args()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan
    data=load_expanded_scan(SESSIONS[args.scan]);folder=ROOT/'development-comparison'
    source=folder/f'{args.scan}-inputs.npz'
    with np.load(source) as z:a={k:z[k] for k in z.files}
    records=json.loads((folder/f'{args.scan}-{args.method}.json').read_text())['records']
    identity_path=ROOT/'development-identity-modes'/f'{args.scan}-{args.method}.json'
    accepted=set(json.loads(identity_path.read_text())['accepted_rows'])
    assignments={r['row_index']:r['catalog_number'] for r in records if r['row_index'] in accepted}
    numbers=sorted(set(assignments.values()));indices=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in numbers])
    colors={n:plt.get_cmap('turbo')(i/max(1,len(numbers)-1)) for i,n in enumerate(numbers)}
    params=a['parameters'];coeff=a['coefficient'];rf_center=np.mean(np.unique(data.rf))
    output=ROOT/'complete-overlays'
    if args.method!='tracklet':output=output/args.method
    output.mkdir(parents=True,exist_ok=True);panels=[]
    for rx in (0,1):
        fig,axes=plt.subplots(2,2,figsize=(17,10),sharex=True,sharey=True)
        for ax,ch in zip(axes.flat,sorted(np.unique(data.channel))):
            rows=a['rows'][(data.receiver[a['rows']]==rx)&(data.channel[a['rows']]==ch)]
            gray=np.array([r for r in rows if int(r) not in assignments],int)
            y=(data.measured+ALIAS_HZ/2)%ALIAS_HZ-ALIAS_HZ/2
            ax.scatter(data.times[gray],y[gray]/1000,s=6,c='#999999',alpha=.55,rasterized=True,zorder=2)
            dense=copy.copy(data);dense.times=np.arange(0,300.001,.25)
            dense.receiver=np.full(len(dense.times),rx,int)
            dense.rf=np.full(len(dense.times),float(np.unique(data.rf[data.channel==ch])[0]))
            pred,visible,_=SharedPredictionPlan(dense,indices).predict(params)
            pred=pred.reshape(len(dense.times),-1)+float(np.ravel(coeff)[0])*(dense.rf[:,None]-rf_center)/1e9
            visible=visible.reshape(pred.shape)
            for col,n in enumerate(numbers):
                curve=wrapped_curve(pred[:,col]);curve[~visible[:,col]]=np.nan
                ax.plot(dense.times,curve/1000,color=colors[n],lw=.65,alpha=.5,zorder=1)
                rr=np.array([r for r in rows if assignments.get(int(r))==n],int)
                if len(rr):ax.scatter(data.times[rr],y[rr]/1000,s=8,color=colors[n],rasterized=True,zorder=3)
            assigned=len(rows)-len(gray)
            panels.append(dict(receiver=rx,channel=int(ch),total=len(rows),screened_assigned=assigned,unassigned=len(gray)))
            ax.set_title(f'CH{ch}: {len(rows)} peaks; {assigned} screened assigned; {len(gray)} unassigned',fontsize=11)
            ax.set(xlim=(0,300),ylim=(-ALIAS_HZ/2000,ALIAS_HZ/2000),xlabel='Receive time (s)',ylabel='Wrapped measured CFO (kHz)')
            ax.grid(alpha=.15)
        fig.suptitle(f'DS13 scan {args.scan} RX{rx} · all canonical GLRT peaks + selected satellite predictions\nDevelopment {args.method}; orbit + receiver/RF calibration, wrapped to the measurement alias interval',fontsize=14)
        fig.legend(handles=[Line2D([],[],color=colors[n],lw=2,label=str(n)) for n in numbers],
                   loc='upper center',bbox_to_anchor=(.5,.92),ncol=13,fontsize=7,frameon=False)
        handles=[Line2D([],[],marker='o',ls='',color='#999999',label='Unassigned / not identity-screened'),
                 Line2D([],[],marker='o',ls='-',color='#0072b2',label='Screened assignment / modeled curve (color by satellite)')]
        fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,.035),ncol=2)
        fig.text(.5,.012,'Each canonical peak appears once. Exact alias copies excluded; nearby alternative peaks retained. Curves break at wrap boundaries.\nNo extra aliases plotted. Screened assignments are provisional—not held-out or negative-control validated.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.10,1,.87));fig.savefig(output/f'{args.scan}-RX{rx}-all-peaks.png',dpi=150);plt.close(fig)
    assert sum(p['total'] for p in panels)==len(a['rows'])
    assert sum(p['screened_assigned'] for p in panels)==len(accepted)
    receipt=dict(scope=__doc__,scan=args.scan,method=args.method,panels=panels,catalog_numbers=numbers,
        source_sha256={str(source):digest(source),str(identity_path):digest(identity_path)})
    (output/f'{args.scan}-receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
