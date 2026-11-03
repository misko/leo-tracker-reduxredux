"""Figures from exact published point owners and replayed CFO predictions."""
from collections import defaultdict
from io import BytesIO
import math

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib import colormaps

from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.presentation.fast_scan_orbits import render_fast_scan_orbits


def position_figure(arms, *, title, selected_model=None, evaluation_reference=None):
    """Legacy diagnostic-map conventions over sealed ALGO07 endpoints."""
    center=(37.906,-122.545)
    def project(latlon, origin=center):
        lat,lon=map(math.radians,latlon);a,b=map(math.radians,origin)
        h=math.sin((lat-a)/2)**2+math.cos(a)*math.cos(lat)*math.sin((lon-b)/2)**2
        distance=12742.0176*math.asin(math.sqrt(min(1,max(0,h))))
        bearing=math.atan2(math.sin(lon-b)*math.cos(lat),
            math.cos(a)*math.sin(lat)-math.sin(a)*math.cos(lat)*math.cos(lon-b))
        return distance*math.sin(bearing),distance*math.cos(bearing)
    figure=Figure(figsize=(9,8),layout='constrained');axis=figure.subplots()
    model='ALGO07'
    if selected_model and not selected_model.startswith('algo07-'):
        model+=' · retained '+selected_model.split('-')[0].upper()
    figure.suptitle(f'{title}\n{model} · diagnostic position map')
    descriptions=[]
    reference=None if evaluation_reference is None else (
        evaluation_reference['latitude_deg'],evaluation_reference['longitude_deg'])
    for arm,marker,color,label in [('fitted_c','D','red','Fitted c'),('c0','s','blue','c = 0')]:
        row=arms[arm];east,north=project(row['endpoint_latlon'])
        axis.plot(east,north,marker=marker,color=color,linestyle='none',markersize=7,
            label=f'{label} selected estimate')
        summary=f'{label}: '
        if reference is not None:
            delta=project(row['endpoint_latlon'],reference)
            summary+=f'reference error {math.hypot(*delta)*1000:,.1f} m'
        else:
            summary+='evaluation reference unavailable'
        if 'residual_rms_hz' in row:summary+=f"; residual RMS {row['residual_rms_hz']:.1f} Hz"
        descriptions.append(summary)
    if reference is not None:
        axis.plot(*project(reference),'k+',markersize=11,markeredgewidth=1.7,
                  label='Reference (evaluation only)')
    axis.plot(0,0,marker='+',color='gray',linestyle='none',markersize=7,
              label='Regional search centre')
    axis.set(title='25 × 25 km regional search\n'+'\n'.join(descriptions),
        xlabel='East of prior centre (km)',ylabel='North of prior centre (km)',
        xlim=(-12.5,12.5),ylim=(-12.5,12.5))
    axis.set_aspect('equal');axis.grid(alpha=.2);axis.legend(fontsize=8,loc='lower left')
    figure.supxlabel('Reference coordinates enter only this presentation stage.\n'
        'Both calibration arms use the same observations and candidate set.',fontsize=8)
    return figure


def render_position(arms, *, title, selected_model=None, evaluation_reference=None):
    figure=position_figure(arms,title=title,selected_model=selected_model,
                           evaluation_reference=evaluation_reference)
    FigureCanvasAgg(figure);stream=BytesIO();figure.savefig(stream,format='png',dpi=120)
    figure.clear();return stream.getvalue()


def render(packet, *, title, evaluation_reference=None):
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
    products['position']=render_position(packet['arms'],title=title,
        selected_model=packet.get('selected_model'),evaluation_reference=evaluation_reference)
    return products
