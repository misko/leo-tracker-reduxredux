"""Publish the canonical inventory, diagnostic ledger and indexed GLRT gallery."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from debug_fast_graph_unassociated import read,write

ARMS=('c0','fitted_c')


def classify(record):
    for model,search,label in [('constant','current','Current-position candidate'),
            ('small_rate','current','Small-rate candidate'),('constant','regional','Regional candidate'),
            ('small_rate','regional','Regional + rate candidate'),('shape_only','current','Offset-prior conflict'),
            ('shape_only','regional','Regional offset-prior conflict')]:
        field='shape_pass' if model=='shape_only' else 'physical_screen_pass'
        sets=[{r['norad'] for r in record['trials'][a][model] if r['search']==search and r[field]} for a in ARMS]
        common=sets[0]&sets[1]
        if common:return label,sorted(common)
    best=[min(r['rms_hz'] for m in record['trials'][a].values() for r in m) for a in ARMS]
    return ('Structured/bounds conflict' if max(best)<=450 else 'Large orbit mismatch'),[]


def csvfile(path,rows):
    if not rows:return
    with path.open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)


def pack_evidence(path,inventories,diagnostics):
    # Store every residual once without repeating immutable time/observation
    # vectors in every candidate trial or duplicating full baseline histories.
    policies=('endpoint_east_north_km','endpoint_latlon',
              'phase_reference','negative_twice_elbo','curved_negative_twice_elbo','RMS_hz')
    compact={}
    for k,v in inventories.items():
        compact[k]=dict(job=v['job'],summary=v['summary'],
                        tracks=[r for r in v['tracks'] if r['current_large'] or r['earlier_large']])
        for name in ('policy','prior_policy'):
            compact[k][name]={}
            for arm,r in v[name].items():
                ids=sorted(r['proposed_associated_ids'])
                compact[k][name][arm]=dict(**{key:r[key] for key in policies if key in r},
                    associated_count=len(ids),associated_ids_sha256=hashlib.sha256('\n'.join(ids).encode()).hexdigest())
    result=[]
    for diag in diagnostics:
        record={k:v for k,v in diag.items() if k!='tracks'};record['tracks']=[]
        for track in diag['tracks']:
            t={k:v for k,v in track.items() if k!='trials'};t['trials']={};t['corrected_observation_hz']={}
            for arm,models in track['trials'].items():
                t['trials'][arm]={}
                for model,trials in models.items():
                    t['trials'][arm][model]=[]
                    for q in trials:
                        t['times_s']=q['times_s'];t['corrected_observation_hz'][arm]=q['corrected_observation_hz']
                        t['trials'][arm][model].append({k:v for k,v in q.items() if k not in ('times_s','corrected_observation_hz','orbit_prediction_hz')})
            record['tracks'].append(t)
        result.append(record)
    with gzip.open(path,'wt') as f:json.dump(dict(inventories=compact,diagnostics=result,
          orbit_reconstruction='prediction = corrected_observation + alias*PERIOD - offset - rate*(times-mean(times)) - residual',
          PERIOD_hz=1/4.4e-6),f,separators=(',',':'))


def gallery(path,rows,inventories,title):
    from leo.analysis.research.graph_position_membership import native_polynomial
    fig,axes=plt.subplots(3,2,figsize=(15,11),layout='constrained')
    cache={}
    for ax,row in zip(axes.flat,rows):
        inv=inventories[row['job_id']];job=inv['job']
        if job['job_id'] not in cache:
            root=Path(job['root'])/job['case'];cache[job['job_id']]=(read(root/'tracks.json'),read(root/'observations.json'))
        tracks,obs=cache[job['job_id']];track=tracks[row['track_index']]
        owned=set(inv['policy']['fitted_c']['proposed_associated_ids']);focus=set(track['observation_ids'])-owned
        lane=[o for o in obs if o['receiver']==row['receiver'] and o['channel']==row['channel'] and row['start_s']-4<=o['time_s']<=row['end_s']+4]
        for color,label,chosen in [('0.72','Already associated',[o for o in lane if o['observation_id'] in owned]),
                ('#e69f00','Other unassociated',[o for o in lane if o['observation_id'] not in owned|focus]),
                ('#cc1748','Unassociated target',[o for o in lane if o['observation_id'] in focus])]:
            ax.scatter([o['time_s'] for o in chosen],[o['measured_cfo_hz']/1000 for o in chosen],s=12,c=color,label=label)
        for k,curve in enumerate(native_polynomial(track,{o['observation_id']:o for o in obs})):
            ax.plot(track['times'],curve/1000,color='#0072b2',lw=.8,label='Graph polynomial' if k==0 else None)
        values=[o['measured_cfo_hz']/1000 for o in lane if o['observation_id'] in focus]
        if values:
            pad=max(2.,np.ptp(values)*.1);ax.set_ylim(min(values)-pad,max(values)+pad)
        ax.set(title=f"{row['label']} RX{row['receiver']} CH{row['channel']} · {row['points']} pts · {row['span_s']:.0f}s\n{row['classification']}",
               xlabel='Time in scan (s)',ylabel='Native GLRT CFO (kHz)');ax.grid(alpha=.2)
    for ax in list(axes.flat)[len(rows):]:ax.set_visible(False)
    fig.legend(*axes.flat[0].get_legend_handles_labels(),loc='outside lower center',ncol=4)
    fig.suptitle(title+'\nRed = target still unassociated; gray = already associated.',fontsize=13)
    fig.savefig(path,dpi=130);plt.close(fig)


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);(out/'figures').mkdir()
    protocol=read(args.inventory/'protocol.json');inventories={};records={};summaries=[];ledger=[];history=[];diagnostics=[]
    for job in protocol['jobs']:
        f=args.inventory/job['job_id']/'inventory.json'
        if not f.exists():continue
        inv=read(f);inventories[job['job_id']]=inv;summaries+=inv['summary']
        df=args.diagnostics/job['job_id']/'result.json'
        if df.exists():
            diag=read(df);diagnostics.append(diag)
            records.update({t['track_id']:t for t in diag['tracks']})
        else:
            for tf in (args.diagnostics/job['job_id']).glob('*.json'):
                if tf.name=='coarse.json':continue
                t=read(tf)
                if 'track_id' in t:records[t['track_id']]=t
        for row in inv['tracks']:
            if row['earlier_large'] and not row['current_large']:
                history.append(dict(label=job['label'],arm=row['arm'],component=row['component'],track_id=row['track_id'],recovered_points=row['recovered_points']))
            if not row['current_large']:continue
            r=row['current'];diag=records.get(row['track_id']);category,norads=classify(diag) if diag else ('Not diagnosed',[])
            best=min((q for v in diag['trials'][row['arm']].values() for q in v),key=lambda q:q['cost']) if diag else None
            ledger.append(dict(job_id=job['job_id'],track_id=row['track_id'],label=job['label'],aliases=';'.join(job['aliases']),
                scope='DS24' if 'DS24' in job['scopes'] else 'Session' if 'session research' in job['scopes'] else 'Automatic today',
                arm=row['arm'],receiver=r['receiver'],channel=r['channel'],component=row['component'],track_index=row['track_index'],
                points=r['unassociated_points'],span_s=r['span_s'],start_s=r['start_s'],end_s=r['end_s'],largest_gap_s=r['largest_gap_s'],
                active_curvature=r['active_curvature'],polynomial_RMS_hz=r['polynomial_RMS_hz'],pieces=r['pieces'],
                classification=category,candidate_norads=';'.join(map(str,norads)),
                best_score_candidate=best['norad'] if best else None,best_score_RMS_hz=best['rms_hz'] if best else None))
    ledger.sort(key=lambda r:(-r['points'],-r['span_s'],r['label'],r['track_id'],r['arm']))
    csvfile(out/'large_tracks.csv',ledger);csvfile(out/'previously_recovered.csv',history)
    csvfile(out/'per_scan.csv',[dict(s,aliases=';'.join(s['aliases']),scopes=';'.join(s['scopes'])) for s in summaries])
    write(out/'protocol.json',protocol)
    pack_evidence(out/'evidence.json.gz',inventories,diagnostics)
    fitted=[r for r in ledger if r['arm']=='fitted_c'];primary=[r for r in fitted if r['scope']!='Automatic today']
    counts=Counter(r['classification'] for r in fitted);points=Counter()
    for r in fitted:points[r['classification']]+=r['points']
    labels=list(counts)
    fig,axs=plt.subplots(1,2,figsize=(15,6),layout='constrained')
    axs[0].barh(labels,[counts[k] for k in labels],color='#4477aa');axs[0].set_xlabel('Large tracks')
    axs[1].barh(labels,[points[k] for k in labels],color='#228833');axs[1].set_xlabel('Unassociated GLRT points (track sums)')
    fig.suptitle('Causal catalogue diagnostics, matched c arms\nCandidate categories are investigation leads, not accepted recoveries')
    fig.savefig(out/'figures/classification.png',dpi=140);plt.close(fig)
    gallery(out/'figures/largest_ds24.png',[r for r in fitted if r['scope']=='DS24'][:6],inventories,'Largest remaining DS24 graph tracks')
    gallery(out/'figures/largest_session.png',[r for r in fitted if r['scope']=='Session'][:6],inventories,'Largest remaining tracks in the manual recovery/validation cases')
    pages=[]
    for start in range(0,len(primary),6):
        name=f'figures/gallery_{start//6+1:03}.png';gallery(out/name,primary[start:start+6],inventories,f'DS24 and manual cases — page {start//6+1}')
        pages.append(name)
    index=['# Every large DS24 and manual-case track','', 'All counts and identities are in [large_tracks.csv](large_tracks.csv). Every panel shows original native GLRT winners; no interpolated points are counted.','']
    for page in pages:index+=['![Unassociated GLRT inventory]('+page+')','']
    (out/'GALLERY.md').write_text('\n'.join(index))
    scopes=[]
    for scope in ['DS24','Session','Automatic today']:
        jobs=[j for j in inventories.values() if ('DS24' if 'DS24' in j['job']['scopes'] else 'Session' if 'session research' in j['job']['scopes'] else 'Automatic today')==scope]
        s=[s for inv in jobs for s in inv['summary'] if s['arm']=='fitted_c'];rows=[r for r in fitted if r['scope']==scope]
        scopes.append(dict(scope=scope,scans=len(s),tracks=len(rows),points=sum(v['large_track_unique_points'] for v in s),
            total=sum(v['total_GLRT'] for v in s),associated=sum(v['associated'] for v in s),outside=sum(v['unassociated_outside_graph'] for v in s)))
    write(out/'summary.json',dict(scope=scopes,classification=counts,track_point_sums=points,diagnosed=len(records),
        inventory_complete=len(inventories),frozen_jobs=len(protocol['jobs']),unavailable=protocol['unavailable']))
    table=['| Scope | Scans | Large tracks | Unique GLRT in large tracks | Associated / all GLRT | Outside graph, unassociated |','|---|---:|---:|---:|---:|---:|']
    for s in scopes:table.append(f"| {s['scope']} | {s['scans']} | {s['tracks']} | {s['points']:,} | {100*s['associated']/max(s['total'],1):.2f}% | {s['outside']:,} |")
    reason_table=['| Diagnostic outcome | Tracks | Point sum |','|---|---:|---:|']+[f'| {k} | {counts[k]} | {points[k]:,} |' for k in labels]
    text=f'''# Comprehensive large-track inventory and causal recovery diagnostics

This audit inventories every available qualified DS24 result, preserves today's manual recovery cases, and includes available automatic analyses updated on October 29 in America/Los_Angeles. Recordings are deduplicated using session, raw-recording authority and input-manifest identities. **No new satellite association has been adopted by this diagnostic sweep.**

{chr(10).join(table)}

Counts above use the fitted-c membership; [per_scan.csv](per_scan.csv) and [large_tracks.csv](large_tracks.csv) include both c=0 and fitted-c separately. Large means at least 20 remaining original GLRT points spanning at least 20 seconds. The ledger retains gaps, piece counts, active curvature and polynomial RMS. A span does not imply uninterrupted support.

DS24 revision 2 has 103 members, including adaptive recordings with DS25 aliases. Ten slots lack a qualified baseline: DS24-0001–0009 were input-unavailable; DS24-0056 / DS25-0037 had no active curvature. These slots remain explicitly unassessed. GLRT outside the graph are counted separately; this is an exhaustive available **graph-track** inventory, not a claim to have found every curve among those untracked points.

## Diagnostic findings

{chr(10).join(reason_table)}

![Diagnostic outcomes](figures/classification.png)

Categories are hierarchical: an earlier category wins. A candidate must pass the relevant screen for the same NORAD in both c arms. “Current-position” permits each arm's incumbent position; regional tests share candidate/position hypotheses between arms. A category can contain competing identities. No discovery count is added to association coverage.

![Largest DS24 tracks](figures/largest_ds24.png)

![Largest manual-case tracks](figures/largest_session.png)

The [complete indexed gallery](GALLERY.md) shows every large remaining track in DS24 and the manual cases. Gray points are already associated, red is the unassociated target, and orange is other unassociated GLRT. The CSV also covers the automatic-analysis population.

## What was tested

1. Replay each frozen baseline or qualified research policy and preserve both c-arm membership sets, including postfit associations. Earlier large tracks that were recovered remain in [previously_recovered.csv](previously_recovered.csv).
2. Search the existing causal sky bank, including satellites absent from the current prior/association model. Screen phases from -15 to +15 seconds in 3-second steps, at both incumbent positions and nine fixed regional points (-10, 0, +10 km east and north). These are a coarse square grid inside the 25 km box, not a dense convergence map.
3. Nominate distinct runner-up identities using at most 16 observed samples and orbit interpolation on a 2-second grid. Union the c-arm nominations, then refine phase on **every original point of the full graph track** using exact orbit evaluation. Both arms receive the same candidate identities, phase windows and regional hypotheses.
4. Compare a 1,000 Hz offset prior; that offset plus a 0.5 Hz/s rate prior; and an intentionally broad offset for shape-only diagnosis. Integer frequency alias is profiled. The rate and broad offset are per-track diagnostic freedoms, not a learned receiver correction.
5. Record elevation, RMS, mean, slope, quadratic structure, steps, autocorrelation, offset and rate bounds. Physical screening requires elevation >=0 degrees, RMS <=450 Hz, |offset| <=3,000 Hz, |rate| <=2 Hz/s and the existing noise screen. Visibility here means above horizon; antenna-pattern likelihood is not tested.

The regional sweep freezes receiver calibration from the incumbent. A better single-track fit away from the incumbent **does not prove a joint local minimum**, because other tracks and calibration must be refitted together. Raw causal orbit predictions in this screen do not include the incumbent's fitted satellite orbital modes; disagreement may also reflect that distinction. The archive records every exact trial and its residual vector.

## Recovery policy and next decisions

The goal is to explain every large track, but “a clear curve exists” is not enough to establish identity or independent position information. Current-position candidates should first be reintroduced whole under the existing causal phase priors, jointly refitted, and checked for loss of old associations. Regional-only candidates require matched multi-start **joint** fits. Small-rate candidates require cross-satellite and cross-receiver residual agreement before attributing the rate to hardware. Offset conflicts require a band/receiver calibration audit. Structured residuals require covariance, timing, join and segment checks, not an automatic gate relaxation.

Use original GLRT IDs to prevent double-counting fragments. Any candidate accepted later must report both c arms, retained old points, added target points, frequency fit and position error separately. Evaluation GPS must not select candidates, priors, starts or acceptance. No future TLE, collection, production change or golden-fixture update was used here.

## Artifacts and reproducibility

- [Full track ledger](large_tracks.csv), [per-scan accounting](per_scan.csv), [recovery history](previously_recovered.csv), [protocol](protocol.json), [summary](summary.json).
- [Compressed evidence archive](evidence.json.gz) contains point IDs, source roots/hashes, policies and exact diagnostic residuals. The frozen public input list derives from the preceding promotion inventory with statuses refreshed at freeze time; later arrivals are outside this snapshot.
- Tools: `inventory_all_large_tracks.py`, `diagnose_all_large_tracks.py`, `test_inventory_recovery.py`, `report_all_large_tracks.py` in `tools/`. Pure alias/rate and shortlist diagnostics have component-owned tests.
- Diagnostic searches are provisional. A low RMS or a lower in-sample score is not a position-accuracy claim.
'''
    (out/'README.md').write_text(text)
    print(json.dumps(scopes,indent=2));print(counts)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('inventory','diagnostics','output'):p.add_argument('--'+key,type=Path,required=True)
    run(p.parse_args())
