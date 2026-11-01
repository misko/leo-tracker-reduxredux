"""Read-only, descriptive comparison of frozen fast-scan evaluations."""
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import spearmanr

OUT = Path(__file__).resolve().parent
REPORTS = OUT.parent
SOURCES = [REPORTS / x for x in (
    '2026_11_01_ds25_fast_causal_variants',
    '2026_11_01_ds26_ds27_causal_variants',
    '2026_11_01_ds28_revision2_evaluation')]
MANIFESTS = {
    'DS24': Path('/srv/bulk/leo/research/ds24-20261024-extension/manifest.json'),
    'DS26': Path('/srv/bulk/leo/research/ds26-20261030/dataset/manifest.json'),
    'DS27': Path('/srv/bulk/leo/research/ds27-algo04-20261031/dataset/manifest.json'),
    'DS28': REPORTS/'2026_11_01_ds28_revision2/dataset/manifest.json',
}
COLORS = dict(zip(MANIFESTS, ['#d55e00', '#0072b2', '#009e73', '#aa4499']))
SITE = (37.849061591561885, -122.48574968092912)
TZ = ZoneInfo('America/Los_Angeles')

def read(p):
    return json.loads(p.read_text())

def write_csv(name, rows):
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader(); w.writerows(rows)

members, denominators = {}, {}
for ds, path in MANIFESTS.items():
    manifest = read(path)
    denominators[ds] = sum(m['recording_id'].startswith('fast8-') for m in manifest['members'])
    for i, member in enumerate(manifest['members'], 1):
        members[f'{ds}-{i:04d}'] = member

all_rows, features = [], []
for root in SOURCES:
    for row in csv.DictReader((root/'position-errors.csv').open()):
        row['dataset'] = row['case'].split('-')[0]
        for key in ['error_m', 'associated_pct']:
            row[key] = float(row[key])
        for key in ['associated', 'total']:
            row[key] = int(row[key])
        all_rows.append(row)
    for path in sorted((root/'inputs').glob('*.json')):
        data = read(path)
        case = data['case']; ds = case.split('-')[0]
        row = next(r for r in all_rows if r['case']==case and r['method']=='ALGO05' and r['arm']=='fitted_c')
        native = Path(data['native_path'])
        obs = read(native/'observations.json')
        nominal = read(native/'nominal_elements.json')
        owners = data['baseline_owners']['fitted_c']
        counts = Counter(owners.values())
        total = sum(counts.values())
        ages = {int(n): v['provenance']['age_s']/3600 for n,v in nominal.items()}
        assert set(counts).issubset(ages), case
        assert len(obs) == row['total'], case
        assert len(owners) == row['associated'], case
        member = members[case]
        ts = data['scan_receipt']['origin_utc_ns']/1e9
        dt = datetime.fromtimestamp(ts, TZ)
        lat,lon = json.loads(row['endpoint_latlon'])
        f = dict(case=case, dataset=ds, recording_id=member['recording_id'],
                 timestamp=ts, local_time=dt.isoformat(), local_hour=dt.hour+dt.minute/60,
                 side=member['recording_id'].split('-')[-1],
                 error_m=row['error_m'], associated=row['associated'], total=row['total'],
                 associated_pct=row['associated_pct'], families=len(counts),
                 effective_families=total**2/sum(v*v for v in counts.values()),
                 largest_family_pct=100*max(counts.values())/total,
                 weighted_tle_age_h=sum(v*ages[n] for n,v in counts.items())/total,
                 median_family_age_h=float(np.median([ages[n] for n in counts])),
                 east_m=(lon-SITE[1])*111320*np.cos(np.deg2rad(SITE[0])),
                 north_m=(lat-SITE[0])*111320,
                 span_s=max(o['time_s'] for o in obs)-min(o['time_s'] for o in obs),
                 median_glrt_margin=float(np.median([o['fractional_margin'] for o in obs])),
                 fallback=bool(data.get('recovery_unavailable')))
        for ch in range(1,9):
            chobs = [o for o in obs if o['channel']==ch]
            f[f'ch{ch}_total'] = len(chobs)
            f[f'ch{ch}_associated'] = sum(o['observation_id'] in owners for o in chobs)
        features.append(f)

