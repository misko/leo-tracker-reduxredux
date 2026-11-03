"""Track ARM-emitted observations in place, with an independent host execution."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from leo.native_pipeline.membership import read_observations,read_tracks
from leo.native_pipeline.runner import digest,finite_json,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True)
    p.add_argument('output',type=Path);args=p.parse_args()
    execution=finite_json(args.replay/'execution.json');protocol=finite_json(args.replay/'protocol.json')
    observations=args.replay/'observations.tsv'
    if execution['exit_code']!=0 or execution['observations_sha256']!=digest(observations):
        raise ValueError('replay observation checkpoint is incomplete or changed')
    if digest(args.replay/'protocol.json')!=execution['protocol_sha256']:
        raise ValueError('replay protocol differs')
    root=Path(__file__).resolve().parents[1];reports=root/'reports';q=shlex.quote
    host_seed=reports/'2026_09_30_arm_fast_tracks/grid/grid-trial-v3'
    arm_seed=reports/'2026_09_30_arm_fast_tracks/grid/grid-trial-arm-v3'
    host_tracker=reports/'2026_09_30_arm_curvature_tracks/hybrid-v1/artifacts/leo-curvature-tracks'
    arm_tracker=host_tracker.with_name(host_tracker.name+'-arm')
    if not args.output.name.replace('-','').isalnum():raise ValueError('invalid diagnostics directory')
    args.output.mkdir(parents=True,exist_ok=False)
    def local(argv,name):
        result=subprocess.run(list(map(str,argv)),capture_output=True,text=True,check=True,timeout=90)
        (args.output/name).write_text(result.stdout);(args.output/(name+'.stderr')).write_text(result.stderr)
    local([host_seed,observations,151,8,512,8,4,16],'host-seeds.tsv')
    local([host_tracker,observations,'--acceleration',250,'--seeds',args.output/'host-seeds.tsv'],'host-tracks.tsv')
    auth=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(reports/'2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    ssh=auth+['ssh']+options+['root@192.168.1.15']
    def remote(text):return subprocess.run(ssh+[text],capture_output=True,text=True,check=True,timeout=120)
    if '/modular-ds9-iq-v1/leo-recorded-' in remote('ps').stdout:
        raise ValueError('paced measurement still active')
    directory='/mnt/glrtbench/'+args.output.name;remote('mkdir '+q(directory))
    for name,path in [('seed',arm_seed),('tracker',arm_tracker)]:
        subprocess.run(auth+['scp','-O']+options+[str(path),'root@192.168.1.15:'+directory+'/'+name],
                       capture_output=True,check=True,timeout=90)
        if remote('sha256sum '+q(directory+'/'+name)).stdout.split()[0]!=digest(path):
            raise ValueError('tracker payload differs')
    remote('chmod 755 '+q(directory+'/seed')+' '+q(directory+'/tracker'))
    device_observations=protocol['device_iq_directory']+'/'+protocol['projection']['observations_name']
    if remote('sha256sum '+q(device_observations)).stdout.split()[0]!=digest(observations):
        raise ValueError('device observation checkpoint differs')
    timings=[]
    for name,argv in [('seeds',[directory+'/seed',device_observations,151,8,512,8,4,16]),
                      ('tracks',[directory+'/tracker',device_observations,'--acceleration',250,'--seeds',directory+'/seeds.tsv'])]:
        result=remote('/mnt/glrtbench/native-adaptive/current/measure-run 90 '+
                      ' '.join(q(str(v)) for v in argv)+' > '+q(directory+'/'+name+'.tsv'))
        (args.output/(name+'.stderr')).write_text(result.stderr)
        output=remote('cat '+q(directory+'/'+name+'.tsv')).stdout
        (args.output/(name+'.tsv')).write_text(output)
        timings.append(next(json.loads(line) for line in result.stderr.splitlines()
                       if line.startswith('{') and json.loads(line).get('scope')=='whole_process'))
    obs=read_observations(observations)
    host=read_tracks(args.output/'host-tracks.tsv',obs);arm=read_tracks(args.output/'tracks.tsv',obs)
    def memberships(tracks):
        return [(t.lane,t.start_ns,t.end_ns,sorted((p.candidate,p.alias) for p in t.points)) for t in tracks.values]
    identical=memberships(host)==memberships(arm)
    receipt={'status':'complete' if identical else 'failed','observations':len(obs),
             'track_count':len(arm.values),'used_candidates':arm.used_count,'host_arm_memberships_exact':identical,
             'host_arm_bytes_exact':digest(args.output/'host-tracks.tsv')==digest(args.output/'tracks.tsv'),
             'input_sha256':digest(observations),'timings':timings,'combined_wall_s':sum(t['wall_s'] for t in timings),
             'binary_sha256':{str(p.relative_to(root)):digest(p) for p in [host_seed,host_tracker,arm_seed,arm_tracker]},
             'scope':'Native seed and tracking consume the on-device projection output; no IQ or observations fetched for runtime'}
    write_json(args.output/'receipt.json',receipt);print(json.dumps(receipt))
    if not identical:raise ValueError('host/ARM memberships differ')


if __name__=='__main__':main()
