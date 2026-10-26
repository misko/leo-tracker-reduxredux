"""Original graph/noise gates on coherent expansion additions; no identities."""
import argparse
import os
from pathlib import Path
import signal
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from integrate import read,write,digest,sha
sys.path.insert(0,str(HERE.parent))
from prepare_overlay import rebuild_graph,scientific_imports,normalized
from integration import bank_reuse_audit,graph_inputs_changed
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')


def main(case):
    assert case in ('DS24-0011','DS24-0097')
    assert all(os.environ.get(k)=='1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'))
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120second graph cap')));signal.alarm(120)
    began=time.monotonic();ledger=read(HERE/(case+'_additions.json'));rows=ledger['observations']
    assert digest(rows)==ledger['observations_sha256']
    original=read(SOURCE/case/'observations.json');old_tracks=read(SOURCE/case/'tracks.json')
    assert rows[:len(original)]==original
    config=read(REPO/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json')['config']
    tracks,g=rebuild_graph(rows,case,config);_,_,_,estimate=scientific_imports()
    noise=normalized(estimate(tracks,rows));old_noise=read(SOURCE/case/'radio_noise.json')
    shifts=[noise['per_observation_noise_sigma_hz'][oid]-v for oid,v in old_noise['per_observation_noise_sigma_hz'].items() if oid in noise['per_observation_noise_sigma_hz']]
    bank=dict(np.load(SOURCE/case/'bank.npz'))
    support=bank_reuse_audit(bank['time_s'].tolist(),bank['norad'].tolist(),read(SOURCE/case/'nominal_elements.json'),
        read(SOURCE/'causal_prior'/case/'receipt.json'),old_tracks,tracks)
    ids={o['observation_id'] for o in original};new={o['observation_id'] for o in rows}-ids
    graph_ids={oid for t in tracks for oid in t['observation_ids']};curved=set(g['curved_observation_ids'])
    original_graph={oid for t in old_tracks for oid in t['observation_ids']}
    memberships=[]
    for t in tracks:
        old=set(t['observation_ids'])&ids;added=set(t['observation_ids'])&new
        if not added:continue
        memberships.append(dict(track_id=t['key'],new_native_ids=sorted(added),incumbent_points=len(old),
            has_original_graph_points=bool(old&original_graph),curved=bool(set(t['observation_ids'])&curved),
            classification='extension_of_incumbent_RF_graph' if old&original_graph else 'new_RF_graph_without_incumbent_graph_points',
            satellite_family_classification='pending fresh causal catalogue association'))
    audit=dict(case=case,graph=g,new_native_owners=len(new),new_in_graph=len(new&graph_ids),
        new_in_curved_graph=len(new&curved),new_unassociated=len(new-graph_ids),
        original_GLRT_count=len(original),total_GLRT_count=len(rows),
        total_GLRT_graph_association_fraction=len(graph_ids)/len(rows),
        new_graph_ids=sorted(new&graph_ids),new_curved_ids=sorted(new&curved),new_outside_graph_ids=sorted(new-graph_ids),
        RF_graph_memberships=memberships,bank_support=support,input_changes=graph_inputs_changed(original,rows,old_tracks,tracks),
        staged_sha256=sha(HERE/(case+'_additions.json')),original_observations_sha256=sha(SOURCE/case/'observations.json'),
        incumbent_noise_proxy_reestimated=True,incumbent_noise_sigma_changed=sum(abs(v)>1e-10 for v in shifts),
        incumbent_noise_sigma_shift_range_hz=[min(shifts,default=0.),max(shifts,default=0.)],
        original_measurements_exactly_preserved=True,forced_satellite_identity=False,GPS_used=False,
        position_execution_authorized=False,seconds=time.monotonic()-began)
    audit=normalized(audit)
    folder=HERE/'graphs'/case;folder.mkdir(parents=True,exist_ok=False)
    write(folder/'observations.json',rows);write(folder/'tracks.json',tracks);write(folder/'radio_noise.json',noise);write(folder/'graph_audit.json',audit)
    print({k:audit[k] for k in ('case','new_native_owners','new_in_graph','new_in_curved_graph','new_unassociated','seconds')},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);main(parser.parse_args().case)
