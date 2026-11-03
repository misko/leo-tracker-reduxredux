"""Bounded physical replay of supplied-track conversion and fixed-site scoring.

No RF, production service or firmware operations. Run only with explicit device
authorization. Inputs are the named DS9 qualification artifacts, not new capture.
"""
import argparse
import json
from pathlib import Path
import statistics
import subprocess

from leo.native_pipeline.runner import digest,finite_json,write_json


def command(argv):
    return subprocess.run(list(map(str,argv)),capture_output=True,text=True,check=True,timeout=150)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--exclusive-candidates',action='store_true',
        help='Qualify the exclusive-membership checkpoint using ARM-generated orbit states')
    args=parser.parse_args();output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[1];reports=root/'reports'
    q=reports/'2026_10_01_native_replay_qualification'
    checkpoint=q/('exclusive-location-input' if args.exclusive_candidates else 'coarse-location-input')
    authority=q/('native-orbit-authority' if args.exclusive_candidates else 'location-authority')
    host_path=q/('exclusive-location-host.json' if args.exclusive_candidates else 'coarse-location-host.json')
    auth=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(reports/'2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    ssh=auth+['ssh']+options+['root@192.168.1.15']
    remote='/mnt/glrtbench/'+output.name
    if not output.name.replace('-','').isalnum():raise ValueError('invalid diagnostic directory name')
    command(ssh+['mkdir '+remote])
    files={'pipeline':Path('/var/tmp/leo-modular-pipeline-arm/leo-adaptive-pipeline'),
        'location':reports/'2026_09_30_native_adaptive_deployment/location/corrected-native-arm-v1/artifacts/arm/leo-location',
        'observations':q/'projection-qualified/observations.tsv',
        'graph':checkpoint/'graph.tsv',
        'authority':authority/'authority.loc1',
        'tracks':reports/'2026_10_01_arm_ungated_tracker_comparison/coarse-seeded/tracks-0.tsv'}
    for name,path in files.items():
        command(auth+['scp','-O']+options+[path,'root@192.168.1.15:'+remote+'/'+name])
        if command(ssh+['sha256sum '+remote+'/'+name]).stdout.split()[0]!=digest(path):
            raise ValueError('device input hash mismatch')
    command(ssh+['chmod 755 '+remote+'/pipeline '+remote+'/location'])
    result=command(ssh+[remote+'/pipeline '+remote+'/observations '+remote+'/graph '+remote+'/authority '+remote+'/input.loc1 --tracks '+remote+'/tracks'+(' --exclusive-candidates' if args.exclusive_candidates else '')])
    (output/'conversion.stdout').write_text(result.stdout)
    (output/'conversion.stderr').write_text(result.stderr)
    input_hash=command(ssh+['sha256sum '+remote+'/input.loc1']).stdout.split()[0]
    if input_hash!=digest(checkpoint/'tracks.loc1'):raise ValueError('native conversion differs on ARM')
    if args.exclusive_candidates:
        members_hash=command(ssh+['sha256sum '+remote+'/input.loc1.members.tsv']).stdout.split()[0]
        if members_hash!=digest(checkpoint/'tracks.loc1.members.tsv'):
            raise ValueError('native membership selection differs on ARM')
    host=finite_json(host_path);trials=[]
    for i in range(3):
        result=command(ssh+['/mnt/glrtbench/native-adaptive/current/measure-run 90 '+remote+'/location score '+remote+'/input.loc1 2'])
        (output/f'score-{i}.json').write_text(result.stdout)
        (output/f'score-{i}.stderr').write_text(result.stderr)
        actual=json.loads(result.stdout)
        # The current frozen scorer is expected to be bit-identical in its JSON.
        if actual!=host:raise ValueError('ARM location output differs from host')
        timing=next(json.loads(line) for line in result.stderr.splitlines()
                    if line.startswith('{') and json.loads(line).get('scope')=='whole_process')
        trials.append(timing)
    receipt={'status':'complete','input_sha256':input_hash,'host_arm_conversion_identical':True,
        'host_arm_scores_identical':True,'trials':trials,'median_wall_s':statistics.median(t['wall_s'] for t in trials),
        'payload_sha256':{k:digest(p) for k,p in files.items()},
        'exclusive_candidates':args.exclusive_candidates,
        'host_reference_sha256':digest(host_path),
        'scope':'Two fixed comparison sites; not a position search or independent-evidence claim'}
    write_json(output/'receipt.json',receipt)
    print(json.dumps(receipt))


if __name__=='__main__':main()
