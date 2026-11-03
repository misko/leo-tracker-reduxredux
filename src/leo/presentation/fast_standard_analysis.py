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
from leo.presentation.regional_position import draw_position_grid


def position_figure(arms, *, title, selected_model=None, evaluation_reference=None, position_grid=None,
                    position_path=None):
    """Legacy diagnostic-map conventions over sealed ALGO07 endpoints."""
    center=(37.906,-122.545)
    def project(latlon, origin=center):
        lat,lon=map(math.radians,latlon);a,b=map(math.radians,origin)
        h=math.sin((lat-a)/2)**2+math.cos(a)*math.cos(lat)*math.sin((lon-b)/2)**2
        distance=12742.0176*math.asin(math.sqrt(min(1,max(0,h))))
        bearing=math.atan2(math.sin(lon-b)*math.cos(lat),
            math.cos(a)*math.sin(lat)-math.sin(a)*math.cos(lat)*math.cos(lon-b))
        return distance*math.sin(bearing),distance*math.cos(bearing)
    figure=Figure(figsize=(14,8) if position_path is not None else (9,8),layout='constrained')
    axes=list(figure.subplots(1,2)) if position_path is not None else [figure.subplots()]
    axis=axes[0]
    def plot_coordinates(latlon):
        if position_grid is None and position_path is None:return project(latlon)
        # Use the solver's declared local coordinates for grid, fits and reference.
        lat,lon=latlon
        return ((lon-center[1])*111.32*math.cos(math.radians(center[0])),
                (lat-center[0])*111.0)
    if position_grid is not None:
        draw_position_grid(figure,axis,
            ((p['east_km'],p['north_km'],p['scores']['fitted_c']) for p in position_grid['points']),
            score_label='Conditional fitted-c objective (lower is better)')
    model='ALGO07'
    if selected_model and not selected_model.startswith('algo07-'):
        model+=' · retained '+selected_model.split('-')[0].upper()
    figure.suptitle(f'{title}\n{model} · diagnostic position map')
    descriptions=[]
    reference=None if evaluation_reference is None else (
        evaluation_reference['latitude_deg'],evaluation_reference['longitude_deg'])
    for arm,marker,color,label in [('fitted_c','D','red','Fitted c'),('c0','s','blue','c = 0')]:
        row=arms[arm];east,north=plot_coordinates(row['endpoint_latlon'])
        for ax in axes:
            ax.plot(east,north,marker=marker,color=color,linestyle='none',markersize=7,zorder=8,
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
        for ax in axes:
            ax.plot(*plot_coordinates(reference),'k+',markersize=11,markeredgewidth=1.7,zorder=9,
                    label='Reference (evaluation only)')
    for ax in axes:
        ax.plot(0,0,marker='+',color='gray',linestyle='none',markersize=7,
                label='Regional search centre')
    if position_path is not None:
        final=position_path['stages'][-1]['arms']['fitted_c']['endpoint']
        zoom_points=[final,plot_coordinates(arms['c0']['endpoint_latlon'])]
        if reference is not None:zoom_points.append(plot_coordinates(reference))
        labels=set();starts=[]
        for stage in position_path['stages']:
            for arm,color,style,label in [('fitted_c','crimson','-','Fitted c'),('c0','royalblue','--','c = 0')]:
                row=stage['arms'][arm]
                for r in row['rounds']:
                    points=r['points'];detailed=r['detail']=='accepted_optimizer_iterates'
                    legend=f'{label} recorded '+('accepted steps' if detailed else 'phase-round endpoints')
                    for ax in axes:
                        ax.plot([p[0] for p in points],[p[1] for p in points],
                            linestyle=style if detailed else 'none',marker='o',ms=3,lw=1.5,
                            color=color,alpha=.85,zorder=5,label=legend if (id(ax),legend) not in labels else '_nolegend_')
                        labels.add((id(ax),legend))
                    if arm=='fitted_c' and math.dist(r['endpoint'],final)<2:
                        zoom_points.append(r['endpoint'])
                if row['rounds']:
                    start=row['rounds'][0]['points'][0]
                    if start not in starts:starts.append(start)
        for number,start in enumerate(starts):
            for ax in axes:
                ax.plot(*start,marker='*',ms=12,color='#f39c12',linestyle='none',zorder=10,
                        label='Recorded fit start' if number==0 else '_nolegend_')
        if starts:
            axis.annotate('Start',starts[0],xytext=(8,9),textcoords='offset points',fontsize=8)
        zoom=axes[1];groups=[]
        for r in position_path['stages'][-1]['arms']['fitted_c']['rounds']:
            if groups and math.dist(groups[-1][0],r['endpoint'])<.01:
                groups[-1][1].append(r['round'])
            else:groups.append((r['endpoint'],[r['round']]))
        for index,(point,rounds) in enumerate(groups):
            label=f'Phase round {rounds[0]}' if len(rounds)==1 else f'Phase rounds {rounds[0]}–{rounds[-1]}'
            zoom.plot(*point,marker='o',ms=8,mfc='none',mec='crimson',linestyle='none',zorder=9)
            zoom.annotate(label,point,xytext=(12,20 if index%2==0 else -35),textcoords='offset points',
                          fontsize=8,arrowprops=dict(arrowstyle='->',color='#555555'))
        low=[min(p[k] for p in zoom_points) for k in (0,1)]
        high=[max(p[k] for p in zoom_points) for k in (0,1)]
        span=max(high[0]-low[0],high[1]-low[1],.5)*1.65
        mid=[(lo+hi)/2 for lo,hi in zip(low,high)]
        zoom.set(xlim=(mid[0]-span/2,mid[0]+span/2),ylim=(mid[1]-span/2,mid[1]+span/2),
                 title='Recorded refinements · display zoom only')
        if not position_path['stages'][-1]['arms']['fitted_c']['history_available']:
            zoom.text(.03,.97,'Intermediate history was not saved for this fit.',transform=zoom.transAxes,
                      va='top',fontsize=8)
    grid_summary='' if position_grid is None else (
        f" · {position_grid['evaluated_points']}/{position_grid['planned_points']} grid locations")
    axis.set(title='25 × 25 km regional search'+grid_summary+'\n'+'\n'.join(descriptions),
        xlabel='East of prior centre (km)',ylabel='North of prior centre (km)',
        xlim=(-12.5,12.5),ylim=(-12.5,12.5))
    for ax in axes:
        ax.set_aspect('equal');ax.grid(alpha=.2)
        ax.set_xlabel('East of prior centre (km)');ax.set_ylabel('North of prior centre (km)')
        ax.legend(fontsize=7 if position_path else 8,loc='lower left')
    note='Both calibration arms use the same observations and candidate set.'
    if position_grid is not None:
        note=('Conditional loss: fixed satellite associations and phase linearization; nuisance model re-evaluated.\n'
              'Matched grid for both c arms. '+('Complete grid.' if position_grid['complete'] else 'Partial grid: time budget reached.'))
    if position_path is not None:
        note=('Lines/markers: saved optimizer steps and phase rounds; separate fits are not connected.\n'
              'Allowed area stays 25 × 25 km; right panel is a display zoom. '
              +('Coloured grid: post-fit conditional loss.' if position_grid else ''))
    figure.supxlabel('Reference coordinates enter only this presentation stage.\n'+note,fontsize=8)
    return figure


def render_position(arms, *, title, selected_model=None, evaluation_reference=None, position_grid=None,
                    position_path=None):
    figure=position_figure(arms,title=title,selected_model=selected_model,
                           evaluation_reference=evaluation_reference,position_grid=position_grid,
                           position_path=position_path)
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
        selected_model=packet.get('selected_model'),evaluation_reference=evaluation_reference,
        position_grid=packet.get('position_grid'),position_path=packet.get('position_path'))
    return products
