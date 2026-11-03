"""Run pinned ARM-local regional search and full scoring of its selected site.

Protocol is persisted before execution. This is recorded-data qualification;
it neither collects RF nor changes production services.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess

from leo.native_pipeline.runner import digest, finite_json, write_json


def measurement_active(processes):
    return any('/modular-ds9-iq-v1/leo-recorded-' in line or '/measure-run ' in line
               for line in processes.splitlines())


def validate(protocol):
    for key in ('search_binary','score_binary','input'):
        item=protocol[key]
        path=PurePosixPath(item['device_path'])
        if not path.is_absolute() or '..' in path.parts or not str(path).startswith('/mnt/glrtbench/'):
            raise ValueError('invalid diagnostic device path')
        if len(item['sha256'])!=64 or any(c not in '0123456789abcdef' for c in item['sha256']):
            raise ValueError('invalid payload hash')
    if protocol['workers'] not in (1,2) or not 1<=protocol['timeout_s']<=600:
        raise ValueError('invalid execution budget')
    prior=protocol['prior']
    import math
    if len(prior)!=3 or not all(math.isfinite(v) for v in prior) or not (
        -90<=prior[0]<=90 and -180<=prior[1]<=180 and 0<prior[2]<=20000):
        raise ValueError('invalid prior')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args=parser.parse_args();report=args.report.resolve()
    protocol=finite_json(report/'protocol.json');validate(protocol)
    if any((report/name).exists() for name in ('search.json','execution.json','progress.jsonl')):
        raise ValueError('preserve existing execution evidence')
    root=Path(__file__).resolve().parents[1]
    ssh=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password',
         'ssh','-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
         '-o','UserKnownHostsFile='+str(root/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts'),
         'root@192.168.1.15']
    def remote(argv,**kwargs):
        return subprocess.run(ssh+[' '.join(shlex.quote(str(v)) for v in argv)],**kwargs)
    for key in ('search_binary','score_binary','input'):
        item=protocol[key]
        actual=remote(['sha256sum',item['device_path']],check=True,capture_output=True,text=True,timeout=30)
        if actual.stdout.split()[0]!=item['sha256']:raise ValueError('device payload differs: '+key)
    processes=remote(['ps'],check=True,capture_output=True,text=True,timeout=30).stdout
    if measurement_active(processes):
        raise ValueError('another device measurement is active')
    measure='/mnt/glrtbench/native-adaptive/current/measure-run'
    argv=[measure,protocol['timeout_s'],protocol['search_binary']['device_path'],
          'search',protocol['input']['device_path'],*protocol['prior'],protocol['workers']]
    with (report/'search.json').open('x') as out,(report/'progress.jsonl').open('x') as err:
        result=remote(argv,stdout=out,stderr=err,timeout=protocol['timeout_s']+30)
    execution={'exit_code':result.returncode,'argv':argv,'protocol_sha256':digest(report/'protocol.json'),
               'search_sha256':digest(report/'search.json'),'progress_sha256':digest(report/'progress.jsonl')}
    write_json(report/'execution.json',execution)
    if result.returncode!=0:
        print(json.dumps(execution));return
    search=finite_json(report/'search.json')
    if search['evaluated_points']!=400 or len(search['evaluations'])!=400:
        raise ValueError('incomplete point inventory')
    selected=search['selected']
    argv=[measure,90,protocol['score_binary']['device_path'],'score-at',protocol['input']['device_path'],
          *protocol['prior'][:2],selected['east_km'],selected['north_km'],protocol['workers']]
    result=remote(argv,capture_output=True,text=True,timeout=120)
    (report/'selected-score.json').write_text(result.stdout)
    (report/'selected-score.stderr').write_text(result.stderr)
    write_json(report/'selected-execution.json',{'exit_code':result.returncode,'argv':argv,
        'score_sha256':digest(report/'selected-score.json'),'search_sha256':execution['search_sha256']})
    if result.returncode:raise ValueError('selected-site scoring failed')
    if json.loads(result.stdout)['points'][0]['score_hz']!=selected['score_hz']:
        raise ValueError('full association score differs from search objective')
    print('400-point ARM search and selected-site full score complete; compare independently and assess throughput')


if __name__=='__main__':main()
