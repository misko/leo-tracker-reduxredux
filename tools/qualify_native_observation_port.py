"""Physical ARM projection qualification from a fresh recorded-IQ checkpoint."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from compare_observation_checkpoints import compare
from leo.native_pipeline.runner import digest,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=Path);p.add_argument('--binary',required=True,type=Path)
    p.add_argument('output',type=Path);args=p.parse_args()
    root=Path(__file__).resolve().parents[1];q=shlex.quote
    auth=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(root/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    ssh=auth+['ssh']+options+['root@192.168.1.15']
    def command(text):return subprocess.run(ssh+[text],capture_output=True,text=True,check=True,timeout=90)
    if '/modular-ds9-iq-v1/leo-recorded-paced' in command('ps').stdout:
        raise ValueError('paced detector measurement is still running')
    if not args.output.name.replace('-','').isalnum():raise ValueError('invalid diagnostic name')
    args.output.mkdir(parents=True,exist_ok=False);remote='/mnt/glrtbench/'+args.output.name
    command('mkdir '+q(remote))
    files={'project':args.binary,'input.tsv':args.input/'input.tsv'}
    for name,path in files.items():
        subprocess.run(auth+['scp','-O']+options+[str(path),'root@192.168.1.15:'+remote+'/'+name],
                       check=True,capture_output=True,text=True,timeout=90)
        if command('sha256sum '+q(remote+'/'+name)).stdout.split()[0]!=digest(path):
            raise ValueError('projection payload hash differs')
    command('chmod 755 '+q(remote+'/project'))
    result=command('/mnt/glrtbench/native-adaptive/current/measure-run 60 '+q(remote+'/project')+
                   ' --checkpoint < '+q(remote+'/input.tsv'))
    (args.output/'observations.tsv').write_text(result.stdout)
    (args.output/'stderr').write_text(result.stderr)
    (args.output/'candidate-map.tsv').write_bytes((args.input/'candidate-map.tsv').read_bytes())
    comparison=compare(args.output,args.input)
    timing=next(json.loads(line) for line in result.stderr.splitlines()
                if line.startswith('{') and json.loads(line).get('scope')=='whole_process')
    receipt={'comparison':comparison,'timing':timing,'payload_sha256':{n:digest(p) for n,p in files.items()},
             'output_sha256':digest(args.output/'observations.tsv'),
             'scope':'Actual ARM native projection; source map is evaluation metadata from the same run'}
    write_json(args.output/'receipt.json',receipt);print(json.dumps(receipt))
    if not comparison['all_scientific_observations_exact']:raise ValueError('ARM projection differs')


if __name__=='__main__':main()
