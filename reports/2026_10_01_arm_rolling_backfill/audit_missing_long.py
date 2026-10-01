"""Audit all remaining long misses without changing tracker or scoring."""
import json
from pathlib import Path
import sys
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
BASE=REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
QUAL=REPORTS/'2026_09_30_arm_streaming_tracks/qualification/rolling-backfill'
PREV=REPORTS/'2026_09_30_arm_curvature_tracks'
sys.path.insert(0,str(PREV/'evaluation'))
import compare_membership as m


def main():
    dest=HERE/'missing-long';dest.mkdir(exist_ok=True)
    so=m.read_observations(BASE/'server-observations.tsv')
    ao=m.read_observations(BASE/'arm-observations.tsv')
    ss=m.read_sources(BASE/'server-candidate-map.tsv',so)
    ars=m.read_sources(BASE/'arm-candidate-map.tsv',ao)
    refs=m.read_tracks(BASE/'server-tracks.tsv',so).values
    settings=json.loads((PREV/'evaluation/thresholds.json').read_text())
    evaluation=json.loads((QUAL/'arm-evaluation.json').read_text())
    missing=set(evaluation['reviewed']['missing_indexes'])
    targets=sorted([r for r in refs if r.index in missing and (r.end_ns-r.start_ns)/1e9>=30],
                   key=lambda r:r.end_ns-r.start_ns,reverse=True)
    banks={'backfill':(m.read_tracks(QUAL/'arm-0.tsv',ao).values,ao,ars),
           'server_input':(m.read_tracks(QUAL/'server-0.tsv',so).values,so,ss),
           'coarse_seeded':(m.read_tracks(PREV/'hybrid-v1/host/arm-a250-v2.tsv',ao).values,ao,ars)}
    origin=min(o.start_ns for o in so.values())
    fig,axes=plt.subplots(len(targets),2,figsize=(15,3.5*len(targets)),layout='constrained')
    rows=[]
    for axes_row,ref in zip(axes,targets):
        record={'reference':ref.index,'channel':ref.lane.channel,'receiver':ref.lane.receiver,
                'duration_s':(ref.end_ns-ref.start_ns)/1e9,'reference_points':len(ref.points),
                'required_matching_sources':math.ceil(.8*len(ref.points))}
        support=next(x for x in evaluation['reference_input_support'] if x['reference_track_index']==ref.index)
        record['input_support']=support
        record['union']=next(x for x in evaluation['fragment_union_coverage'] if x['reference_track_index']==ref.index)
        best_track=None
        for label,(tracks,obs,sources) in banks.items():
            candidates=[(m.membership_metrics(ref,t,so,obs,ss,sources,settings),t)
                        for t in tracks if t.lane==ref.lane]
            met,track=max(candidates,key=lambda x:(x[0]['consistent_source_count'],x[0]['in_span_output_purity']))
            record[label]={'track':track.index,'complete':m.complete(met,settings),**met}
            if label=='backfill':best_track=track
        spacing=settings['alias_spacing_hz']*settings['canonical_rf_hz']/ref.lane.rf_hz
        points=sorted(ref.points,key=lambda p:so[p.candidate].center_ns)
        t=np.array([(so[p.candidate].center_ns-origin)/1e9 for p in points])
        f=np.array([p.dealiased_cfo_hz for p in points])
        matched=set(record['backfill']['consistent_sources'])
        evidence=[]
        for p in points:
            source=ss[p.candidate];source_text=':'.join(map(str,source))
            candidates=[o for cid,o in ao.items() if o.lane==ref.lane and ars[cid]==source]
            nearest=min((m.circular_distance(o.measured_cfo_hz*settings['canonical_rf_hz']/ref.lane.rf_hz-p.raw_cfo_hz,spacing)
                         for o in candidates),default=None)
            evidence.append({'source':source_text,'time_s':(so[p.candidate].center_ns-origin)/1e9,
                'arm_candidates':len(candidates),'nearest_cfo_error_hz':nearest,
                'available':nearest is not None and nearest<=settings['same_source_circular_cfo_gate_hz'],
                'in_best_output':source_text in matched})
        record['evidence']=evidence
        record['available_but_omitted']=[e for e in evidence if e['available'] and not e['in_best_output']]
        record['absent_source_count']=sum(e['arm_candidates']==0 for e in evidence)
        record['wrong_cfo_only_count']=sum(e['arm_candidates']>0 and not e['available'] for e in evidence)
        available_evidence=[e for e in evidence if e['available']]
        record['available_evidence_gaps_over_4s']=[{'from_s':a['time_s'],'to_s':b['time_s'],
            'gap_s':b['time_s']-a['time_s']} for a,b in zip(available_evidence,available_evidence[1:])
            if b['time_s']-a['time_s']>4]
        for ax in axes_row:
            ax.plot(t,f/1000,'o-',mfc='none',ms=4,color='#aaa',lw=.7,label='Server reference')
            ax.set(xlabel='Seconds from first observation',ylabel='CFO (kHz)',xlim=(t[0]-1,t[-1]+1))
            ax.grid(alpha=.2)
        available=np.array([e['available'] for e in evidence])
        axes_row[0].scatter(t[available],f[available]/1000,s=15,color='#187db5',label='Matching ARM evidence')
        axes_row[0].set_title(f'#{ref.index} Ch{ref.lane.channel}/RX{ref.lane.receiver}: {record["duration_s"]:.1f}s\n'
                              f'ARM input: {sum(available)}/{len(points)} reference sources available')
        ff=f.copy()
        if record['backfill']['consistent_source_count']:
            tt,ff=np.array(sorted(((ao[p.candidate].center_ns-origin)/1e9,p.dealiased_cfo_hz)
                         for p in best_track.points if ref.start_ns<=ao[p.candidate].center_ns<=ref.end_ns)).T
            ff+=np.round((np.interp(tt,t,f)-ff)/spacing)*spacing
            axes_row[1].plot(tt,ff/1000,'.-',color='#c67116',ms=5,lw=.8,label='Best backfill output')
        else:
            axes_row[1].text(.5,.5,'No output contains matching reference points',
                             transform=axes_row[1].transAxes,ha='center')
        purity_label=(f'In-span purity {record["backfill"]["in_span_output_purity"]:.1%}'
                      if record['backfill']['consistent_source_count'] else 'No matching output')
        axes_row[1].set_title(f'#{ref.index}: best output {record["backfill"]["consistent_source_count"]}/{len(points)}\n'
                              +purity_label)
        lo,hi=min(min(f),min(ff))/1000,max(max(f),max(ff))/1000
        for ax in axes_row:ax.set_ylim(lo-(hi-lo)*.06,hi+(hi-lo)*.06)
        rows.append(record)
    for ax in axes[0]:ax.legend(fontsize=8)
    fig.savefig(dest/'comparison.png',dpi=130)
    fig.savefig(dest/'comparison.pdf')
    plt.close(fig)
    (dest/'audit.json').write_text(json.dumps({'rows':rows},indent=2)+'\n')
    for r in rows:
        print(json.dumps({k:r[k] for k in ['reference','duration_s','reference_points','input_support','absent_source_count','wrong_cfo_only_count']}))
        print({label:{k:r[label][k] for k in ['consistent_source_count','in_span_output_purity','complete']} for label in banks})
        print('available omitted',r['available_but_omitted'])


if __name__=='__main__':main()
