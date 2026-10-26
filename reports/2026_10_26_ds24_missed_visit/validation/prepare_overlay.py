"""Prepare separate exploratory graph inputs; never rewrite a tracking export."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np

from integration import bank_reuse_audit,digest,graph_inputs_changed

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')


def encode(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(type(value).__name__)


def normalized(value):
    return json.loads(json.dumps(value,default=encode,allow_nan=False))


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(folder,name,value):
    with (folder/name).open('x') as stream:
        json.dump(value,stream,default=encode,indent=2,allow_nan=False);stream.write('\n')


def scientific_imports():
    sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools')]
    from evaluate_ds22_public_tracks import graph_rf_lanes
    from leo.analysis.polynomial_tracklets import TrackConfig
    from localize_merged_track_catalogue import raw_curvature
    from ds23_radio_noise import estimate
    return graph_rf_lanes,TrackConfig,raw_curvature,estimate


def rebuild_graph(rows,case,config):
    graph_rf_lanes,TrackConfig,raw_curvature,_=scientific_imports()
    tracks,assigned=graph_rf_lanes(rows,case,TrackConfig(**config))
    ids=[oid for t in tracks for oid in t['observation_ids']]
    if len(ids)!=len(set(ids)) or assigned!=len(ids):
        raise ValueError('new graph duplicates native owners')
    curved=[t for t in tracks if raw_curvature(dict(times=np.asarray(t['times']),values=np.asarray(t['values'])))]
    return normalized(tracks),dict(graph_points=assigned,graph_tracks=len(tracks),
        curved_tracks=len(curved),curved_graph_points=sum(len(t['observation_ids']) for t in curved),
        curved_observation_ids=sorted({oid for t in curved for oid in t['observation_ids']}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',required=True)
    parser.add_argument('--staged',type=Path,required=True)
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    split=read(ROOT/'split.json')
    if args.case not in split['development'] or Path(args.label).name!=args.label:
        raise ValueError('development-only exact case and safe output label required')
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
        if os.environ.get(key)!='1':raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('580s graph preparation cap')))
    signal.alarm(580);began=time.monotonic()
    staged=read(args.staged)
    if staged.get('schema')!='missed-visit-exploratory-observations-v1':
        raise ValueError('stage through the independent observation adapter first')
    if digest(staged['observations'])!=staged['observations_sha256']:
        raise ValueError('staged observation digest differs')
    folder=HERE/(args.case+'-'+args.label)
    folder.mkdir(exist_ok=False)
    original=read(SOURCE/args.case/'observations.json');old_tracks=read(SOURCE/args.case/'tracks.json')
    config=read(REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json')['config']
    tracks,graph=rebuild_graph(staged['observations'],args.case,config)
    _,_,_,estimate=scientific_imports()
    noise=estimate(tracks,staged['observations'])
    old_noise=read(SOURCE/args.case/'radio_noise.json')
    old_by_id=old_noise['per_observation_noise_sigma_hz'];new_by_id=noise['per_observation_noise_sigma_hz']
    shifts=[new_by_id[oid]-value for oid,value in old_by_id.items() if oid in new_by_id]
    bank=dict(np.load(SOURCE/args.case/'bank.npz'))
    # FreshScan's paired search uses the causal_prior receipt while the ephemeris
    # bank itself is pinned by the original preparation receipt.
    receipt=read(SOURCE/'causal_prior'/args.case/'receipt.json')
    bank_audit=bank_reuse_audit(bank['time_s'].tolist(),bank['norad'].tolist(),
        read(SOURCE/args.case/'nominal_elements.json'),receipt,old_tracks,tracks)
    changed=graph_inputs_changed(original,staged['observations'],old_tracks,tracks)
    original_ids={o['observation_id'] for o in original}
    new_ids={o['observation_id'] for o in staged['observations']}-original_ids
    graph_ids={oid for t in tracks for oid in t['observation_ids']}
    curved_ids=set(graph['curved_observation_ids'])
    result=dict(case=args.case,status='graph_prepared_pending_causal_association',
        staged_sha256=sha(args.staged),original_observations_sha256=sha(SOURCE/args.case/'observations.json'),
        tracking_export_sha256=sha(SOURCE/args.case/'tracking.json'),tracking_export_unchanged=True,
        observations_sha256=digest(staged['observations']),graph=graph,
        new_native_owners=len(new_ids),new_in_graph=len(new_ids&graph_ids),new_in_curved_graph=len(new_ids&curved_ids),
        new_unassociated=len(new_ids-graph_ids),bank_support=bank_audit,input_changes=changed,
        selection_conditioning='new margins selected over timing search; noise remains the existing uncalibrated proxy',
        incumbent_noise_proxy_reestimated=True,
        incumbent_noise_sigma_changed=sum(abs(v)>1e-10 for v in shifts),
        incumbent_noise_sigma_shift_range_hz=[min(shifts,default=0.),max(shifts,default=0.)],
        same_c_arm_inputs_required=True,position_execution_authorized=False,
        new_GPS_or_satellite_identity_used=False,seconds=time.monotonic()-began)
    write(folder,'observations.json',staged['observations']);write(folder,'tracks.json',tracks)
    write(folder,'radio_noise.json',noise);write(folder,'graph_audit.json',result)
    print(json.dumps({k:result[k] for k in ('case','status','new_native_owners','new_in_graph','new_in_curved_graph','new_unassociated','seconds')}))


if __name__=='__main__':
    main()
