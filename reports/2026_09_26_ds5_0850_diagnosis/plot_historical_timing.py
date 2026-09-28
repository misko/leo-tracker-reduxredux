"""Descriptive historical TLE-consistency distributions; no prior refitting."""
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator,FuncFormatter
import numpy as np
from scipy.stats import t

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_26_reno_track_audit/probabilistic_history.json'


def main():
    history=json.loads(SOURCE.read_text());pairs=history['pairs']
    assert len(pairs)==history['training_pairs']+history['validation_pairs']
    summary=[]
    for lo,hi in ((0,12),(12,24),(24,48),(48,72),(72,120)):
        rows=[r for r in pairs if lo<=r['age_hours']<hi]
        x=np.array([r['equivalent_tau_s'] for r in rows])
        assert np.isfinite(x).all()
        summary.append({'lower_age_h':lo,'upper_age_h':hi,'pairs':len(rows),
            'satellites':len({r['satellite_id'] for r in rows}),
            'quantiles_s':{str(q):float(np.quantile(x,q)) for q in (0,.005,.025,.05,.5,.95,.975,.995,1)},
            'absolute_at_least_41_9s':int((abs(x)>=41.9).sum()),
            'positive_at_least_41_9s':int((x>=41.9).sum())})
    focus=[r for r in pairs if 12<=r['age_hours']<24]
    focus_abs=np.abs([r['equivalent_tau_s'] for r in focus])
    scale=next(b['scale_s'] for b in history['bins'] if b['lower_h']==12)
    empirical=float(np.mean(focus_abs>=41.9));prior=float(2*t.sf(41.9/scale,4))
    split_counts={}
    for val in (False,True):
        rows=[r for r in focus if r['validation_group']==val]
        split_counts['validation' if val else 'training']={
            'pairs':len(rows),'absolute_at_least_41_9s':sum(abs(r['equivalent_tau_s'])>=41.9 for r in rows)}
    receipt={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'scope':'descriptive pooled training+validation history; equal pair weights; not independent samples or true orbit errors',
        'definition':'dot(position_new-position_old, velocity_old)/dot(velocity_old,velocity_old), at a common epoch',
        'age_bins':summary,'focus_12_24h':{'existing_t4_scale_s':scale,
            'empirical_absolute_tail_at_41_9s':empirical,'model_absolute_tail_at_41_9s':prior,
            'empirical_to_model_ratio':empirical/prior,'split_counts':split_counts}}
    (HERE/'historical_timing_distribution.json').write_text(json.dumps(receipt,indent=2)+'\n')

    plt.rcParams.update({'font.size':11,'axes.titlesize':13,'axes.labelsize':12,
        'axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False})
    fig,(ax,tail)=plt.subplots(1,2,figsize=(15.8,7.4),gridspec_kw={'wspace':.29})
    fig.subplots_adjust(left=.065,right=.975,bottom=.22,top=.79)
    fig.suptitle('Historical TLE differences expressed as equivalent timing shifts',fontsize=18,y=.97)
    fig.text(.5,.905,f'{len(pairs):,} element-set pairs · 257 satellites · historical data predating DS5',ha='center',fontsize=12)
    colors=['#2477b4','#de8b22','#23936d','#8c65ac']
    for (lo,hi),color in zip(((12,24),(24,48),(48,72),(72,120)),colors):
        x=np.sort([r['equivalent_tau_s'] for r in pairs if lo<=r['age_hours']<hi])
        ax.step(x,np.arange(1,len(x)+1)/len(x)*100,where='post',color=color,lw=2,
            label=f'{lo}–{hi} h  (n = {len(x):,})')
    ax.set_xscale('symlog',linthresh=1,linscale=1)
    largest=max(abs(r['equivalent_tau_s']) for r in pairs)
    ax.set_xlim(-largest*1.15,largest*1.15);ax.set_ylim(0,102)
    ax.xaxis.set_major_locator(FixedLocator([-1000,-100,-10,-1,0,1,10,100,1000]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:g}'))
    ax.set_xlabel('Signed equivalent timing difference τ (seconds)\nSymmetric-log axis; linear between −1 and +1 s')
    ax.set_ylabel('Historical pairs at or below τ (%)')
    ax.set_title('Observed distributions by older TLE age',pad=13)
    ax.grid(alpha=.16);ax.axvline(0,color='#777777',lw=.7)
    ax.axvline(41.9,color='#bc3544',lw=1.5,ls='--')
    ax.text(41.9,10,' +41.9 s\n diagnostic fit',color='#9c2835',fontsize=10,ha='left',va='bottom')
    ax.legend(loc='upper left',title='Age at comparison epoch',fontsize=10,title_fontsize=10)

    x,count=np.unique(focus_abs,return_counts=True)
    survival=np.cumsum(count[::-1])[::-1]/len(focus_abs)
    positive=x>0
    tail.step(x[positive],survival[positive],where='pre',color=colors[0],lw=2.2,label='Observed pairs (n = 1,296)')
    grid=np.geomspace(.02,float(focus_abs.max())*1.15,600)
    model=2*t.sf(grid/scale,4)
    tail.plot(grid,model,color='#b16a19',lw=2,ls='--',label=f'Existing t₄ prior (scale {scale:.3f} s)')
    tail.set_xscale('log');tail.set_yscale('log')
    tail.set_xlim(grid.min(),grid.max());tail.set_ylim(float(model.min())*.7,1.5)
    tail.xaxis.set_major_locator(FixedLocator([.1,1,10,100]))
    tail.xaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:g}'))
    tail.set_xlabel('Absolute equivalent timing difference |τ| (seconds)')
    tail.set_ylabel('Fraction at or above |τ| / prior tail probability')
    tail.set_title('12–24 h TLEs: observed tails vs fitted prior',pad=13)
    tail.grid(which='major',alpha=.16)
    tail.axvline(41.9,color='#bc3544',lw=1.5,ls='--')
    tail.scatter([41.9],[empirical],color=colors[0],s=42,zorder=4)
    tail.scatter([41.9],[prior],color='#b16a19',s=42,zorder=4)
    tail.annotate('Observed: 6 / 1,296 = 0.46%',xy=(41.9,empirical),xytext=(-208,15),
        textcoords='offset points',fontsize=11,arrowprops={'arrowstyle':'-','color':colors[0]})
    tail.annotate(f'Prior: {prior*100:.6f}%',xy=(41.9,prior),xytext=(-175,-25),
        textcoords='offset points',fontsize=11,arrowprops={'arrowstyle':'-','color':'#b16a19'})
    tail.legend(loc='lower left',fontsize=10)
    fig.text(.065,.105,'12–24 h observed central 90%: −4.06 to +1.19 s. Six pairs exceed ±41.9 s; only two exceed +41.9 s.',fontsize=11)
    fig.text(.065,.063,'These are first-order along-velocity projections of old/new TLE position differences—not verified orbital errors or clock offsets.',fontsize=10)
    fig.text(.065,.03,'Pairs are correlated; each pair has equal weight. No tails trimmed. Under 12 h: only 12 pairs, insufficient to calibrate a young-TLE prior.',fontsize=10)
    fig.savefig(HERE/'historical_timing_distribution.png',dpi=160,facecolor='white')
    fig.savefig(HERE/'historical_timing_distribution.pdf',facecolor='white')
    print(json.dumps(receipt['focus_12_24h'],indent=2))


if __name__=='__main__':main()
