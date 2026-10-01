"""CFO plots of the same 85 physical replay dwells, with GLRT filtering visible."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE=Path(__file__).resolve().parent
FULL=HERE.parent/'2026_09_30_arm_full_scan_comparison'
BASE=HERE.parent/'2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0,str(HERE.parent/'2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m


def main():
    inventory={r['visit']:r for r in json.loads((FULL/'arm-v2/inventory.json').read_text())}
    rows={'ordinary':[],'ungated':[]};visits=[]
    for p in sorted((HERE/'physical').glob('visits-*.json')):
        ids=json.loads(p.read_text());visits.extend(ids)
        suffix=p.stem.split('-')[1]
        for label in rows:
            for line in (p.parent/f'{label}-{suffix}.jsonl').read_text().splitlines():
                doc=json.loads(line)
                if 'result' not in doc:continue
                call=doc['result'];visit=ids[call['sequence']]
                for row in call['rows']:
                    for c in row['candidates']:
                        rows[label].append({**c,'visit':visit,'rx':row['receiver_id'],
                            't':inventory[visit]['capture_time_s']})
    assert len(visits)==len(set(visits))==85
    server=[]
    for visit in visits:
        doc=json.loads((FULL/f'server/visits/visit-{visit:06d}.json').read_text())
        for rx in [0,1]:
            for c in doc['candidates'][str(rx)]:
                if c['passed_fractional_margin_gate']:
                    server.append({'visit':visit,'rx':rx,'t':inventory[visit]['capture_time_s'],
                                   'tracking_cfo_hz':c['fractional_tracking_cfo_hz']})
    def agrees(c):
        event=inventory[c['visit']]['event']
        scale=11.2e9/(event['target']['rf_center_hz']-event['actual_if_offset_hz'])
        return any(m.circular_distance(c['tracking_cfo_hz']-s['tracking_cfo_hz'],1/4.4e-6)*scale<=2500
                   for s in server if (s['visit'],s['rx'])==(c['visit'],c['rx']))
    for values in rows.values():
        for c in values:c['server_agreement']=agrees(c)
    counts={label:{'evaluated':len(values),'passed':sum(c['margin']>=.025 for c in values),
        'below_gate':sum(c['margin']<.025 for c in values),
        'passing_server_agreement':sum(c['margin']>=.025 and c['server_agreement'] for c in values),
        'passing_without_server_agreement':sum(c['margin']>=.025 and not c['server_agreement'] for c in values)}
        for label,values in rows.items()}
    fig,axes=plt.subplots(2,3,figsize=(18,9),sharex=True,sharey=True,layout='constrained')
    colors={'server':'#8c96a0','original':'#2479bb','rejected':'#c4c8cd','agree':'#16875b','unmatched':'#d56c19'}
    def scatter(ax,values,**kwargs):
        if values:ax.scatter([c['t'] for c in values],[c['tracking_cfo_hz']/1000 for c in values],**kwargs)
    for rx in [0,1]:
        ss=[c for c in server if c['rx']==rx]
        old=[c for c in rows['ordinary'] if c['rx']==rx and c['margin']>=.025]
        allnew=[c for c in rows['ungated'] if c['rx']==rx]
        passed=[c for c in allnew if c['margin']>=.025]
        rejected=[c for c in allnew if c['margin']<.025]
        for ax in axes[rx]:
            scatter(ax,ss,s=33,facecolors='none',edgecolors=colors['server'],linewidths=.7,zorder=1)
            ax.plot([inventory[v]['capture_time_s'] for v in visits],[.018]*len(visits),'|',
                    transform=ax.get_xaxis_transform(),color='#596675',ms=4,alpha=.5)
            ax.grid(alpha=.15);ax.set_xlim(0,300)
            ax.set_xlabel('Time from scan start (s)')
        scatter(axes[rx,0],old,s=14,color=colors['original'],zorder=3)
        axes[rx,0].set_title(f'RX{rx}: original cutoff\n{len(old)} candidates pass final GLRT')
        scatter(axes[rx,1],rejected,s=11,color=colors['rejected'],alpha=.6,zorder=2)
        for col in [1,2]:
            scatter(axes[rx,col],[c for c in passed if c['server_agreement']],s=18,color=colors['agree'],zorder=3)
            scatter(axes[rx,col],[c for c in passed if not c['server_agreement']],s=30,marker='x',color=colors['unmatched'],zorder=4)
        axes[rx,1].set_title(f'RX{rx}: coarse cutoff removed — all evaluated\n{len(rejected)} rejected by final GLRT; {len(passed)} pass')
        axes[rx,2].set_title(f'RX{rx}: coarse cutoff removed — passing only\n{sum(not c["server_agreement"] for c in passed)} lack server CFO agreement')
        axes[rx,0].set_ylabel('Measured tracking CFO (kHz)')
    legend=[Line2D([],[],marker='o',ls='',mfc='none',mec=colors['server'],label='Server passing candidate'),
            Line2D([],[],marker='o',ls='',color=colors['original'],label='Original ARM passing candidate'),
            Line2D([],[],marker='o',ls='',color=colors['rejected'],label='Below final GLRT gate'),
            Line2D([],[],marker='o',ls='',color=colors['agree'],label='Passes; agrees with server CFO'),
            Line2D([],[],marker='x',ls='',color=colors['unmatched'],label='Passes; no server CFO agreement')]
    fig.legend(handles=legend,loc='outside lower center',ncol=3,fontsize=10)
    fig.suptitle('Removing the coarse cutoff: CFO versus time on the same 85 selected dwells\n'
        'Final GLRT margin ≥0.025 remains active. Bottom tick marks show replayed dwells; gaps were not replayed.\n'
        'Raw CFO is not dealiased; channels are combined within each receiver. Orange points are not proven noise.',fontsize=12)
    fig.savefig(HERE/'cfo-cutoff-comparison.png',dpi=150)
    fig.savefig(HERE/'cfo-cutoff-comparison.pdf')
    plt.close(fig)
    # Reference-aligned zooms show recovered points without hiding the overview's extra candidates.
    so=m.read_observations(BASE/'server-observations.tsv');ao=m.read_observations(BASE/'arm-observations.tsv')
    ss=m.read_sources(BASE/'server-candidate-map.tsv',so);ars=m.read_sources(BASE/'arm-candidate-map.tsv',ao)
    refs=m.read_tracks(BASE/'server-tracks.tsv',so).values
    results=json.loads((HERE/'results.json').read_text())
    fig,axes=plt.subplots(3,2,figsize=(14,11),layout='constrained')
    for ax,index in zip(axes.flat,[2,30,8,34,47]):
        ref=refs[index];spacing=11.2e9/ref.lane.rf_hz/4.4e-6
        points=sorted(ref.points,key=lambda p:so[p.candidate].center_ns)
        tt=[];ff=[];old_t=[];old_f=[];new_t=[];new_f=[]
        for p in points:
            source=ss[p.candidate];visit,rx,_=source;t=inventory[visit]['capture_time_s'];f=p.dealiased_cfo_hz
            tt.append(t);ff.append(f/1000)
            matching=[o for cid,o in ao.items() if o.lane==ref.lane and ars[cid]==source and
                m.circular_distance(o.measured_cfo_hz*11.2e9/ref.lane.rf_hz-p.raw_cfo_hz,spacing)<=2500]
            if matching:
                raw=matching[0].measured_cfo_hz*11.2e9/ref.lane.rf_hz
                old_t.append(t);old_f.append((raw+round((f-raw)/spacing)*spacing)/1000)
            recovered=next((r for r in results['records'] if r['reference']==index and r['visit']==visit and r['ungated_recovered']),None)
            if recovered:
                raw=recovered['ungated_matching_candidates'][0]['tracking_cfo_hz']*11.2e9/ref.lane.rf_hz
                new_t.append(t);new_f.append((raw+round((f-raw)/spacing)*spacing)/1000)
        ax.plot(tt,ff,'o-',mfc='none',ms=5,color='#abb2b9',lw=.6,label='Server reference')
        ax.scatter(old_t,old_f,s=15,color=colors['original'],label='Already available ARM detection',zorder=3)
        ax.scatter(new_t,new_f,s=28,marker='+',linewidths=1.6,color=colors['agree'],label='Recovered with cutoff disabled',zorder=4)
        ax.set_title(f'Ref #{index} · Ch{ref.lane.channel}/RX{ref.lane.receiver}\n'
                     f'{len(old_t)} existing + {len(new_t)} recovered / {len(points)} server sources')
        ax.set(xlabel='Time from scan start (s)',ylabel='Alias-aligned normalized CFO (kHz)');ax.grid(alpha=.2)
    axes.flat[-1].axis('off');handles,labels=axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(handles,labels,loc='upper left',bbox_to_anchor=(.04,.90),fontsize=11)
    axes.flat[-1].text(.05,.23,'Detection availability, not reconstructed tracks.\n'
        'Only target-matching points shown in these zooms;\nextra candidates remain visible in the overview.\n'
        'Aliases aligned to each reference for display only.',transform=axes.flat[-1].transAxes,fontsize=10)
    fig.suptitle('Where the 67 recovered detections lie on the five server tracks',fontsize=14)
    fig.savefig(HERE/'cfo-recovered-track-zooms.png',dpi=145)
    fig.savefig(HERE/'cfo-recovered-track-zooms.pdf')
    plt.close(fig)
    (HERE/'plot-counts.json').write_text(json.dumps({'counts':counts,'dwells':85,
        'agreement':'Same visit/RX; circular CFO difference normalized to 11.2 GHz <=2500 Hz; not one-to-one, no epoch gate',
        'scope':'Selected missing-detection dwells; unmatched candidates are not established noise'},indent=2)+'\n')
    print(json.dumps(counts,indent=2))

if __name__=='__main__':main()
