"""Read-only inventory of graph evidence left by a sealed cohort policy."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from debug_fast_graph_unassociated import read, write, helpers


def remaining_track(track, associated):
    mask=np.array([oid not in associated for oid in track['observation_ids']])
    if mask.sum()<2:return None
    times=np.asarray(track['times'])[mask];values=np.asarray(track['values'])[mask]
    x=times-times.mean();centered=values-values.mean()
    residual=centered-x*(x@centered)/max(x@x,1e-12)
    duration=float(np.ptp(times));curvature=float(np.sqrt(np.mean(residual**2)))
    return dict(component=track['key'],receiver=track['receiver'],channel=track['channel'],
        unassociated_points=int(mask.sum()),total_track_points=len(mask),start_s=float(times.min()),
        end_s=float(times.max()),span_s=duration,largest_gap_s=float(np.diff(np.sort(times)).max()),
        wholly_unassociated=bool(mask.all()),remaining_detrended_RMS_hz=curvature,
        active_curvature=bool(duration>=20 and curvature>=250),
        polynomial_RMS_hz=track['residual_rms_hz'],pieces=len(track['pieces']),
        quality_status=track['quality_status'],big=bool(mask.sum()>=20 and duration>=20))


def gallery(path, selected, cases, title):
    fig,axes=plt.subplots(3,2,figsize=(14,11),layout='constrained')
    for ax,row in zip(axes.flat,selected):
        data=cases[row['case']];observations=data['observations'];ids=data['associated']
        track=next(t for t in data['tracks'] if t['key']==row['component'])
        focus=set(track['observation_ids'])-ids
        lane=[o for o in observations if o['receiver']==row['receiver'] and o['channel']==row['channel']
              and row['start_s']-5<=o['time_s']<=row['end_s']+5]
        for label,color,size,chosen in [
            ('Associated GLRT','0.75',12,[o for o in lane if o['observation_id'] in ids]),
            ('Other unassociated GLRT','#e69f00',16,[o for o in lane if o['observation_id'] not in ids|focus]),
            ('Highlighted unassociated track','#cc1748',22,[o for o in lane if o['observation_id'] in focus])]:
            ax.scatter([o['time_s'] for o in chosen],[o['measured_cfo_hz']/1000 for o in chosen],c=color,s=size,label=label,alpha=.85)
        lookup={o['observation_id']:o for o in observations}
        for k,curve in enumerate(helpers.native_polynomial(track,lookup)):
            ax.plot(track['times'],curve/1000,color='#0072b2',lw=1,label='Existing graph polynomial' if k==0 else None)
        native=np.array([lookup[o]['measured_cfo_hz']/1000 for o in focus]);pad=max(3.,np.ptp(native)*.10)
        ax.set_ylim(native.min()-pad,native.max()+pad)
        short=row['component'].split(row['case']+'-')[1].split('-RF')[0]
        ax.set(title=f"{row['case']} {short}\n{row['unassociated_points']} points · {row['span_s']:.1f} s · polynomial RMS {row['polynomial_RMS_hz']:.0f} Hz",
               xlabel='Scan time (s)',ylabel='Native GLRT CFO (kHz)',xlim=(row['start_s']-5,row['end_s']+5))
        ax.grid(alpha=.2)
    for ax in list(axes.flat)[len(selected):]:ax.set_visible(False)
    fig.legend(*axes.flat[0].get_legend_handles_labels(),loc='outside lower center',ncol=2)
    fig.suptitle(title+'\nRed = unassociated target; gray = ASSOCIATED. No new satellite assignments.',fontsize=13)
    fig.savefig(path,dpi=150);plt.close(fig)


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    protocol=read(args.study/'protocol.json');source=Path(protocol['root']);cases={};rows=[];summary=[];hashes={}
    for case in protocol['selected']:
        result_path=args.study/case/'result.json'
        # Every covariance addition was rejected in this cohort; explicitly
        # honor any authoritative secondary result rather than assume that.
        for prefix in ('single','single-controlled'):
            p=args.study/prefix/case/'result.json'
            if p.exists():result_path=p
        result=read(result_path);arms={a:set(result['covariance'][a]['proposed_associated_ids']) for a in ('c0','fitted_c')}
        if arms['c0']!=arms['fitted_c']:raise ValueError('Arm memberships differ; publish separate inventories')
        associated=arms['fitted_c'];tracks=read(source/case/'tracks.json');observations=read(source/case/'observations.json')
        for p in (result_path,source/case/'tracks.json',source/case/'observations.json'):
            hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        cases[case]=dict(tracks=tracks,observations=observations,associated=associated)
        local=[dict(case=case,**r) for t in tracks if (r:=remaining_track(t,associated))]
        rows.extend(local);large=[r for r in local if r['big']]
        large_keys={r['component'] for r in large};large_ids={oid for t in tracks if t['key'] in large_keys for oid in t['observation_ids'] if oid not in associated}
        graph_ids={oid for t in tracks for oid in t['observation_ids']}
        summary.append(dict(case=case,total_GLRT=len(observations),associated=len(associated),
            unassociated=len(observations)-len(associated),large_tracks=len(large),large_track_unique_points=len(large_ids),
            large_curved=sum(r['active_curvature'] for r in large),
            outside_graph=sum(o['observation_id'] not in associated|graph_ids for o in observations)))
    rows.sort(key=lambda r:(-r['unassociated_points'],-r['span_s'],r['case'],r['component']))
    large=[r for r in rows if r['big']];write(out/'inventory.json',dict(summary=summary,tracks=rows,source_sha256=hashes,
        policy='Accepted support-backoff + qualified covariance policy; identical point memberships in both c arms',
        big_definition='at least 20 unassociated points spanning at least 20 seconds',
        curvature_definition='existing raw curvature criterion: detrended RMS >=250 Hz, span >=20 s',
        limitation='Graph inventory only; no exhaustive search for curves outside the graph, no satellite re-association'))
    for filename,records in [('large_tracks.csv',large),('per_scan.csv',summary)]:
        with (out/filename).open('x',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator='\n');writer.writeheader();writer.writerows(records)
    gallery(out/'largest_six.png',large[:6],cases,'Six largest remaining graph tracks across the 12-scan cohort')
    best=[next(r for r in large if r['case']==case) for case in protocol['selected']]
    gallery(out/'largest_per_scan_1.png',best[:6],cases,'Largest remaining track in each scan — first six scans')
    gallery(out/'largest_per_scan_2.png',best[6:],cases,'Largest remaining track in each scan — last six scans')
    table=['| Scan | Large tracks | Curved | Unique GLRT in large tracks | All unassociated GLRT | Outside graph |','|---|---:|---:|---:|---:|---:|']
    for r in summary:table.append(f"| {r['case']} | {r['large_tracks']} | {r['large_curved']} | {r['large_track_unique_points']} | {r['unassociated']} | {r['outside_graph']} |")
    leaders=['| Scan / track | Points | Time interval s | Span s | Polynomial RMS Hz | Largest point gap s |','|---|---:|---:|---:|---:|---:|']
    for r in large[:12]:
        leaders.append(f"| {r['component'].split('-RF')[0]} | {r['unassociated_points']} | {r['start_s']:.1f}–{r['end_s']:.1f} | {r['span_s']:.1f} | {r['polynomial_RMS_hz']:.1f} | {r['largest_gap_s']:.1f} |")
    total=sum(r['large_track_unique_points'] for r in summary);remaining=sum(r['unassociated'] for r in summary)
    text=f'''# Large unassociated tracks remaining in the 12-scan cohort

**Yes: all 12 scans retain large, obvious graph tracks.** After the accepted support-backoff policy, {len(large)} tracks retain at least 20 unassociated GLRT winners spanning 20 seconds. They contain **{total:,} unique points**, or **{100*total/remaining:.1f}% of the {remaining:,} remaining unassociated points**. {sum(r['active_curvature'] for r in large)} meet the existing active-curvature threshold; {sum(r['wholly_unassociated'] for r in large)} are wholly unassociated and one is partially associated. This is an inventory, not a new association or position result.

Both `c=0` and fitted-`c` policies have identical associated point sets, verified before inventory. Counts include postfit associations, so these points are truly outside the accepted satellite association set. Original GLRT winners are counted once; no interpolation is counted as evidence.

## Largest tracks

{chr(10).join(leaders)}

![Six largest unassociated tracks](largest_six.png)

The largest, **DS24-0018 RX2 CH3 T000**, has 89 points over 62.4 s, polynomial RMS 27.0 Hz, and no point gap longer than 1.8 s. Its RMS after removing a straight line is 2,718 Hz: it has substantial curvature, not merely a high-order fit to a nearly straight line. DS24-0089 RX1 CH3 T001 has 63 points over 42.9 s and polynomial RMS 92.2 Hz; this is particularly relevant because DS24-0089 is the worst position-error case in the cohort.

Polynomial RMS measures agreement with a graph curve, **not** agreement with a satellite orbit. The blue line is the existing graph polynomial rendered in the measured alias; it is not an orbital prediction. A good polynomial and substantial curvature make these strong investigation targets, but do not establish satellite identity or rule out a mistaken graph join.

## Every scan

{chr(10).join(table)}

![Largest per scan, first six](largest_per_scan_1.png)

![Largest per scan, last six](largest_per_scan_2.png)

Gray points are already associated. Red points are the highlighted unassociated graph track. Orange points are other unassociated GLRT winners nearby. Figures zoom to the highlighted track's frequency span; tables retain all point counts.

## Why the preceding test did not resolve these

The previous experiment was narrow: one unsupported-orbital-owner recovery proposal per scan, followed by same-family CH7/CH8 covariance proposals and a separately labeled single-high-channel amendment. It did not attempt to associate every large remaining graph curve. “No eligible pair” meant no proposal satisfied that particular CH7/CH8 rule, not no large tracks remained.

DS24-0101 RX1 CH3 T000 and DS24-0095 RX2 CH2 T000 already failed the support-backoff trial; they are still visible here because the failed proposals were not adopted. DS24-0085 and DS24-0097 CH8 curves also remain after their rejected covariance trials. Most other tracks were outside those bounded recovery tests. This inventory does not claim a new cause for their original satellite-association failure.

The next priorities are **DS24-0018 RX2 CH3 T000** for its exceptionally clean, dense curved evidence and **DS24-0089 RX1 CH3 T001** because it could bear on the cohort's worst position error. For each, compare the frozen incumbent-family prediction against a causal catalogue search, inspect the specific failing gates and any joins, and only then test recovery with matched `c` arms. Do not accept them solely to improve coverage.

## Scope and reproduction

- Frozen cohort and policy: [qualification report](../README.md).
- No inference refit, new TLE, new collection, GPS-based selection or production change.
- Duration is first-to-last remaining point, not proof of continuous coverage. `large_tracks.csv` includes the largest inter-point gap and whole/partial status.
- Active curvature follows the existing pipeline threshold: linear-detrended RMS ≥250 Hz over ≥20 s on the remaining graph-lifted values. It is a screening statistic, not an orbital information calculation.
- This inventory does not search for new tracks among GLRT winners outside the graph; those points are separately counted.
- `inventory.json` records all remaining multi-point graph tracks, per-scan accounting and hashes of every input. `large_tracks.csv` is the ranked list of all 68 large tracks.

```bash
PYTHONPATH=src:tools .venv/bin/python tools/inventory_cohort_unassociated.py --study /srv/bulk/leo/research/ch78-qualified-cohort-20261029 --output FRESH_OUTPUT
```
'''
    (out/'README.md').write_text(text);print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())
