"""Plot measured transport separately from counter-proven IQ continuity."""
import json
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--data',type=Path,default=ROOT.parent/'data')
parser.add_argument('--output',type=Path,default=ROOT.parent)
args=parser.parse_args()
ROOT=args.data
DEST=args.output
DEST.mkdir(parents=True, exist_ok=True)
raw = json.loads((ROOT/'raw-1r1t-3s.json').read_text())['cells']
direct = json.loads((ROOT/'ladder-2r2t-30s.json').read_text())['cells']
repeat = json.loads((ROOT/'raw-1r1t-60m-10s-repeat.json').read_text())['cells']
plt.rcParams.update({'font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,axs = plt.subplots(1,2,figsize=(13,4.8),layout='constrained')
x=np.array([c['rate_hz']/1e6 for c in raw])
r=np.array([c['payload_MBps'] for c in raw])
xd=np.array([c['rate_hz']/1e6 for c in direct])
rd=np.array([c['payload_MBps_read'] for c in direct])
axs[0].plot(x,4*x,':',color='gray',label='Continuous CI16 input: 4 × sample rate')
axs[0].plot(x,r,'o-',color='#167d9a',label='1R1T ordinary IQ, 3 nominal seconds')
axs[0].plot(xd,rd,'s--',color='#ba5b21',label='2R2T RX0 direct-async, 30 nominal seconds')
for c in repeat:
    axs[0].plot(60,c['payload_MBps'],'D',color='#6c4799',ms=6)
axs[0].plot([],[],'D',color='#6c4799',label='60 MS/s: three 10-second repeats')
axs[0].set(xlabel='RFIC and capture sample rate (MS/s)',ylabel='IQ payload (MB/s, decimal)',
           title='Measured Ethernet IQ delivery',xlim=(0,63),ylim=(0,253))
axs[0].legend(loc='upper left',fontsize=8.7)
axs[1].plot(x,100*r/(4*x),'o-',color='#167d9a',label='1R1T ordinary IQ')
axs[1].plot(xd,100*rd/(4*xd),'s--',color='#ba5b21',label='2R2T RX0 direct-async')
for c in repeat:
    axs[1].plot(60,100*c['delivery_equivalent_duty'],'D',color='#6c4799')
mean=np.mean([c['payload_MBps'] for c in repeat])
axs[1].annotate(f'60 MS/s: {mean:.2f} MB/s\n{100*mean/240:.1f}% delivery equivalent',
    xy=(60,100*mean/240),xytext=(24,50),arrowprops={'arrowstyle':'->','color':'#6c4799'},color='#6c4799')
axs[1].axhline(100,color='gray',ls=':',lw=1)
axs[1].set(xlabel='RFIC and capture sample rate (MS/s)',ylabel='Delivered payload / continuous input (%)',
           title='Transport capacity; not a continuity guarantee',xlim=(0,63),ylim=(0,108))
for ax in axs: ax.grid(alpha=.18)
fig.suptitle('192.168.1.17 · v0.49 · one CI16 receiver · 1 Gb/s Ethernet',fontsize=14)
fig.savefig(DEST/'ethernet_ladder.png',dpi=180)
plt.close(fig)

fig,ax=plt.subplots(figsize=(13,4.9),layout='constrained')
labels=[]
for index,c in enumerate(direct):
    rate=c['rate_hz']; first=c['frames'][0]['first']
    span=c['source_span_seconds']
    y=3-index
    ax.broken_barh([(0,span)],(y-.24,.48),facecolors='#eee4df')
    intervals=[((r['first']-first)/rate,r['samples']/rate) for r in c['runs']]
    ax.broken_barh(intervals,(y-.24,.48),facecolors='#17818d')
    labels.append(f"{rate/1e6:g} MS/s · longest {c['longest_contiguous_seconds']:.2f} s")
    ax.text(span+.4,y,f"{100*c['source_coverage_fraction']:.1f}% of source interval",va='center',fontsize=10)
ax.set_yticks([3,2,1,0],labels)
ax.set(xlim=(0,61),ylim=(-.7,3.8),xlabel='Seconds since first delivered sample in each independent session',
       title='Counter-proven contiguous intervals · 50 × 1M-sample DMA buffers = 200 MB')
ax.text(.01,-.25,'Teal = received contiguous IQ; pale = counter-proven missing IQ. Each row contains 30 seconds of delivered samples.\n'
        '60 MS/s: largest contiguous chunk UNKNOWN — v0.49 metadata requires 2R2T, which caps this CMOS board at 30.72 MS/s.',
        transform=ax.transAxes,fontsize=10,va='top')
ax.grid(axis='x',alpha=.2)
fig.savefig(DEST/'capture_continuity.png',dpi=180,bbox_inches='tight')
plt.close(fig)
print(DEST)

c=next(c for c in direct if c['rate_hz']==30_000_000)
lengths=np.array([run['samples']/c['rate_hz'] for run in c['runs']])
fig,ax=plt.subplots(figsize=(12,4.7),layout='constrained')
bars=ax.bar(np.arange(1,len(lengths)+1),lengths,color='#17818d',width=.72)
bars[-1].set(facecolor='#cbdde0',hatch='//',edgecolor='#17818d')
ax.axhline(np.median(lengths),color='#a15022',ls='--',label=f'Median: {np.median(lengths):.2f} s')
ax.scatter(np.flatnonzero(lengths<.04)+1,lengths[lengths<.04],color='#b34843',zorder=3,
           label='Six isolated buffers: 33.33 ms each')
ax.set(xticks=np.arange(1,len(lengths)+1),xlabel='Continuous segment, in source-time order',
       ylabel='Continuous IQ duration (seconds)',ylim=(0,4.05),
       title='30 MS/s · 18 counter-proven segments · minimum 33.33 ms · median 2.35 s')
ax.annotate('Final segment reaches test end;\nnatural end is unknown',xy=(18,lengths[-1]),xytext=(10,3.6),
            arrowprops={'arrowstyle':'->','color':'#385a65'},fontsize=10)
ax.grid(axis='y',alpha=.2)
ax.legend(loc='upper left',fontsize=9)
fig.savefig(DEST/'segment_lengths_30m.png',dpi=180)
plt.close(fig)