summary = []
for ds in MANIFESTS:
    for arm in ['c0','fitted_c']:
        for method in ['ALGO05','48h_15s','72h_15s','72h_30s','72h_30s_recency']:
            rows = [r for r in all_rows if (r['dataset'],r['arm'],r['method'])==(ds,arm,method)]
            e = np.array([r['error_m'] for r in rows])
            summary.append(dict(dataset=ds,arm=arm,method=method,n=len(e),roster=denominators[ds],
                mean_m=np.mean(e),median_m=np.median(e),p90_m=np.percentile(e,90),worst_m=max(e),
                within500=int(sum(e<=500)),within1000=int(sum(e<=1000)),
                associated_pct=100*sum(r['associated'] for r in rows)/sum(r['total'] for r in rows)))
write_csv('summary.csv', summary)
write_csv('scan-features.csv', features)
write_csv('position-errors.csv', all_rows)

diagnostics = {}
for ds in MANIFESTS:
    f = [r for r in features if r['dataset']==ds]
    diagnostics[ds] = {'n':len(f), 'mean_east_m':np.mean([r['east_m'] for r in f]),
        'mean_north_m':np.mean([r['north_m'] for r in f]),
        'start_local':min(r['local_time'] for r in f), 'end_local':max(r['local_time'] for r in f),
        'sides':dict(Counter(r['side'] for r in f)), 'fallbacks':[r['case'] for r in f if r['fallback']]}
    for key in ['total','families','effective_families','largest_family_pct','weighted_tle_age_h','span_s','median_glrt_margin']:
        diagnostics[ds][f'median_{key}'] = float(np.median([r[key] for r in f]))
        diagnostics[ds][f'rho_error_{key}'] = float(spearmanr([r[key] for r in f],[r['error_m'] for r in f]).statistic)
    for side in ['upper','lower']:
        ff = [r for r in f if r['side']==side]
        diagnostics[ds][side] = {'n':len(ff),'mean_m':np.mean([r['error_m'] for r in ff]), 'median_m':np.median([r['error_m'] for r in ff])}
    diagnostics[ds]['rho_error_associated_pct'] = float(spearmanr([r['associated_pct'] for r in f],[r['error_m'] for r in f]).statistic)
    diagnostics[ds]['channel_coverage_pct'] = [100*sum(r[f'ch{ch}_associated'] for r in f)/sum(r[f'ch{ch}_total'] for r in f) for ch in range(1,9)]
(OUT/'diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')

plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.2,'figure.dpi':150})
fig, axes = plt.subplots(1,2,figsize=(12,4.8),sharey=True)
for ax, arm in zip(axes,['fitted_c','c0']):
    for ds,c in COLORS.items():
        for method,style in [('ALGO05','-'),('72h_30s','--')]:
            e = sorted(r['error_m']/1000 for r in all_rows if (r['dataset'],r['arm'],r['method'])==(ds,arm,method))
            ax.step([0]+e+[8], [0]+list(np.arange(1,len(e)+1)/len(e)*100)+[100],where='post',
                    color=c,ls=style,lw=1.8,label=f'{ds} (n={len(e)})' if method=='ALGO05' else None)
    ax.axvline(.5,color='gray',ls=':',lw=1);ax.axvline(1,color='gray',ls=':',lw=1)
    ax.set(xlim=(0,8),ylim=(0,102),xlabel='Position error (km)',title='Fitted c' if arm=='fitted_c' else 'c = 0 control')
    ax.legend(loc='lower right')
axes[0].set_ylabel('Scans at or below this error (%)')
fig.suptitle('Same ALGO05 baseline across fast-scan cohorts\nSolid: ALGO05; dashed: fixed 72 h / ±30 s recovery policy (mostly overlaps)')
fig.tight_layout();fig.savefig(OUT/'comparable_ecdfs.png');plt.close(fig)

fig,axes=plt.subplots(2,2,figsize=(12,9))
for ds,c in COLORS.items():
    ff=[f for f in features if f['dataset']==ds]
    e=sorted(f['error_m']/1000 for f in ff)
    axes[0,0].step([0]+e+[8],[0]+list(np.arange(1,len(e)+1)/denominators[ds]*100)+[len(e)/denominators[ds]*100],where='post',color=c,label=f'{ds}: {len(e)}/{denominators[ds]} available')
    axes[0,1].scatter([f['east_m']/1000 for f in ff],[f['north_m']/1000 for f in ff],s=20,alpha=.7,color=c,label=ds)
    axes[0,1].scatter(np.mean([f['east_m'] for f in ff])/1000,np.mean([f['north_m'] for f in ff])/1000,marker='X',s=130,color=c,edgecolor='black')
    axes[1,0].scatter([f['associated_pct'] for f in ff],[f['error_m']/1000 for f in ff],s=22,color=c,alpha=.65,label=ds)
    axes[1,1].plot(range(1,9),diagnostics[ds]['channel_coverage_pct'],marker='o',color=c,label=ds)
