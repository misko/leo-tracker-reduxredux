"""Serial bounded PLUTO+ replay; no RF or firmware operations."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
REMOTE='/mnt/glrtbench/streaming-tracks-f363-v1'
INPUTS='/mnt/glrtbench/curvature-tracks-f363-v1'
WRAPPER='/mnt/glrtbench/native-adaptive/current/measure-run'
AUTH=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
OPTIONS=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
         '-o','UserKnownHostsFile='+str(ROOT/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
SSH=AUTH+['ssh']+OPTIONS+['root@192.168.1.15']


def run(command,timeout=150):
    return subprocess.run(command,capture_output=True,text=True,timeout=timeout,check=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--name',required=True)
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--unit',type=Path,required=True)
    args=p.parse_args()
    if not args.name.replace('-','').isalnum():
        raise ValueError('invalid name')
    out=HERE/'qualification'/args.name/'device'
    out.mkdir(exist_ok=False)
    (out/'device-before.txt').write_text(run(SSH+['uname -a; cat /sys/devices/system/cpu/online; ps']).stdout)
    run(SSH+['mkdir -p '+REMOTE])
    for source,suffix in [(args.binary,'cli'),(args.unit,'unit')]:
        remote=f'{REMOTE}/{args.name}-{suffix}'
        run(AUTH+['scp','-O']+OPTIONS+[str(source.resolve()),'root@192.168.1.15:'+remote])
        receipt=run(SSH+['chmod 755 '+shlex.quote(remote)+'; sha256sum '+shlex.quote(remote)]).stdout
        if receipt.split()[0]!=sha(source):
            raise ValueError('uploaded binary hash mismatch')
    unit=run(SSH+[f'{WRAPPER} 90 {REMOTE}/{args.name}-unit'])
    (out/'unit.stdout').write_text(unit.stdout)
    (out/'unit.stderr').write_text(unit.stderr)
    rows=[]
    for side,repeats in [('arm',3),('server',1)]:
        remote_input=f'{INPUTS}/{side}-observations.tsv'
        remote_hash=run(SSH+['sha256sum '+remote_input]).stdout.split()[0]
        local_input=HERE.parent/f'2026_09_30_arm_fast_tracks/server-baseline/output/{side}-observations.tsv'
        if remote_hash!=sha(local_input):
            raise ValueError('device input mismatch')
        for repeat in range(repeats):
            result=run(SSH+[f'{WRAPPER} 90 {REMOTE}/{args.name}-cli {remote_input}'])
            path=out/f'{side}-{repeat}.tsv'
            path.write_text(result.stdout)
            (out/f'{side}-{repeat}.stderr').write_text(result.stderr)
            equal=sha(path)==sha(out.parent/f'{side}-0.tsv')
            timings=[float(line.split('\t')[2]) for line in result.stderr.splitlines()
                     if line.startswith('TIMING\treconstruct_s\t')]
            row={'side':side,'repeat':repeat,'host_byte_identical':equal,
                 'reconstruct_s':timings[0] if timings else None,'output_sha256':sha(path)}
            rows.append(row)
            print(json.dumps(row),flush=True)
    (out/'receipt.json').write_text(json.dumps({'binary_sha256':sha(args.binary),
        'unit_sha256':sha(args.unit),'rows':rows,'unit_exit_code':0,
        'scope':'Physical PLUTO+ saved-observation replay; parsing and stdout excluded from reconstruct_s'},indent=2)+'\n')


if __name__=='__main__':
    main()
