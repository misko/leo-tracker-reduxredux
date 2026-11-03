"""Validate all frozen track formats on host and optionally physical PLUTO+.

Device mode installs into an exclusive diagnostics directory; no radio access.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from leo.native_pipeline.runner import digest, write_json


def command(argv):
    return subprocess.run(list(map(str,argv)),capture_output=True,text=True,check=True,timeout=90)


def qualify(output, device=False):
    root=Path(__file__).resolve().parents[1]
    reports=root/'reports'
    output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    host=Path('/var/tmp/leo-modular-pipeline-host')
    arm=Path('/var/tmp/leo-modular-pipeline-arm')
    full=reports/'2026_10_01_arm_ungated_full_scan/analysis'
    comparison=reports/'2026_10_01_arm_ungated_tracker_comparison'
    methods=['rolling','kalman-v2','linking-v2','coarse-seeded','rolling-backfill']
    files={'observations':full/'observations.tsv',**{
        name:full/'tracks-0.tsv' if name=='rolling-backfill' else comparison/name/'tracks-0.tsv'
        for name in methods}}
    unit=command([host/'test_pipeline'])
    receipt={'host_unit':unit.stdout,'inputs':{k:digest(p) for k,p in files.items()},'host':{}}
    for name in methods:
        result=command([host/'leo-adaptive-pipeline','--validate-tracks',files['observations'],files[name]])
        receipt['host'][name]=json.loads(result.stdout)
    if device:
        auth=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
        options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+str(reports/'2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
        ssh=auth+['ssh']+options+['root@192.168.1.15']
        remote='/mnt/glrtbench/'+output.name
        command(ssh+['mkdir '+shlex.quote(remote)])
        payload={**files,'cli':arm/'leo-adaptive-pipeline','unit':arm/'test_pipeline'}
        for name,path in payload.items():
            command(auth+['scp','-O']+options+[path,'root@192.168.1.15:'+remote+'/'+name])
            actual=command(ssh+['sha256sum '+remote+'/'+name]).stdout.split()[0]
            if actual != digest(path):raise RuntimeError('device payload hash mismatch')
        command(ssh+['chmod 755 '+remote+'/cli '+remote+'/unit'])
        receipt['device_unit']=command(ssh+[remote+'/unit']).stdout
        receipt['device']={}
        for name in methods:
            result=command(ssh+[remote+'/cli --validate-tracks '+remote+'/observations '+remote+'/'+name])
            receipt['device'][name]=json.loads(result.stdout)
        if receipt['device']!=receipt['host']:raise RuntimeError('host/device track port mismatch')
        receipt['arm_binary_sha256']=digest(arm/'leo-adaptive-pipeline')
    receipt['host_binary_sha256']=digest(host/'leo-adaptive-pipeline')
    receipt['status']='complete'
    write_json(output/'receipt.json',receipt)
    print(json.dumps(receipt))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--device',action='store_true')
    args=parser.parse_args()
    qualify(args.output,args.device)