axes[0,0].set(xlim=(0,8),ylim=(0,102),xlabel='Position error (km)',ylabel='% of all fast cohort members',title='Availability-aware success curve');axes[0,0].legend(fontsize=8)
axes[0,1].axhline(0,c='gray',lw=.6);axes[0,1].axvline(0,c='gray',lw=.6)
axes[0,1].scatter(0,0,marker='*',s=160,c='black',label='Evaluation site')
axes[0,1].set(xlabel='East error (km)',ylabel='North error (km)',title='Position errors; X = cohort mean vector',aspect='equal');axes[0,1].legend(fontsize=8)
axes[1,0].set(xlabel='GLRT associated (%)',ylabel='Position error (km)',title='More associations do not guarantee lower error')
axes[1,1].set(xlabel='Channel',ylabel='GLRT associated (%)',title='Point-weighted association coverage',xticks=range(1,9));axes[1,1].legend()
fig.suptitle('ALGO05 fitted-c diagnostics; unavailable scans remain unresolved')
fig.tight_layout();fig.savefig(OUT/'cohort_diagnostics.png');plt.close(fig)

fig,axes=plt.subplots(1,3,figsize=(14,4.5))
for ds,c in COLORS.items():
    ff=[f for f in features if f['dataset']==ds]
    axes[0].scatter([datetime.fromtimestamp(f['timestamp'],TZ) for f in ff],[f['error_m']/1000 for f in ff],s=20,color=c,label=ds)
    axes[1].scatter([f['weighted_tle_age_h'] for f in ff],[f['error_m']/1000 for f in ff],s=20,color=c,alpha=.6)
    axes[2].scatter([f['effective_families'] for f in ff],[f['error_m']/1000 for f in ff],s=20,color=c,alpha=.6)
import matplotlib.dates as mdates
axes[0].xaxis.set_major_formatter(mdates.DateFormatter('%b %d',tz=TZ));axes[0].tick_params(axis='x',rotation=35)
axes[0].set(title='Capture date (Pacific)',ylabel='Position error (km)');axes[0].legend(fontsize=8)
axes[1].set(title='Associated-point-weighted TLE age',xlabel='Hours')
axes[2].set(title='Effective satellite family count',xlabel='1 / sum(point-share²)')
fig.tight_layout();fig.savefig(OUT/'explanatory_checks.png');plt.close(fig)

fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharey=True)
for ax,side in zip(axes,['upper','lower']):
    for ds,c in COLORS.items():
        e=sorted(f['error_m']/1000 for f in features if f['dataset']==ds and f['side']==side)
        ax.step([0]+e+[8],[0]+list(np.arange(1,len(e)+1)/len(e)*100)+[100],where='post',color=c,label=f'{ds} (n={len(e)})')
    ax.set(xlim=(0,8),ylim=(0,102),xlabel='Position error (km)',title=f'{side.title()} channel-edge recordings')
    ax.legend(loc='lower right');ax.axvline(.5,color='gray',ls=':');ax.axvline(1,color='gray',ls=':')
axes[0].set_ylabel('Scans at or below this error (%)')
fig.suptitle('ALGO05 fitted c: upper/lower means frequency edge, not CH1–4/CH5–8')
fig.tight_layout();fig.savefig(OUT/'edge_stratified_ecdfs.png');plt.close(fig)

assert len({(r['case'],r['arm'],r['method']) for r in all_rows}) == len(all_rows)
assert len(features) == sum(s['n'] for s in summary if s['arm']=='fitted_c' and s['method']=='ALGO05')
paired = []
for ds in MANIFESTS:
    lookup={(r['case'],r['arm'],r['method']):r for r in all_rows if r['dataset']==ds}
    for arm in ['c0','fitted_c']:
        for method in ['48h_15s','72h_15s','72h_30s','72h_30s_recency']:
            rr=[r for r in all_rows if (r['dataset'],r['arm'],r['method'])==(ds,arm,method)]
            deltas=[r['error_m']-lookup[(r['case'],arm,'ALGO05')]['error_m'] for r in rr]
            paired.append(dict(dataset=ds,arm=arm,method=method,mean_delta_m=np.mean(deltas),
                max_abs_delta_m=max(abs(x) for x in deltas),changed_scans=sum(abs(x)>1 for x in deltas)))
write_csv('paired-variant-effects.csv',paired)
print(json.dumps({'summary':[s for s in summary if s['arm']=='fitted_c' and s['method']=='ALGO05'], 'diagnostics':diagnostics},indent=2))
