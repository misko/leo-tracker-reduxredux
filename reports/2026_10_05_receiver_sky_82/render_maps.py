"""Compare original/new/combined sky maps; fail closed on incomplete cohorts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from sky_extension import temporal_kernel, BASELINE
from receiver_sky_model import disk_grid
import render_receiver_sky as graphics
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
WORK=Path('/srv/bulk/leo/receiver-sky-82-20261005')


def ready_records(cohort, allow_partial=False):
    original=[json.loads((BASELINE/'receiver-sky-maps/paired'/f'{s}.json').read_text()) for s in cohort['original_labels']]
    added=[];pending=[]
    for scan in cohort['new_labels']:
        path=WORK/'paired'/f'{scan}.json'
        if path.exists():
            r=json.loads(path.read_text())
            if r['scan']!=scan or r['reconstruction_max_hz']>=1e-5:
                raise ValueError('unverified paired evidence')
            added.append(r)
        else:
            pending.append(scan)
    if pending and not allow_partial:
        raise ValueError(f'{len(pending)}/64 additions still pending; do not present this as an 82-scan result')
    if not added:
        raise ValueError('no additional scan has completed paired evidence')
    return original,added,pending


def run(allow_partial=False):
    cohort=json.loads((HERE/'cohort.json').read_text())
    original,added,pending=ready_records(cohort,allow_partial)
    total=len(original)+len(added)
    out=HERE/f'maps-{total}-scans';out.mkdir(exist_ok=True)
    graphics.OUT=out
    epochs={s['label']:s['capture_start_ns'] for s in cohort['scans']}
    _,_,inside,grid=disk_grid(101)
    cases={};summary=[]
    for name,records in [('Original 18',original),(f'Additional {len(added)}',added),(f'Combined {total}',original+added)]:
        for arm,gate in [('fitted-c',600),('fitted-c',300),('zero-c',600),('zero-c',300)]:
            events=[e for r in records for e in r['events'] if e['arm']==arm and e['gate_hz']==gate]
            keys=[(e['scan'],e['satellite'],e['visit'],e['probe']) for e in events]
            assert len(set(keys))==len(keys)
            result=temporal_kernel(events,grid,epochs)
            cases[name,arm,gate]=result
            filename=f"{name.lower().replace(' ','-')}-{arm}-{gate}.npz"
            np.savez_compressed(out/filename,probability=result['probability'],supported=result['supported'],
                intervals=result['intervals'],time_blocks=result['time_block_count'],inside=inside,directions=grid)
            summary.append(dict(cohort=name,arm=arm,gate_hz=gate,scans=len(records),events=len(events),
                counts=[sum(e['outcome']==i for e in events) for i in range(3)],
                top_only_both=sum(e['top_candidate_outcome']==2 for e in events),
                temporal_blocks=result['total_time_blocks']))
            print(name,arm,gate,len(events),'outcomes',flush=True)
    names=['Original 18',f'Additional {len(added)}',f'Combined {total}']
    fig,axs=plt.subplots(3,3,figsize=(16,16))
    for row,name in enumerate(names):
        r=cases[name,'fitted-c',600];p=r['probability']
        for col,(values,title) in enumerate([(p[:,0]+p[:,2],'RX0'),(p[:,1]+p[:,2],'RX1'),(p[:,2],'Both')]):
            graphics.panel(axs[row,col],values,inside,f'{name} · {title}',r['supported'])
    partial=f' · PARTIAL: {len(pending)} additions pending' if pending else ''
    fig.suptitle('Receiver sky maps · original, additional, combined'+partial,fontsize=18)
    graphics.save(fig,'comparison.png','Conditional reception given ≥1 unique satellite match in the same channel / 20 ms probe. Fitted c; ±600 Hz.\n'
        'Same scan-balanced 10° smoother. Gray = insufficient evidence: fewer than 5 three-hour blocks or 20 encounter-time blocks within 15°.\n'
        'These are provisional Doppler associations, not absolute gain, identity certification, or localization accuracy.')
    name=names[-1];r=cases[name,'fitted-c',600];p=r['probability']
    fig,axs=plt.subplots(2,2,figsize=(13,12))
    for ax,values,title in zip(axs.flat,[p[:,0]+p[:,2],p[:,1]+p[:,2],p[:,2],r['time_block_count']],
                             ['RX0 reception','RX1 reception','Simultaneous shared reception','Evidence · three-hour blocks']):
        support=title.startswith('Evidence')
        graphics.panel(ax,values,inside,title,None if support else r['supported'],
                       cmap='cividis' if support else 'viridis',vmax=r['total_time_blocks'] if support else 1)
    fig.suptitle(f'{total} completed scans · empirical receiver sky maps'+partial,fontsize=18)
    graphics.save(fig,'sky-maps.png','Center = zenith; rim = horizon; stars = nominal pointing. Gray = insufficient evidence.\n'
        'All eligible paired outcomes fitted; no new train/test split. Neighboring scans are clustered for uncertainty.')
    fig,axs=plt.subplots(2,2,figsize=(13,12))
    for ax,(arm,gate) in zip(axs.flat,[('fitted-c',300),('fitted-c',600),('zero-c',300),('zero-c',600)]):
        r=cases[name,arm,gate]
        graphics.panel(ax,r['probability'][:,2],inside,f'{arm} · ±{gate} Hz · both',r['supported'])
    fig.suptitle(f'{total} completed scans · calibration and matching sensitivity',fontsize=18)
    graphics.save(fig,'sensitivity.png','Same refined inputs, selected satellite roster, timing, smoothing and support rules across RF arms.\n'
        'Calibration-dependent matching changes eligible outcome sets. No claim about position accuracy.')
    doc=dict(completed_total=total,pending=pending,status='partial' if pending else 'complete',summaries=summary,
             uncertainty='250 whole-three-hour-block bootstrap replicates',
             implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'summary.json').write_text(json.dumps(doc,indent=2))
    print(str(out),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--allow-partial',action='store_true')
    run(p.parse_args().allow_partial)
