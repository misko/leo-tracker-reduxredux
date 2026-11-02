"""Figures from exact published point owners and replayed CFO predictions."""
from collections import defaultdict
from io import BytesIO

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib import colormaps

from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.presentation.fast_scan_orbits import render_fast_scan_orbits


def render(packet, *, title):
    rows=packet['rows']['fitted_c'];raw={o['observation_id']:o for o in packet['observations']}
    numbers=sorted({r['norad'] for r in rows})
    colors={n:colormaps['tab20'](k%20) for k,n in enumerate(numbers)}
    products=render_fast_scan_orbits(packet['orbit_lanes'],title=title,alias_period_hz=PERIOD,
        subtitle='ALGO07 selected result · fitted c · receiver calibration removed; shared phase/orbit corrections included')
    groups=defaultdict(list)
    for r in rows:groups[r['component']].append(r)
    def save(name,fig):
        FigureCanvasAgg(fig);s=BytesIO();fig.savefig(s,format='png',dpi=125);products[name]=s.getvalue();fig.clear()
    for first,last in ((1,4),(5,8)):
        fig=Figure(figsize=(15,11),layout='constrained');axes=fig.subplots(4,2,squeeze=False)
        for ch in range(first,last+1):
            for rx in (1,2):
                ax=axes[ch-first,rx-1]
                lane=[o for o in raw.values() if o['receiver']==rx and o['channel']==ch]
                owned=[r for r in rows if r['receiver']==rx and r['channel']==ch]
                for n in numbers:
                    rr=[r for r in owned if r['norad']==n]
                    ax.scatter([r['time_s'] for r in rr],[r['residual_hz'] for r in rr],s=5,c=[colors[n]])
                ax.axhline(0,c='black',lw=.6);ax.set_ylabel('CFO residual (Hz)')
                ax.set_title(f'RX{rx} CH{ch} · {len(owned)}/{len(lane)} associated');ax.set_xlabel('Time (s)');ax.set_xlim(0,300);ax.grid(alpha=.2)
        fig.suptitle(f'{title}\nALGO07 selected result · conditional residuals · fitted c',fontsize=11)
        save(f'ch{first}-{last}-residuals',fig)
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
