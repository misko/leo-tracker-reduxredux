"""Per-channel accounting of saved DS24 fits, not single-channel localization."""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent
HALF = Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
ROOTS = {'full': Path('/srv/bulk/leo/research/ds25-20261024'),
         'low_only': HALF/'ch1_4', 'high_only': HALF/'ch5_8'}
EVIDENCE = Path('/srv/bulk/leo/research/ds24-bottlenecks-20261024/evidence')
SOURCE = {}


def read(path):
    content = path.read_bytes(); SOURCE[str(path)] = hashlib.sha256(content).hexdigest()
    return json.loads(content)


def encode(value):
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, np.ndarray): return value.tolist()
    raise TypeError(type(value).__name__)


def write(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, default=encode, allow_nan=False)+'\n')


def csvout(name, rows):
    with (OUT/name).open('w') as stream:
        writer=csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def curvature(track):
    t=np.asarray(track['times']); y=np.asarray(track['values'])
    x=t-t.mean(); v=y-y.mean(); r=v-x*(v@x)/max(x@x,1e-12)
    return np.ptp(t)>=20 and np.sqrt(np.mean(r*r))>=250


def main():
    cases=read(HALF/'summary.json')['baseline']['fitted_c']['common_cases']
    assert len(cases)==24
    pointmeta={}; gateinfo={}; per_scan=[]; trackrows=[]; windows={}; rf_by_channel=defaultdict(set)
    for case in cases:
        tracking=read(ROOTS['full']/case/'tracking.json')['source']
        assert tracking['sample_rate_hz']==10_000_000
        receivers=sorted({p['receiver_id'] for p in tracking['probes']})
        counts=Counter((receivers.index(p['receiver_id'])+1,p['channel']) for p in tracking['probes'])
        for rx in (1,2):
            for ch in range(1,9): windows[case,rx,ch]=counts[rx,ch]
        for group,root in ROOTS.items():
            observations=read(root/case/'observations.json'); lookup={o['observation_id']:o for o in observations}
            assert len(lookup)==len(observations)
            tracks=read(root/case/'tracks.json'); tracks_by_key={t['key']:t for t in tracks}
            graph=set(); raw_curved=set()
            for t in tracks:
                assert not graph.intersection(t['observation_ids'])
                graph.update(t['observation_ids'])
                if curvature(t): raw_curved.update(t['observation_ids'])
            assert graph <= lookup.keys()
            for o in observations:
                key=(case,o['observation_id'])
                if key in pointmeta: assert pointmeta[key]==o
                else: pointmeta[key]=o
                rf_by_channel[o['channel']].add(o['actual_rf_hz'])
            saved=read(root/'family_cavity/position'/f'{case}.json')
            membership=None
            for arm,s in saved['policy_arms'].items():
                curved=set(); predictive=set(); families=defaultdict(set)
                for g in s['gates']['tracks']:
                    if not g['compatible']: continue
                    ids=set(g['observation_ids']); assert len(ids)==g['points']
                    assert not curved.intersection(ids); curved.update(ids)
                    t=tracks_by_key[g['component']]
                    for oid in ids:
                        gateinfo[group,arm,case,oid]=g
                        families[t['receiver'],t['channel']].add(g['norad'])
                    active_times=[time for oid,time in zip(t['observation_ids'],t['times'],strict=True) if oid in ids]
                    trackrows.append(dict(case=case,group=group,arm=arm,receiver=t['receiver'],channel=t['channel'],
                        rf_hz=t['rf_hz'],norad=g['norad'],component=g['component'],points=len(ids),
                        start_s=min(active_times),end_s=max(active_times),
                        profile_bias_hz=g['profile_bias_hz'],conditional_mean_hz=g['conditional_residual_gate']['mean_hz'],
                        conditional_RMS_hz=g['conditional_residual_gate']['rms_hz']))
                for g in s.get('linear_gates',[]):
                    if not g['compatible']: continue
                    ids=set(g['observation_ids']); assert len(ids)==g['points']
                    assert not predictive.intersection(ids); predictive.update(ids)
                assert not curved.intersection(predictive)
                assert curved|predictive <= lookup.keys()
                assert len(curved)==s['active_points']
                assert len(predictive)==s.get('predictive_points',s.get('additional_predictive_points',0))
                if membership is None: membership=(curved.copy(),predictive.copy())
                else: assert membership==(curved,predictive)
                for rx in (1,2):
                    for ch in sorted({o['channel'] for o in observations}):
                        local=[o for o in observations if o['receiver']==rx and o['channel']==ch]
                        ids={o['observation_id'] for o in local}; n=len(ids)
                        frequencies=sorted({o['actual_rf_hz'] for o in local})
                        assert len(frequencies)==1
                        per_scan.append(dict(case=case,group=group,arm=arm,receiver=rx,channel=ch,rf_hz=frequencies[0],
                            processed_windows=windows[case,rx,ch],GLRT=n,graph_points=len(ids&graph),
                            raw_curvature_points=len(ids&raw_curved),curved_points=len(ids&curved),
                            predictive_points=len(ids&predictive),associated=len(ids&(curved|predictive)),
                            association_percent=100*len(ids&(curved|predictive))/n if n else None,
                            retained_curved_families=len(families[rx,ch]),
                            median_winner_margin=float(np.median([o['fractional_margin'] for o in local])) if n else None))
    residuals=defaultdict(list)
    path=EVIDENCE/'curved_point_residuals.csv'; SOURCE[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    mapping={'all_channels':'full','ch1_4':'low_only','ch5_8':'high_only'}
    with path.open() as stream:
        for r in csv.DictReader(stream):
            group=mapping[r['group']]; o=pointmeta[r['case'],r['observation_id']]
            assert int(r['channel'])==o['channel'] and int(r['receiver'])==o['receiver']
            assert (group,r['arm'],r['case'],r['observation_id']) in gateinfo
            residuals[r['case'],group,r['arm'],o['receiver'],o['channel']].append(
                (float(r['residual_hz']),float(r['sigma_hz']),o['actual_rf_hz']))
    for r in per_scan:
        values=np.asarray(residuals[r['case'],r['group'],r['arm'],r['receiver'],r['channel']])
        assert len(values)==r['curved_points']
        for name in ('RMS_hz','normalized_RMS_11p5GHz_hz','mean_residual_hz'):r[name]=None
        if len(values):
            r.update(RMS_hz=float(np.sqrt(np.mean(values[:,0]**2))),
                     normalized_RMS_11p5GHz_hz=float(np.sqrt(np.mean((values[:,0]*11.5e9/values[:,2])**2))),
                     mean_residual_hz=float(np.mean(values[:,0])))
    summary=[]
    for group in ROOTS:
        for arm in ('c0','fitted_c'):
            for ch in range(1,9):
                for rx in (0,1,2):
                    rows=[r for r in per_scan if r['group']==group and r['arm']==arm and r['channel']==ch and (rx==0 or r['receiver']==rx)]
                    if not rows:continue
                    total={k:sum(r[k] for r in rows) for k in ('processed_windows','GLRT','graph_points','raw_curvature_points','curved_points','predictive_points','associated')}
                    biases=[t['profile_bias_hz'] for t in trackrows if t['group']==group and t['arm']==arm and t['channel']==ch and (rx==0 or t['receiver']==rx)]
                    values=np.concatenate([np.asarray(residuals[r['case'],group,arm,r['receiver'],ch]) for r in rows if r['curved_points']])
                    scan_rates=[]
                    for case in cases:
                        rr=[r for r in rows if r['case']==case]
                        scan_rates.append(100*sum(r['associated'] for r in rr)/sum(r['GLRT'] for r in rr))
                    summary.append(dict(group=group,arm=arm,channel=ch,receiver=rx,**total,
                        association_percent=100*total['associated']/total['GLRT'],graph_percent=100*total['graph_points']/total['GLRT'],
                        winner_percent_of_windows=100*total['GLRT']/total['processed_windows'],
                        association_scan_median_percent=float(np.median(scan_rates)),association_scan_q25_percent=float(np.quantile(scan_rates,.25)),
                        association_scan_q75_percent=float(np.quantile(scan_rates,.75)),
                        pooled_RMS_hz=float(np.sqrt(np.mean(values[:,0]**2))),
                        pooled_normalized_RMS_11p5GHz_hz=float(np.sqrt(np.mean((values[:,0]*11.5e9/values[:,2])**2))),
                        mean_conditional_residual_hz=float(np.mean(values[:,0])),
                        profile_bias_median_hz=float(np.median(biases)),profile_bias_q25_hz=float(np.quantile(biases,.25)),
                        profile_bias_q75_hz=float(np.quantile(biases,.75))))
    for arm in ('c0','fitted_c'):
        rows=[r for r in summary if r['group']=='full' and r['arm']==arm and r['receiver']==0]
        assert sum(r['GLRT'] for r in rows)==108600 and sum(r['associated'] for r in rows)==78067
        assert sum(r['curved_points'] for r in rows)==66110
        for group,numerator,denominator in [('low_only',42621,60059),('high_only',33339,48541)]:
            rows=[r for r in summary if r['group']==group and r['arm']==arm and r['receiver']==0]
            assert sum(r['GLRT'] for r in rows)==denominator and sum(r['associated'] for r in rows)==numerator
    rf=[]
    for ch,f in sorted(rf_by_channel.items()):
        values=np.asarray(sorted(f)); scales=values/11.5e9
        rf.append(dict(channel=ch,actual_RF_GHz=values/1e9,wavelength_mm=299792458/values*1000,
                       frequency_scale=scales,doppler_Hz_per_m_s=values/299792458,
                       maximum_numerical_reference_scaling_error_hz=float(max(abs((-11.5e9*np.array([-7.,0.,7.])[:,None]/299792.458)*scales[None,:]-(-values[None,:]*np.array([-7.,0.,7.])[:,None]/299792.458)).ravel()))))
    edge_rows=[]
    for arm in ('c0','fitted_c'):
        for ch in range(1,9):
            for edge,frequency in zip(('lower','upper'),sorted(rf_by_channel[ch]),strict=True):
                rows=[r for r in per_scan if r['group']=='full' and r['arm']==arm and r['channel']==ch and r['rf_hz']==frequency]
                values=np.concatenate([np.asarray(residuals[r['case'],'full',arm,r['receiver'],ch]) for r in rows if r['curved_points']])
                edge_rows.append(dict(arm=arm,channel=ch,edge=edge,rf_hz=frequency,scans=len({r['case'] for r in rows}),
                    GLRT=sum(r['GLRT'] for r in rows),associated=sum(r['associated'] for r in rows),
                    association_percent=100*sum(r['associated'] for r in rows)/sum(r['GLRT'] for r in rows),
                    winner_percent_of_windows=100*sum(r['GLRT'] for r in rows)/sum(r['processed_windows'] for r in rows),
                    pooled_normalized_RMS_11p5GHz_hz=float(np.sqrt(np.mean((values[:,0]*11.5e9/values[:,2])**2)))))
    csvout('per_scan_channel.csv',per_scan);csvout('channel_summary.csv',summary);csvout('track_biases.csv',trackrows);csvout('edge_summary.csv',edge_rows)
    write('summary.json',dict(cases=cases,scope='Per-channel slices of saved full and half-band fits; no new single-channel localization',
          association_denominator='unique original gate-passing GLRT winners in that channel',
          association_numerator='curved plus predictive likelihood IDs, excluding postfit-only matches',
          rows=summary,RF=rf,edge_rows=edge_rows,c0_and_fitted_c_preserved=True,no_new_GPS_or_TLE_inference=True))
    write('provenance.json',dict(source_sha256=SOURCE))
    plot(summary,per_scan,cases)
    print(json.dumps([r for r in summary if r['group']=='full' and r['arm']=='fitted_c' and r['receiver']==0],indent=2))


def plot(summary,per_scan,cases):
    def pick(group,rx=0,arm='fitted_c'):
        return sorted([r for r in summary if r['group']==group and r['arm']==arm and r['receiver']==rx],key=lambda r:r['channel'])
    full=pick('full'); halves=pick('low_only')+pick('high_only'); ch=np.arange(1,9)
    fig,ax=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    ax[0,0].bar(ch-.19,[r['association_percent'] for r in full],width=.38,label='Full-band fit',color='#477ca8')
    ax[0,0].bar(ch+.19,[r['association_percent'] for r in halves],width=.38,label='Respective half-band fit',color='#de8731')
    ax[0,0].set(ylabel='Associated / winning GLRT (%)',ylim=(0,100),title='Association by channel; fitted c');ax[0,0].legend(fontsize=9)
    ax[0,1].bar(ch,[r['GLRT'] for r in full],color='#cecece',label='All winning GLRT')
    ax[0,1].bar(ch,[r['associated'] for r in full],color='#477ca8',label='Used in full likelihood')
    ax[0,1].set(ylabel='Points across 24 scans',title='Unequal amount of detected evidence');ax[0,1].legend(fontsize=9)
    for rx,color in ((1,'#b64d5d'),(2,'#339175')):
        r=pick('full',rx)
        ax[1,0].plot(ch,[v['pooled_normalized_RMS_11p5GHz_hz'] for v in r],'o-',color=color,label=f'RX{rx}')
        ax[1,1].plot(ch,[v['winner_percent_of_windows'] for v in r],'o-',color=color,label=f'RX{rx}')
    ax[1,0].set(ylabel='Conditional residual RMS at 11.5 GHz (Hz)',title='Carrier-normalized residuals of retained curved points');ax[1,0].legend()
    ax[1,1].set(ylabel='Winning GLRT / processed windows (%)',title='Detection yield, before track/satellite selection');ax[1,1].legend()
    for a in ax.flat:a.set(xticks=ch,xlabel='Channel');a.grid(axis='y',alpha=.2);a.set_axisbelow(True)
    fig.suptitle('DS24: each channel within existing fits — not channel-only localization',fontsize=13)
    for ext in ('png','pdf'):fig.savefig(OUT/f'channel_comparison.{ext}',dpi=170)
    plt.close(fig)
    matrix=np.array([[100*sum(r['associated'] for r in per_scan if r['case']==case and r['group']=='full' and r['arm']=='fitted_c' and r['channel']==ch)/sum(r['GLRT'] for r in per_scan if r['case']==case and r['group']=='full' and r['arm']=='fitted_c' and r['channel']==ch) for ch in range(1,9)] for case in cases])
    fig,ax=plt.subplots(figsize=(9,9),constrained_layout=True)
    image=ax.imshow(matrix,vmin=0,vmax=100,cmap='viridis',aspect='auto')
    for i in range(len(cases)):
        for j in range(8):ax.text(j,i,f'{matrix[i,j]:.0f}',ha='center',va='center',fontsize=8,color='white' if matrix[i,j]<55 else 'black')
    ax.set(xticks=range(8),xticklabels=[f'CH{k}' for k in range(1,9)],yticks=range(len(cases)),yticklabels=[c.replace('DS24-','') for c in cases],title='Full-fit GLRT association by scan and channel (%)',ylabel='DS24 scan')
    fig.colorbar(image,ax=ax,label='Curved + predictive / original channel GLRT (%)')
    for ext in ('png','pdf'):fig.savefig(OUT/f'association_heatmap.{ext}',dpi=170)
    plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    for rx,color in ((1,'#b64d5d'),(2,'#339175')):
        r=pick('full',rx);offset=-.08 if rx==1 else .08
        med=np.array([v['profile_bias_median_hz'] for v in r])
        errors=np.array([[v['profile_bias_median_hz']-v['profile_bias_q25_hz'] for v in r],
                         [v['profile_bias_q75_hz']-v['profile_bias_median_hz'] for v in r]])
        ax[0].errorbar(ch+offset,med,yerr=errors,fmt='o',capsize=4,color=color,label=f'RX{rx}: median and IQR')
        ax[1].plot(ch,[v['mean_conditional_residual_hz'] for v in r],'o-',color=color,label=f'RX{rx}')
    ax[0].set(title='Constants profiled after shared receiver/orbit terms',ylabel='Per-track profile bias (Hz)')
    ax[1].set(title='After fitted fragment constants',ylabel='Mean conditional residual (Hz)')
    for a in ax:a.set(xticks=ch,xlabel='Channel');a.axhline(0,color='gray',lw=1);a.grid(alpha=.2);a.legend(fontsize=9)
    fig.suptitle('Saved full-fit offsets are descriptive; near-zero final residuals do not exclude hardware bias',fontsize=12)
    for ext in ('png','pdf'):fig.savefig(OUT/f'channel_offsets.{ext}',dpi=170)
    plt.close(fig)


if __name__=='__main__':main()
