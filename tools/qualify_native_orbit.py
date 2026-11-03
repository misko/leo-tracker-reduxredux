"""Native orbit generation versus frozen maintained-server SGP4 states."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import numpy as np
from leo.native_pipeline.orbit_input import select_tles
from leo.native_pipeline.runner import digest,finite_json,write_json


def command(argv,timeout=150):
    return subprocess.run(list(map(str,argv)),capture_output=True,text=True,check=True,timeout=timeout)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('authority',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--device',action='store_true');args=p.parse_args()
    authority=args.authority.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    meta=finite_json(authority/'authority.json')
    if 'sha256:'+digest(authority/'snapshot.tle')!=meta['tle_digest']:raise ValueError('TLE digest mismatch')
    tles=select_tles((authority/'snapshot.tle').read_text(),meta['satellite_ids'])
    (out/'selected.tle').write_text(tles)
    protocol={'position_tolerance_km':1e-6,'velocity_tolerance_km_s':1e-8,
        'scope':'Native propagation of frozen response-independent eligible catalogue; full validity selection remains frozen.'}
    write_json(out/'protocol.json',protocol)
    geometry=list(map(str,[meta['start_utc_ns'],meta['knot_start_s'],meta['knot_step_s'],meta['knot_count']]))
    host=Path('/var/tmp/leo-modular-location-host/leo-orbit')
    started=time.monotonic();r=command([host,out/'selected.tle',*geometry,out/'host.states'])
    host_wall=time.monotonic()-started
    (out/'host.json').write_text(r.stdout)
    if json.loads(r.stdout)['satellite_ids']!=meta['satellite_ids']:raise ValueError('native catalogue mismatch')
    if digest(authority/'states.npy')!=meta['files']['states.npy']:raise ValueError('server orbit state hash mismatch')
    expected=np.load(authority/'states.npy',mmap_mode='r')
    def compare(path):
        actual=np.fromfile(path,dtype='<f8').reshape(expected.shape)
        if not np.all(np.isfinite(actual)):raise ValueError('nonfinite native states')
        position=float(np.max(np.abs(actual[:,:,:3]-expected[:,:,:3])))
        velocity=float(np.max(np.abs(actual[:,:,3:]-expected[:,:,3:])))
        if position>protocol['position_tolerance_km'] or velocity>protocol['velocity_tolerance_km_s']:
            raise ValueError(f'native orbit tolerance exceeded: {position}, {velocity}')
        return {'max_position_component_error_km':position,'max_velocity_component_error_km_s':velocity}
    receipt={'host':compare(out/'host.states'),'host_wall_s':host_wall,'host_binary_sha256':digest(host),
             'tle_digest':meta['tle_digest'],'satellite_count':len(meta['satellite_ids']),'knot_count':meta['knot_count']}
    if args.device:
        root=Path(__file__).resolve().parents[1]
        auth=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
        options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+str(root/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
        ssh=auth+['ssh']+options+['root@192.168.1.15']
        if not out.name.replace('-','').isalnum():raise ValueError('invalid device directory name')
        remote='/mnt/glrtbench/'+out.name;command(ssh+['mkdir '+remote])
        arm=Path('/var/tmp/leo-modular-location-arm/leo-orbit')
        for name,path in [('orbit',arm),('selected.tle',out/'selected.tle')]:
            command(auth+['scp','-O']+options+[path,'root@192.168.1.15:'+remote+'/'+name])
            if command(ssh+['sha256sum '+remote+'/'+name]).stdout.split()[0]!=digest(path):raise ValueError('device payload hash mismatch')
        command(ssh+['chmod 755 '+remote+'/orbit'])
        result=command(ssh+['/mnt/glrtbench/native-adaptive/current/measure-run 90 '+remote+'/orbit '+remote+'/selected.tle '+' '.join(geometry)+' '+remote+'/arm.states'])
        (out/'arm.json').write_text(result.stdout);(out/'arm.stderr').write_text(result.stderr)
        if json.loads(result.stdout)['satellite_ids']!=meta['satellite_ids']:raise ValueError('ARM catalogue mismatch')
        command(auth+['scp','-O']+options+['root@192.168.1.15:'+remote+'/arm.states',out/'arm.states'])
        command(['sudo','-n','chown',f'{os.getuid()}:{os.getgid()}',out/'arm.states'])
        if command(ssh+['sha256sum '+remote+'/arm.states']).stdout.split()[0]!=digest(out/'arm.states'):raise ValueError('retrieved orbit hash mismatch')
        receipt['arm']=compare(out/'arm.states')
        receipt['arm_binary_sha256']=digest(arm)
        receipt['arm_timing']=next(json.loads(l) for l in result.stderr.splitlines() if l.startswith('{') and json.loads(l).get('scope')=='whole_process')
    receipt['status']='complete';write_json(out/'receipt.json',receipt);print(json.dumps(receipt))


if __name__=='__main__':main()
