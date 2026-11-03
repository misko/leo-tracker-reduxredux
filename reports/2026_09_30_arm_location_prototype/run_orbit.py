"""Run actual SGP4 on ARM and compare its orbit table with the server table."""
import hashlib
import json
import os
import subprocess
import numpy as np
from arm import HERE,ROOT,SSH,OPTIONS,remote,upload
from check import pack,compare

def main():
    m=json.loads((HERE/'inputs.json').read_text());local=HERE/'local';step=10;nk=(m['knots']-1)//step+1
    for name in ('orbit-arm','tles.txt'):upload(local/name)
    remote('chmod +x '+ROOT+'/orbit-arm')
    command=f"ulimit -v 180000; {ROOT}/orbit-arm {ROOT}/tles.txt {m['start_utc_ns']} {m['knot_start_s']} {step} {nk} {ROOT}/arm-states.bin"
    output=remote(command,120);(HERE/'arm-orbit.json').write_text(output)
    path=local/'arm-states.bin'
    subprocess.run([*SSH,'scp','-O',*OPTIONS,'root@192.168.1.15:'+ROOT+'/arm-states.bin',str(path)],capture_output=True,check=True,timeout=120)
    subprocess.run(['sudo','-n','chown',f'{os.getuid()}:{os.getgid()}',str(path)],check=True)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==remote('sha256sum '+ROOT+'/arm-states.bin').split()[0]
    actual=np.fromfile(path,dtype='<f8').reshape(len(m['satellite_ids']),nk,6)
    expected=np.load(local/'states.npy',mmap_mode='r')[:,::step]
    errors=dict(max_position_error_m=float(np.max(abs(actual[...,:3]-expected[...,:3]))*1000),max_velocity_error_m_s=float(np.max(abs(actual[...,3:]-expected[...,3:]))*1000),table_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    fixture=local/'ephemeris-arm-generated.bin';pack(fixture,m,actual,step);upload(fixture)
    scores=remote('ulimit -v 180000; '+ROOT+'/score-arm '+ROOT+'/'+fixture.name,120)
    (HERE/'arm-generated-scores.json').write_text(scores)
    errors['comparison']=compare(m,json.loads(scores))
    (HERE/'orbit-validation.json').write_text(json.dumps(errors,indent=2)+'\n')
    print(output,flush=True)
    print({k:v for k,v in errors.items() if k!='comparison'},flush=True)
    print([(x['name'],x['candidate_matches'],x['tau_matches'],x['score_delta_hz']) for x in errors['comparison']],flush=True)

if __name__=='__main__':main()
