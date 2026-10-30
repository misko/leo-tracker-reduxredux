"""Freeze same-lane pair nominations for curves lacking block partitions."""
import argparse,csv,hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from predictive_graph_bundle import polynomial_pair


def run(args):
    jobs={r['track_id']:r for r in read(args.study/'systematic-annotation-v1/protocol.json')['rows']}
    rows=[r for r in csv.DictReader(args.annotations.open()) if r['status']=='insufficient_partitions']
    cache={};seen=set();bundles=[]
    for row in rows:
        job=jobs[row['track_id']];path=Path(job['inventory'])
        if path not in cache:
            inv=read(path);tracks_path=Path(inv['job']['root'])/inv['job']['case']/'tracks.json'
            occupied=set(o for a in inv['policy'].values() for o in a['proposed_associated_ids'])
            cache[path]=(inv,read(tracks_path),occupied,tracks_path)
        inv,tracks,occupied,tracks_path=cache[path];target=next(t for t in inv['tracks'] if t['track_id']==row['track_id']);a=tracks[target['track_index']]
        if occupied.intersection(a['observation_ids']):continue
        for other in inv['tracks']:
            pair=tuple(sorted([target['track_id'],other['track_id']]))
            if pair in seen or pair[0]==pair[1] or not other['current_large']:continue
            b=tracks[other['track_index']]
            if (a['receiver'],a['channel'],a['rf_hz'])!=(b['receiver'],b['channel'],b['rf_hz']):continue
            if occupied.intersection(b['observation_ids']) or set(a['observation_ids'])&set(b['observation_ids']):continue
            if max(a['start_s'],b['start_s'])-min(a['end_s'],b['end_s'])>12:continue
            times=np.r_[a['times'],b['times']]
            if len(np.unique(times))!=len(times) or len(np.unique(np.floor(times/12)))<3:continue
            fit=polynomial_pair(a,b)
            if not fit or fit['RMS_hz']>=250:continue
            seen.add(pair);bid=hashlib.sha256('|'.join(pair).encode()).hexdigest()[:20]
            bundles.append(dict(bundle_id=bid,job=inv['job'],inventory=str(path),points=len(times),
                members=[dict(track_id=target['track_id'],track_index=target['track_index'],alias_lift=0),
                         dict(track_id=other['track_id'],track_index=other['track_index'],alias_lift=fit['alias_lift'])],
                nomination=fit,source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (path,tracks_path,args.annotations)},
                nomination_is_not_validation=True,selection_uses_frozen_graph_CFO=True,GPS_used=False,satellite_identity_used=False))
    bundles.sort(key=lambda b:(-b['points'],b['bundle_id']))
    write(args.output,dict(bundles=bundles,short_fragment_inputs=len(rows),same_RX_CH_RF=True,maximum_gap_s=12,
        maximum_polynomial_order=4,noise_floor_hz=150,BIC_penalty=True,maximum_nomination_RMS_hz=250,
        conditional_on_full_data_frozen_graph_and_pair_nomination=True,no_association_authorized=True))
    print('bundles',len(bundles),'scans',len({b['job']['job_id'] for b in bundles}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','annotations','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
