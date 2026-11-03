"""Build/test compact C scoring against the frozen published DS9 result."""
import hashlib
import json
import math
import struct
import subprocess
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'


def pack(path,m,states,step,tracks=None,ids=None):
    tracks=m['tracks'] if tracks is None else tracks
    ids=m['satellite_ids'] if ids is None else ids
    with path.open('wb') as f:
        f.write(struct.pack('<5I2d',0x31434f4c,len(ids),states.shape[1],len(tracks),len(m['points']),m['knot_start_s'],step))
        for p in m['points']:f.write(np.array(p['receiver']+p['up'],dtype='<f8').tobytes())
        for t in tracks:
            f.write(struct.pack('<2I',len(t['times_s']),len(np.unique(np.floor(t['times_s'])))))
            f.write(np.asarray(t['times_s'],dtype='<f8').tobytes())
            f.write(np.asarray(t['measured_hz'],dtype='<f8').tobytes())
            f.write(np.asarray(t['training_mask'],dtype='u1').tobytes())
        f.write(np.asarray(ids,dtype='<i4').tobytes());f.write(np.asarray(states,dtype='<f8').tobytes())


def compare(m,result):
    reports=[]
    for point,got in zip(m['points'],result['points'],strict=True):
        expected={x['track_id']:x for x in point['expected_tracks']}
        rows=[]
        for track,actual in zip(m['tracks'],got['tracks'],strict=True):
            e=expected[track['track_id']]
            rows.append(dict(track_id=track['track_id'],candidate_match=str(actual['candidate_id'])==str(e['candidate_id']),tau_match=actual['tau_s']==e['tau_s'],held_delta_hz=None if e['heldout_rms_hz'] is None or actual['held_hz'] is None else actual['held_hz']-e['heldout_rms_hz'],actual=actual,expected=e))
        reports.append(dict(name=point['name'],score_hz=got['score_hz'],expected_score_hz=point['expected_score_hz'],score_delta_hz=got['score_hz']-point['expected_score_hz'],candidate_matches=sum(x['candidate_match'] for x in rows),tau_matches=sum(x['tau_match'] for x in rows),track_count=len(rows),max_abs_held_delta_hz=max(abs(x['held_delta_hz']) for x in rows if x['held_delta_hz'] is not None),tracks=rows))
    return reports


def main():
    local=HERE/'local';m=json.loads((HERE/'inputs.json').read_text())
    states=np.load(local/'states.npy',mmap_mode='r')
    commands=[]
    for name,compiler,flags in [('score-host','gcc',[]),('score-arm',CC,['-D_GNU_SOURCE','-DARM_TARGET','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard'])]:
        cmd=[compiler,'-std=c11','-O3','-fno-fast-math',*flags,str(HERE/'score.c'),'-lm','-o',str(local/name)]
        subprocess.run(cmd,check=True);commands.append(cmd)
    summary={}
    for step in (10,30,60):
        fixture=local/f'ephemeris-{step}.bin';compact=states[:,::step,:]
        pack(fixture,m,compact,step)
        output=subprocess.check_output([str(local/'score-host'),str(fixture)],timeout=120,text=True)
        (HERE/f'host-{step}.json').write_text(output)
        result=json.loads(output);comparison=compare(m,result)
        summary[str(step)]=dict(cpu_seconds=result['cpu_seconds'],wall_seconds=result['wall_seconds'],peak_rss_kib=result['peak_rss_kib'],fixture_bytes=fixture.stat().st_size,ephemeris_bytes=compact.nbytes,fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),comparisons=comparison)
        print(step,[(x['name'],x['candidate_matches'],x['tau_matches'],x['score_delta_hz'],x['max_abs_held_delta_hz']) for x in comparison], 'host seconds',result['wall_seconds'],flush=True)
    (HERE/'host-comparison.json').write_text(json.dumps(summary,indent=2)+'\n')
    (HERE/'builds.json').write_text(json.dumps(dict(commands=commands,source_sha256=hashlib.sha256((HERE/'score.c').read_bytes()).hexdigest(),binaries={name:hashlib.sha256((local/name).read_bytes()).hexdigest() for name in ['score-host','score-arm']}),indent=2)+'\n')


if __name__=='__main__':main()
