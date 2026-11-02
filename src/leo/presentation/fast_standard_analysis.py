"""Figures from exact published point owners and replayed CFO predictions."""
from collections import defaultdict
from io import BytesIO

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib import colormaps

from leo.analysis.research.graph_position_membership import native_polynomial


def render(packet, *, title):
    rows=packet['rows']['fitted_c'];raw={o['observation_id']:o for o in packet['observations']}
    selected={r['observation_id']:r for r in rows};numbers=sorted({r['norad'] for r in rows})
    colors={n:colormaps['tab20'](k%20) for k,n in enumerate(numbers)};products={}
    groups=defaultdict(list)
    for r in rows:groups[r['component']].append(r)
    def save(name,fig):
        FigureCanvasAgg(fig);s=BytesIO();fig.savefig(s,format='png',dpi=125);products[name]=s.getvalue();fig.clear()
    for first,last in ((1,4),(5,8)):
        for kind in ('all','unassociated','residuals'):
            fig=Figure(figsize=(15,11),layout='constrained');axes=fig.subplots(4,2,squeeze=False)
            for ch in range(first,last+1):
                for rx in (1,2):
                    ax=axes[ch-first,rx-1]
                    lane=[o for o in raw.values() if o['receiver']==rx and o['channel']==ch]
                    owned=[o for o in lane if o['observation_id'] in selected];unowned=[o for o in lane if o['observation_id'] not in selected]
                    if kind=='residuals':
                        for n in numbers:
                            rr=[selected[o['observation_id']] for o in owned if selected[o['observation_id']]['norad']==n]
                            ax.scatter([r['time_s'] for r in rr],[r['residual_hz'] for r in rr],s=5,c=[colors[n]],label=str(n))
                        ax.axhline(0,c='black',lw=.6);ax.set_ylabel('CFO residual (Hz)')
                    else:
                        if kind=='all':
                            for n in numbers:
                                oo=[o for o in owned if selected[o['observation_id']]['norad']==n]
                                ax.scatter([o['time_s'] for o in oo],[o['measured_cfo_hz']/1000 for o in oo],s=7,c=[colors[n]],label=str(n))
                            for rr in groups.values():
                                rr=sorted([r for r in rr if r['receiver']==rx and r['channel']==ch],key=lambda r:r['time_s'])
                                if len(rr)<2:continue
                                t=np.array([r['time_s'] for r in rr]);v=np.array([r['prediction_hz']/1000 for r in rr])
                                v[np.r_[False,(np.diff(t)>3)|(abs(np.diff(v))>100)]]=np.nan
                                ax.plot(t,v,c=colors[rr[0]['norad']],lw=1)
                        ax.scatter([o['time_s'] for o in unowned],[o['measured_cfo_hz']/1000 for o in unowned],s=7,c='crimson',label='Unassociated')
                        if kind=='unassociated':
                            for tr in packet['tracks']:
                                if tr['receiver']!=rx or tr['channel']!=ch:continue
                                for v in native_polynomial(tr,raw):
                                    v=np.array(v);v[[oid in selected for oid in tr['observation_ids']]]=np.nan
                                    ax.plot(tr['times'],v/1000,c='#264653',lw=1)
                        ax.set_ylabel('Native CFO (kHz)')
                    ax.set_title(f'RX{rx} CH{ch} · {len(owned)}/{len(lane)} associated');ax.set_xlabel('Time (s)');ax.set_xlim(0,300);ax.grid(alpha=.2)
            fig.suptitle(f'{title}\nALGO07 selected result · {kind} · fitted c\nColored points = published satellite owners; red = unassociated. Lines = '+('remaining graph polynomials' if kind=='unassociated' else 'replayed conditional orbital predictions, including receiver corrections'),fontsize=11)
            save(f'ch{first}-{last}-{kind}',fig)
    fig=Figure(figsize=(16,6),layout='constrained');ax=fig.subplots()
    metrics=sorted([(key,float(np.sqrt(np.mean([r['residual_hz']**2 for r in rr]))),rr[0]['norad'],len(rr)) for key,rr in groups.items()],key=lambda a:-a[1])
    ax.bar(range(len(metrics)),[m[1] for m in metrics],color=[colors[m[2]] for m in metrics]);ax.set_xticks(range(len(metrics)),[f'{m[0]}\n{m[2]} · {m[3]} pts' for m in metrics],rotation=90,fontsize=5)
    ax.set(ylabel='Replayed RMS (Hz)',title=f'{title} · ALGO07 · RMS for every associated polynomial fragment');ax.grid(axis='y',alpha=.2);save('track-rms',fig)
    fig=Figure(figsize=(7,7),layout='constrained');ax=fig.subplots()
    center=(37.906,-122.545)
    for arm,color in [('c0','#277da8'),('fitted_c','#e76f51')]:
        lat,lon=packet['arms'][arm]['endpoint_latlon'];east=(lon-center[1])*111.32*np.cos(np.deg2rad(center[0]));north=(lat-center[0])*111.32
        ax.scatter([east],[north],c=color,s=80,label=arm);ax.annotate(f'{arm}\n{lat:.6f}, {lon:.6f}',(east,north),xytext=(7,7 if arm=='c0' else -25),textcoords='offset points',fontsize=8)
    ax.set(xlim=(-12.5,12.5),ylim=(-12.5,12.5),xlabel='East from configured regional center (km)',ylabel='North from configured regional center (km)',title=f'{title}\nALGO07 · published positions, both calibration arms\n25 × 25 km regional search');ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend();save('position',fig)
    return products
