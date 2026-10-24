"""Summarize fixed-evidence DS24 diagnostics; GPS enters evaluation only."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from audit_evidence import OUT,ROOTS,read,write,summary

def graph_noise(cases):
    from localize_merged_track_catalogue import raw_curvature
    rows=[]
    for case in cases:
        for group,root in ROOTS.items():
            squares=defaultdict(list)
            for track in read(root/case/'tracks.json'):
                t,y=np.asarray(track['times']),np.asarray(track['values'])
                if not raw_curvature(dict(times=t,values=y)):continue
                for piece in track['pieces']:
                    use=(t>=piece['start_s'])&(t<=piece['end_s']);degree=piece['degree']
                    if use.sum()<2*(degree+1)+3:continue
                    tt,yy=t[use],y[use];z=(tt-tt.mean())/max(1.,float(np.ptp(tt)))
                    q,_=np.linalg.qr(np.vander(z,degree+1,increasing=True));h=np.sum(q*q,axis=1)
                    e=yy-q@(q.T@yy)
                    key=(track['receiver'],'low' if track['channel']<=4 else 'high')
                    squares[key].extend(e*e/(1-h))
            for (rx,band),v in squares.items():
                rows.append(dict(case=case,group=group,receiver=rx,band=band,points=len(v),radio_scatter_hz=float(np.sqrt(np.mean(v)))))
    return rows

def main():
    q=read(OUT/'evidence_quick.json');r=read(OUT/'residuals.json');tracks=r['tracks'];families=r['families']
    differences=[]
    for record in q['records']:
        rr=[x for x in tracks if all(x[k]==record[k] for k in ('case','group','arm'))]
        n=sum(x['points'] for x in rr)
        assert n==record['curved_points']
        rms=np.sqrt(sum(x['points']*x['RMS_hz']**2 for x in rr)/n)
        differences.append(abs(rms-record['RMS_hz']))
    assert len(differences)==144 and max(differences)<1e-6
    grouped={};strata=[]
    for group in ROOTS:
        for arm in ('c0','fitted_c'):
            rr=[x for x in tracks if x['group']==group and x['arm']==arm]
            grouped[group+'/'+arm]=dict(tracks=len(rr),points=sum(x['points'] for x in rr),
                pooled_RMS_hz=float(np.sqrt(sum(x['RMS_hz']**2*x['points'] for x in rr)/sum(x['points'] for x in rr))),
                track_lag1_ACF=summary([x['lag1_acf'] for x in rr]),
                tracks_exceeding_legacy_ACF_threshold=sum(x['acf_exceeds_legacy_threshold'] for x in rr),
                absolute_half_mean_step_hz=summary([abs(x['half_mean_step_hz']) for x in rr]),
                standardized_track_RMS=summary([x['standardized_RMS'] for x in rr]))
            for rx in (1,2):
                for band in ('low','high'):
                    ss=[x for x in rr if x['receiver']==rx and ('low' if x['channel']<=4 else 'high')==band]
                    if not ss:continue
                    scan_rms=[]
                    for case in q['cases']:
                        tt=[x for x in ss if x['case']==case]
                        if tt:scan_rms.append(np.sqrt(sum(x['points']*x['RMS_hz']**2 for x in tt)/sum(x['points'] for x in tt)))
                    strata.append(dict(group=group,arm=arm,receiver=rx,band=band,tracks=len(ss),points=sum(x['points'] for x in ss),scan_RMS_hz=summary(scan_rms),track_standardized_RMS=summary([x['standardized_RMS'] for x in ss]),track_ACF=summary([x['lag1_acf'] for x in ss])))
    active={(x['case'],x['group'],x['arm'],x['norad']) for x in tracks}
    phase={(x['case'],x['group'],x['arm'],x['norad']):x['phase_s'] for x in families if (x['case'],x['group'],x['arm'],x['norad']) in active}
    phase_changes=[]
    for group in ('ch1_4','ch5_8'):
        for arm in ('c0','fitted_c'):
            for case in q['cases']:
                common=sorted({k[-1] for k in phase if k[:3]==(case,group,arm)}&{k[-1] for k in phase if k[:3]==(case,'all_channels',arm)})
                for norad in common:
                    a,b=phase[(case,'all_channels',arm,norad)],phase[(case,group,arm,norad)]
                    phase_changes.append(dict(case=case,group=group,arm=arm,norad=norad,full_phase_s=a,half_phase_s=b,difference_s=b-a))
    phase_summary={g+'/'+a:summary([abs(x['difference_s']) for x in phase_changes if x['group']==g and x['arm']==a]) for g in ('ch1_4','ch5_8') for a in ('c0','fitted_c')}
    noise=graph_noise(q['cases'])
    noise_summary={g+f'/RX{rx}/{b}':summary([x['radio_scatter_hz'] for x in noise if x['group']==g and x['receiver']==rx and x['band']==b]) for g in ROOTS for rx in (1,2) for b in ('low','high')}
    write(OUT/'evidence_summary.json',dict(residual_groups=grouped,residual_strata=strata,phase_summary=phase_summary,phase_changes=phase_changes,graph_noise=noise,graph_noise_summary=noise_summary,
        replay_validation=dict(arms_replayed=len(differences),maximum_RMS_difference_hz=max(differences),all_active_point_counts_match=True),
        interpretation='conditional fitted residuals and graph scatter are uncertainty proxies, not calibrated measurement error or independently verified satellite identity'))
    with (OUT/'track_residual_metrics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(tracks[0]));w.writeheader();w.writerows(tracks)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(14,4.3),layout='constrained')
    colors={'all_channels':'#333333','ch1_4':'#1976d2','ch5_8':'#a348ad'}
    for group in ROOTS:
        rr=[x for x in q['records'] if x['group']==group and x['arm']=='fitted_c']
        axes[0].scatter([x['RMS_hz'] for x in rr],[x['curved_families'] for x in rr],label=group,c=colors[group],alpha=.7)
        ss=[x for x in tracks if x['group']==group and x['arm']=='fitted_c']
        xx=np.sort([x['lag1_acf'] for x in ss]);axes[1].step(xx,np.arange(1,len(xx)+1)/len(xx),where='post',c=colors[group],label=group)
    axes[0].set(xlabel='Curved fit RMS (Hz)',ylabel='Active curved model families',title='More families can matter beyond RMS')
    axes[1].set(xlabel='Within-track lag-one residual correlation',ylabel='Fraction of tracks',title='Residuals pass conservative legacy gates')
    for group in ('ch1_4','ch5_8'):
        rr=[x for x in q['comparisons'] if x['group']==group and x['arm']=='fitted_c']
        axes[2].scatter([100*(x['identity_disagreements']+x['full_only']+x['half_only'])/x['GLRT'] for x in rr],[x['endpoint_separation_km'] for x in rr],label=group,c=colors[group])
    axes[2].set(xlabel='Changed membership or model label (% GLRT)',ylabel='Half vs full endpoint distance (km)',title='Reassociation is mostly changing membership')
    for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(OUT/'evidence_diagnostics.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4.3),layout='constrained')
    keys=[(1,'low'),(1,'high'),(2,'low'),(2,'high')]
    for i,(rx,band) in enumerate(keys):
        ss=[x['radio_scatter_hz'] for x in noise if x['group']=='all_channels' and x['receiver']==rx and x['band']==band]
        ax.boxplot(ss,positions=[i],widths=.45,showfliers=False);ax.scatter(i+np.random.default_rng(i).uniform(-.12,.12,len(ss)),ss,s=16,alpha=.7)
    ax.set(xticks=range(4),xticklabels=[f'RX{rx} {b}' for rx,b in keys],ylabel='Graph polynomial radio scatter (Hz)',title='24 DS24 scans: measurement scatter differs by RX and band')
    ax.grid(axis='y',alpha=.2);fig.savefig(OUT/'radio_scatter_by_receiver.png',dpi=170);plt.close(fig)
    print(json.dumps(dict(residual_groups=grouped,phase_summary=phase_summary,graph_noise_summary=noise_summary),indent=2))

if __name__=='__main__':main()
