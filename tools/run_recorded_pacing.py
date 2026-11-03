"""Run a predeclared full-scan detector replay after local device IQ verification."""
import argparse
from pathlib import Path
import shlex
import subprocess

from leo.native_pipeline.runner import digest,finite_json,write_json


def execution_flags(protocol):
    flags=[]
    for key,flag in [('probe_prefix_only','--probe-prefix'),('iq_reuse','--reuse-iq')]:
        value=protocol.get(key,False)
        if not isinstance(value,bool):raise ValueError('invalid boolean execution option: '+key)
        if value:flags.append(flag)
    return flags


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report',type=Path)
    args=p.parse_args();report=args.report.resolve();protocol=finite_json(report/'protocol.json')
    if (report/'output.jsonl').exists():raise ValueError('output already exists; preserve prior run')
    root=Path(__file__).resolve().parents[1]
    auth=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(root/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    ssh=auth+['ssh']+options+['root@192.168.1.15']
    remote=protocol['device_iq_directory'];q=shlex.quote
    binary_name=protocol.get('device_binary_name','leo-recorded-paced-arm')
    if Path(binary_name).name!=binary_name:raise ValueError('invalid device binary name')
    manifest_name=protocol.get('device_manifest_name','manifest.tsv')
    if Path(manifest_name).name!=manifest_name:raise ValueError('invalid device manifest name')
    def command(text):return subprocess.run(ssh+[text],check=True,capture_output=True,text=True,timeout=30).stdout
    verified=command('cat '+q(remote+'/verification.log')).splitlines()
    expected=[f'visit-{i:06d}.ci16: OK' for i in range(protocol['visits'])]
    if verified!=expected:raise ValueError('full device IQ verification is incomplete or failed')
    (report/'iq-verification.log').write_text('\n'.join(verified)+'\n')
    for path,expected_digest in [(remote+'/'+binary_name,protocol['binary_sha256']),
                                  (remote+'/'+manifest_name,protocol['manifest_sha256'])]:
        if command('sha256sum '+q(path)).split()[0]!=expected_digest:raise ValueError('device payload differs')
    if digest(report/'manifest.tsv')!=protocol['manifest_sha256']:raise ValueError('local manifest changed')
    panel=finite_json(root/'reports/2026_09_30_arm_ds9_native_comparison/panel.json')
    template_hashes={f'{edge}-{role}.c128':item['sha256']
                     for edge,roles in panel['templates'].items() for role,item in roles.items()}
    templates={path for line in (report/'manifest.tsv').read_text().splitlines()
               for path in line.split('\t')[2:4]}
    for path in templates:
        if command('sha256sum '+q(path)).split()[0]!=template_hashes[Path(path).name]:
            raise ValueError('device template differs')
    argv=['/mnt/glrtbench/native-adaptive/current/measure-run',str(protocol['timeout_s']),
          remote+'/'+binary_name,remote+'/'+manifest_name,str(protocol['queue_capacity'])]
    argv+=execution_flags(protocol)
    projection=protocol.get('projection')
    if projection:
        for key in ['authority_name','observations_name']:
            if Path(projection[key]).name!=projection[key]:raise ValueError('invalid projection path')
        authority=remote+'/'+projection['authority_name']
        if command('sha256sum '+q(authority)).split()[0]!=projection['authority_sha256']:
            raise ValueError('projection authority differs')
        argv+=['--authority',authority,'--observations',remote+'/'+projection['observations_name']]
        if projection.get('graph_name'):
            if Path(projection['graph_name']).name!=projection['graph_name']:raise ValueError('invalid graph path')
            argv+=['--graph',remote+'/'+projection['graph_name'],'--session',projection['session_id']]
    with (report/'output.jsonl').open('x') as out,(report/'stderr').open('x') as error:
        result=subprocess.run(ssh+[' '.join(map(q,argv))],stdout=out,stderr=error,
                              timeout=protocol['timeout_s']+30)
    receipt={'exit_code':result.returncode,'argv':argv,'protocol_sha256':digest(report/'protocol.json'),
             'output_sha256':digest(report/'output.jsonl'),
             'scope':'Execution receipt; evaluate science, pacing and drop accounting separately'}
    if projection and result.returncode in (0,3):
        source=remote+'/'+projection['observations_name']
        with (report/'observations.tsv').open('x') as out:
            subprocess.run(ssh+['cat '+q(source)],stdout=out,check=True,text=True,timeout=90)
        receipt['observations_sha256']=digest(report/'observations.tsv')
        if command('sha256sum '+q(source)).split()[0]!=receipt['observations_sha256']:
            raise ValueError('downloaded observations differ')
        if projection.get('graph_name'):
            source=remote+'/'+projection['graph_name']
            with (report/'graph.tsv').open('x') as out:
                subprocess.run(ssh+['cat '+q(source)],stdout=out,check=True,text=True,timeout=90)
            receipt['graph_sha256']=digest(report/'graph.tsv')
            if command('sha256sum '+q(source)).split()[0]!=receipt['graph_sha256']:
                raise ValueError('downloaded graph differs')
    write_json(report/'execution.json',receipt);print(receipt)


if __name__=='__main__':main()
