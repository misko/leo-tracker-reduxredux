"""Summarize a frozen metadata-only sample-rate audit with scan-level uncertainty."""
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent
RATES = (2500000, 5000000, 10000000)
TZ = ZoneInfo('America/Los_Angeles')


def quant(values):
    a = np.asarray(values, dtype=float)
    return dict(n=len(a), p25=float(np.quantile(a, .25)), median=float(np.median(a)),
                p75=float(np.quantile(a, .75)), p90=float(np.quantile(a, .9))) if len(a) else dict(n=0)


def main():
    evidence = json.loads(Path('/var/tmp/leo-weekly-rate-products.json').read_text())
    inventory = json.loads(Path('/var/tmp/leo-weekly-rate-inventory.json').read_text())
    metadata = {r['session_id']: r for r in inventory['rows']}
    products = [p for p in evidence['products'] if p['document']['schema_version'] == 14
                and p['document']['sample_rate_hz'] in RATES]
    # One common algorithm/configuration; no mixing old/new products or duplicate scans.
    assert len({p['document']['configuration_digest'] for p in products}) == 1
    assert len({p['document']['session_id'] for p in products}) == len(products)
    rows, scans = [], []
    for p in products:
        d = p['document']
        m = metadata[d['session_id']]
        assert m['sample_rate_hz'] == d['sample_rate_hz']
        epoch = m['captured_ns'] / 1e9
        day = datetime.fromtimestamp(epoch, TZ).strftime('%Y-%m-%d')
        base = dict(session_id=d['session_id'], rate=d['sample_rate_hz'], epoch=epoch, day=day)
        rr = []
        for t in d['track_reviews']:
            c = next(c for c in t['candidates'] if c['rank'] == 1)
            r = dict(**base, tracklet_id=t['tracklet_id'], channel=t['channel'], edge=t['edge'],
                     satellite_candidate=c['catalog_number'], span_s=t['end_s']-t['start_s'],
                     track_epoch=epoch+t['start_s'], observations=t['observation_count'],
                     evaluation_observations=t['randomized_evaluation_observation_count'],
                     fit_rms_hz=c['fit_rms_hz'], evaluation_rms_hz=c['randomized_evaluation_rms_hz'],
                     tau_s=c['selected_tau_s'])
            rows.append(r)
            rr.append(r)
        scans.append(dict(**base, reviews=len(rr), eligible=d.get('review_eligible_count'),
                          deferred=d.get('deferred_review_count'),
                          median_rms_hz=float(np.median([r['evaluation_rms_hz'] for r in rr])) if rr else None,
                          tracklets=len(d['tracklets']),
                          stable_candidates=sum(not c['abstention_recommended'] for c in d['tle_candidates']),
                          attempted_groups=d['attempted_group_count']))
    for name, data in [('tracks.csv', rows), ('scans.csv', scans), ('recordings.csv', inventory['rows'])]:
        with (OUT/name).open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator='\n')
            writer.writeheader(); writer.writerows(data)
    summary = dict(start=evidence['start'], end=evidence['end'], configuration_digest=products[0]['document']['configuration_digest'],
                   product_count=len(products), inventory_errors=inventory['errors'], product_errors=evidence['errors'], rates={})
    for rate in RATES:
        rr = [r for r in rows if r['rate'] == rate]
        ss = [s for s in scans if s['rate'] == rate]
        summary['rates'][rate] = dict(recordings=sum(r['sample_rate_hz']==rate for r in inventory['rows']),
             scans=len(ss), reviews=len(rr), satellites=len({r['satellite_candidate'] for r in rr}),
             evaluation_rms_hz=quant([r['evaluation_rms_hz'] for r in rr]),
             fit_rms_hz=quant([r['fit_rms_hz'] for r in rr]),
             scan_median_rms_hz=quant([s['median_rms_hz'] for s in ss if s['median_rms_hz'] is not None]),
             span_s=quant([r['span_s'] for r in rr]), observations=quant([r['observations'] for r in rr]),
             fraction_under_100_hz=float(np.mean([r['evaluation_rms_hz']<100 for r in rr])),
             fraction_under_200_hz=float(np.mean([r['evaluation_rms_hz']<200 for r in rr])),
             review_eligible=sum(s['eligible'] for s in ss), deferred=sum(s['deferred'] for s in ss),
             stable_candidates=sum(s['stable_candidates'] for s in ss), attempted_groups=sum(s['attempted_groups'] for s in ss),
             daily={day:dict(scans=sum(s['day']==day for s in ss), **quant([r['evaluation_rms_hz'] for r in rr if r['day']==day])) for day in sorted({s['day'] for s in ss})},
             by_edge={e:quant([r['evaluation_rms_hz'] for r in rr if r['edge']==e]) for e in ['lower','upper']},
             span_30_90=quant([r['evaluation_rms_hz'] for r in rr if 30<=r['span_s']<90]))
    # Common capture-time window shared by all three rate cohorts.
    common_start=max(min(s['epoch'] for s in scans if s['rate']==rate) for rate in RATES)
    common_end=min(max(s['epoch'] for s in scans if s['rate']==rate) for rate in RATES)
    rng=np.random.default_rng(20261003)
    summary['common_window'] = dict(start=common_start, end=common_end, rates={})
    boot={}
    for rate in RATES:
        ss=[s for s in scans if s['rate']==rate and common_start<=s['epoch']<=common_end and s['median_rms_hz'] is not None]
        a=np.array([s['median_rms_hz'] for s in ss])
        b=np.median(rng.choice(a, (4000,len(a)), replace=True), axis=1)
        boot[rate]=b
        summary['common_window']['rates'][rate]=dict(**quant(a), ci95=np.quantile(b,[.025,.975]).tolist())
    summary['common_window']['ratios_10m_to_other']={rate:dict(median=float(np.median(boot[10000000]/boot[rate])),ci95=np.quantile(boot[10000000]/boot[rate],[.025,.975]).tolist()) for rate in RATES[:-1]}
    # Same candidate/channel/edge, within 15 min, span and support within a factor of two.
    # Greedy nearest-time pairs without reusing tracks; descriptive, not independent trials.
    matched={}
    for other in RATES[:-1]:
        groups=defaultdict(list)
        for r in rows:
            if r['rate']==other:
                groups[(r['satellite_candidate'],r['channel'],r['edge'])].append(r)
        possible=[]
        for a in rows:
            if a['rate']!=10000000: continue
            for b in groups[(a['satellite_candidate'],a['channel'],a['edge'])]:
                gap=abs(a['track_epoch']-b['track_epoch'])
                if gap<=900 and .5<=a['span_s']/b['span_s']<=2 and .5<=a['observations']/b['observations']<=2:
                    possible.append((gap,a,b))
        used=set(); pairs=[]
        for gap,a,b in sorted(possible,key=lambda x:x[0]):
            ka=(a['session_id'],a['tracklet_id']);kb=(b['session_id'],b['tracklet_id'])
            if ka in used or kb in used: continue
            used.update((ka,kb))
            pairs.append(dict(rate_other=other, session_10=a['session_id'], session_other=b['session_id'],
                              candidate=a['satellite_candidate'], time_gap_s=gap,
                              rms_10=a['evaluation_rms_hz'], rms_other=b['evaluation_rms_hz'],
                              ratio=a['evaluation_rms_hz']/b['evaluation_rms_hz']))
        matched[other]=dict(pairs=len(pairs), candidates=len({p['candidate'] for p in pairs}),
                            scans_10=len({p['session_10'] for p in pairs}),scans_other=len({p['session_other'] for p in pairs}),
                            ratio=quant([p['ratio'] for p in pairs]),
                            rms_10=quant([p['rms_10'] for p in pairs]),rms_other=quant([p['rms_other'] for p in pairs]),
                            fraction_10_better=float(np.mean([p['ratio']<1 for p in pairs])) if pairs else None,
                            gap_s=quant([p['time_gap_s'] for p in pairs]))
        if pairs:
            with (OUT/f'matched-{other}.csv').open('w') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(pairs[0]),lineterminator='\n');writer.writeheader();writer.writerows(pairs)
    summary['matched']=matched
    # Compare like support, date, channel, and edge without claiming the same satellite.
    cells=defaultdict(lambda:defaultdict(list))
    for r in rows:
        key=(r['day'],r['channel'],r['edge'],int(r['span_s']//10),int(r['observations']//20))
        cells[key][r['rate']].append(r['evaluation_rms_hz'])
    summary['stratified']={}
    for other in RATES[:-1]:
        eligible=[v for v in cells.values() if len(v[other])>=5 and len(v[10000000])>=5]
        ratios=[float(np.median(v[10000000])/np.median(v[other])) for v in eligible]
        summary['stratified'][other]=dict(cells=len(eligible),ratio_10_to_other=quant(ratios),
           tracks_10=sum(len(v[10000000]) for v in eligible),tracks_other=sum(len(v[other]) for v in eligible))
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    (OUT/'provenance.json').write_text(json.dumps([dict(path=p['path'],sha256=p['sha256']) for p in products],indent=2)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    colors=['#2171b5','#e08214','#23934d']
    for rate,color in zip(RATES,colors):
        a=np.sort([r['evaluation_rms_hz'] for r in rows if r['rate']==rate])
        axes[0].plot(a,np.arange(1,len(a)+1)/len(a),label=f'{rate/1e6:g} MS/s',color=color)
        daily=summary['rates'][rate]['daily']
        axes[1].plot(list(daily),[v['median'] for v in daily.values()],'.-',label=f'{rate/1e6:g} MS/s',color=color)
    axes[0].set(xscale='log',xlim=(10,1500),xlabel='Held-out Doppler RMS (Hz; lower is better)',ylabel='Fraction of reviewed tracks')
    axes[1].set(xlabel='Capture date (Pacific)',ylabel='Median held-out Doppler RMS (Hz)')
    axes[1].tick_params(axis='x',rotation=35)
    for ax in axes: ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Past week: same v14 tracking configuration; observational comparison')
    fig.savefig(OUT/'rms-comparison.png',dpi=170)
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
