"""Full-scan detection and targeted track comparisons, without hiding extra candidates."""
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
BASE=REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
FULL=REPORTS/'2026_09_30_arm_full_scan_comparison'
sys.path.insert(0,str(REPORTS/'2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m


def main():
    inv=json.loads((HERE/'arm/inventory.json').read_text())
    so=m.read_observations(BASE/'server-observations.tsv')
    ss=m.read_sources(BASE/'server-candidate-map.tsv',so)
    ao=m.read_observations(BASE/'arm-observations.tsv');ars=m.read_sources(BASE/'arm-candidate-map.tsv',ao)
    no=m.read_observations(HERE/'analysis/observations.tsv');ns=m.read_sources(HERE/'analysis/candidate-map.tsv',no)
    server_by_source={}
    for cid,o in so.items():server_by_source.setdefault(ss[cid],[]).append(o)
    counts={}
    fig,axes=plt.subplots(2,3,figsize=(18,9),sharex=True,sharey=True,layout='constrained')
    for col,(label,obs,sources) in enumerate([('Server',so,ss),('Original ARM cutoff',ao,ars),('ARM cutoff disabled',no,ns)]):
        counts[label]={'passing':len(obs),'server_cfo_agreement':0,'no_server_cfo_agreement':0}
        for rx in [0,1]:
            yes=[];unmatched=[]
            for cid,o in obs.items():
                source=sources[cid]
                if source[1]!=rx:continue
                scale=11.2e9/o.lane.rf_hz
                agree=any(m.circular_distance(o.measured_cfo_hz-s.measured_cfo_hz,1/4.4e-6)*scale<=2500 for s in server_by_source.get(source,[]))
                (yes if agree else unmatched).append((inv[source[0]]['capture_time_s'],o.measured_cfo_hz/1000))
            ax=axes[rx,col]
            if yes:
                t,f=np.array(yes).T;ax.scatter(t,f,s=3,alpha=.55,color=['#778899','#287ab5','#15865d'][col],rasterized=True)
            if unmatched:
                t,f=np.array(unmatched).T;ax.scatter(t,f,s=7,alpha=.6,color='#d47626',marker='x',linewidths=.5,rasterized=True)
            counts[label]['server_cfo_agreement']+=len(yes);counts[label]['no_server_cfo_agreement']+=len(unmatched)
            ax.set_title(f'{label} · RX{rx}\n{len(yes)+len(unmatched):,} passing entries'+(f'; {len(unmatched):,} without server CFO agreement' if col else ''))
            ax.set(xlim=(0,300),xlabel='Time from scan start (s)');ax.grid(alpha=.15)
            if col==0:ax.set_ylabel('Measured tracking CFO (kHz)')
    fig.suptitle('Full 300-second DS9 scan · every dwell processed on ARM\n'
                 'Passing candidates only (GLRT margin ≥0.025). Orange = no same-source server CFO agreement, not proven noise.\n'
                 'Raw CFO is not dealiased; channels combined within each receiver. Candidate entries include duplicate hypotheses.',fontsize=12)
    fig.savefig(HERE/'full-scan-cfo.png',dpi=155);fig.savefig(HERE/'full-scan-cfo.pdf');plt.close(fig)
    (HERE/'detection-agreement.json').write_text(json.dumps(counts,indent=2)+'\n')
    refs=m.read_tracks(BASE/'server-tracks.tsv',so).values
    old=m.read_tracks(REPORTS/'2026_09_30_arm_streaming_tracks/qualification/rolling-backfill/arm-0.tsv',ao).values
    new=m.read_tracks(HERE/'analysis/tracks-0.tsv',no).values
    settings=json.loads((REPORTS/'2026_09_30_arm_curvature_tracks/evaluation/thresholds.json').read_text())
    origin=min(o.start_ns for o in so.values());target_rows=[]
    fig,axes=plt.subplots(5,2,figsize=(14,17),layout='constrained')
    for row,index in enumerate([2,30,8,34,47]):
        ref=refs[index];record={'reference':index};spacing=11.2e9/ref.lane.rf_hz/4.4e-6
        t,f=np.array(sorted(((so[p.candidate].center_ns-origin)/1e9,p.dealiased_cfo_hz) for p in ref.points)).T
        vals=list(f)
        for col,(label,bank,obs,sources,color) in enumerate([('Original',old,ao,ars,'#d47820'),('Cutoff disabled',new,no,ns,'#15865d')]):
            choices=[(m.membership_metrics(ref,tr,so,obs,ss,sources,settings),tr) for tr in bank if tr.lane==ref.lane]
            met,tr=max(choices,key=lambda v:(m.complete(v[0],settings),v[0]['consistent_source_count'],v[0]['in_span_output_purity']))
            record[label]={'output_index':tr.index,'complete':m.complete(met,settings),**met}
            ax=axes[row,col];ax.plot(t,f/1000,'o-',mfc='none',ms=4,color='#aeb5bb',lw=.6,label='Server reference')
            if met['consistent_source_count']:
                tt,ff=np.array(sorted(((obs[p.candidate].center_ns-origin)/1e9,p.dealiased_cfo_hz) for p in tr.points
                                     if ref.start_ns<=obs[p.candidate].center_ns<=ref.end_ns)).T
                ff+=np.round((np.interp(tt,t,f)-ff)/spacing)*spacing;vals.extend(ff)
                ax.plot(tt,ff/1000,'.-',ms=4,color=color,lw=.7,label='Tracker membership')
            title=f'#{index}: {label}\n{met["consistent_source_count"]}/{len(ref.points)} matching sources'
            if met['consistent_source_count']:title+=f', purity {met["in_span_output_purity"]:.1%}'
            ax.set(title=title,xlim=(t[0]-1,t[-1]+1),xlabel='Seconds from first projected observation',ylabel='Alias-aligned CFO (kHz)');ax.grid(alpha=.15)
            if row==0:ax.legend(fontsize=9)
        lo,hi=min(vals)/1000,max(vals)/1000
        for ax in axes[row]:ax.set_ylim(lo-(hi-lo)*.06,hi+(hi-lo)*.06)
        target_rows.append(record)
    fig.suptitle('Same rolling-backfill tracker, original versus cutoff-disabled full-scan GLRT\n'
                 'Five previously missing long references; unchanged matching thresholds',fontsize=13)
    fig.savefig(HERE/'five-long-tracks.png',dpi=140);fig.savefig(HERE/'five-long-tracks.pdf');plt.close(fig)
    (HERE/'five-long-tracks.json').write_text(json.dumps(target_rows,indent=2)+'\n')
    print(json.dumps(counts,indent=2))

if __name__=='__main__':main()
