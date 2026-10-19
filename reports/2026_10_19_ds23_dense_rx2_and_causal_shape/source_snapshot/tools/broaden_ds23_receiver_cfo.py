"""RF-only bounded carrier-basin check; no orbit or position input."""

import argparse
import copy
import json
from pathlib import Path
import numpy as np
from local_pilot_refinement import PilotWorkspace
from probe_ds23_refined_curve_position import proposed_delta
from refine_ds23_receiver_panel import OUT
from run_algo01_ds23_sample import ROOT,read,write,sha


def worker(case,worker_id):
    source=read(OUT/(case+'_refined.json'));z=np.load(OUT/(case+'_panel.npz'));metadata=json.loads(str(z['metadata_json']));fs=metadata['sample_rate_hz']
    rows=[];changed=0
    for number,original in enumerate(source['rows']):
        if number%2!=worker_id:continue
        row=copy.deepcopy(original);p=row['point'];v=z[p['window_key']][:,p['receiver_offset']]
        y=v[:,0].astype(float)+1j*v[:,1].astype(float);epoch=p['peak']['integer_epoch_sample']+p['peak']['fractional_epoch_offset_samples']
        workspace=PilotWorkspace(y,fs,p['edge'],epoch,rotation_cache_bytes=64*1024*1024)
        f=row['archived_CFO_hz']+np.arange(-600,601,20.);old=row['joint_CFO_epoch_rate']
        starts=[]
        for offset,ppm in [(0.,0.),(old['offset_samples'],old['modulation_ppm'])]:
            score=workspace.evaluate(f,offset,ppm);k=int(np.argmax(score))
            if 0<k<len(f)-1:starts.append((float(score[k]),float(f[k])))
        reliable=proposed_delta(row,'joint_CFO_epoch_rate')[1]=='refined'
        threshold=old['score'] if reliable else float(workspace.evaluate([row['archived_CFO_hz']])[0])
        accepted=False;best=max(starts,default=None)
        if best and best[0]>threshold+1e-5:
            joint=workspace.joint_fit(best[1])
            candidate=dict(row,joint_CFO_epoch_rate=joint)
            if proposed_delta(candidate,'joint_CFO_epoch_rate')[1]=='refined' and abs(joint['CFO_hz']-row['archived_CFO_hz'])<=800 and joint['score']>threshold+1e-5 and joint['margin']>=max(0.,old['margin'] if reliable else 0.):
                fixed=workspace.frequency_fit(joint['CFO_hz']);odd=workspace.frequency_fit(joint['CFO_hz'],subset='odd');even=workspace.frequency_fit(joint['CFO_hz'],subset='even')
                for r in (fixed,joint,odd,even):r['effective_time_from_probe_start_s']=workspace.effective_time(r)
                row.update(joint_CFO_epoch_rate=joint,fixed_epoch_CFO=fixed,odd_frames=odd,even_frames=even)
                accepted=True;changed+=1
        row['broad_carrier_check']=dict(accepted=accepted,old_joint_CFO_hz=old['CFO_hz'],
            old_reliable=reliable,scout_peak_score=None if best is None else best[0],radius_hz=600,final_bound_hz=800)
        rows.append(row)
        if len(rows)%50==0:print(case,'broad worker',worker_id,len(rows),'changed',changed,flush=True)
    write(OUT/f'{case}_broad_worker{worker_id}.json',dict(case=case,rows=rows,source_sha256=sha(Path(__file__)),
        original_refined_sha256=sha(OUT/(case+'_refined.json')),no_GPS_TLE_or_track_shape_used=True))


def combine(case):
    old=read(OUT/(case+'_refined.json'));workers=[read(OUT/f'{case}_broad_worker{k}.json') for k in range(2)]
    rows=[r for w in workers for r in w['rows']]
    assert len(rows)==len({r['point']['observation_id'] for r in rows})==len(old['rows'])
    old.update(rows=rows,broaden_source_sha256=sha(Path(__file__)),
        initial_refinement_sha256=sha(OUT/(case+'_refined.json')),no_original_points_removed=True)
    write(OUT/(case+'_broad_refined.json'),old)
    print(case,'broadened',sum(r['broad_carrier_check']['accepted'] for r in rows),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--worker-id',type=int,choices=[0,1]);parser.add_argument('--combine',action='store_true');args=parser.parse_args()
    if args.combine:combine(args.case)
    else:worker(args.case,args.worker_id)
