"""Two bounded ARM diagnostic workloads; scientific evaluation is separate."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import time

from leo.native_pipeline.runner import digest, finite_json, write_json


def diagnostic_path(value):
    p=PurePosixPath(value)
    if not p.is_absolute() or '..' in p.parts or not str(p).startswith('/mnt/glrtbench/'):
        raise ValueError('invalid diagnostic path')


def validate(protocol):
    if set(protocol['jobs'])!={'detector','search'}:
        raise ValueError('two explicit workloads required')
    for path,sha in protocol['payloads'].items():
        diagnostic_path(path)
        if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('invalid payload digest')
    for job in protocol['jobs'].values():
        if type(job['timeout_s']) is not int or not 1<=job['timeout_s']<=600:
            raise ValueError('invalid workload timeout')
        if type(job['nice']) is not int or not 0<=job['nice']<=19:
            raise ValueError('invalid workload priority')
        mask=job.get('cpu_mask')
        if mask is not None and (type(mask) is not int or not 1<=mask<=3):
            raise ValueError('invalid two-core affinity mask')
        if mask is not None and job.get('affinity_launcher') not in protocol['payloads']:
            raise ValueError('affinity launcher must be pinned')
        argv=job['argv']
        if not argv or not all(isinstance(v,str) and v and '\x00' not in v for v in argv):
            raise ValueError('invalid workload argv')
        if argv[0] not in protocol['payloads']:
            raise ValueError('workload executable must be pinned')
    if set(protocol['downloads'])!={'observations','graph'}:
        raise ValueError('explicit projection products required')
    for path in protocol['downloads'].values():diagnostic_path(path)


def concurrent_results(jobs,run):
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending={name:pool.submit(run,name) for name in jobs}
        return {name:future.result() for name,future in pending.items()}


def workload_argv(job):
    argv=['/mnt/glrtbench/native-adaptive/current/measure-run',str(job['timeout_s']),
          'nice','-n',str(job['nice'])]
    if job.get('cpu_mask') is not None:
        argv+=[job['affinity_launcher'],str(job['cpu_mask'])]
    return argv+job['argv']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path);args=parser.parse_args()
    report=args.report.resolve();protocol=finite_json(report/'protocol.json');validate(protocol)
    if any((report/(name+suffix)).exists() for name in protocol['jobs'] for suffix in ('.stdout','.stderr')):
        raise ValueError('preserve prior execution')
    root=Path(__file__).resolve().parents[1]
    ssh=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password',
         'ssh','-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
         '-o','UserKnownHostsFile='+str(root/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts'),
         'root@192.168.1.15']
    def command(argv,**kwargs):
        return subprocess.run(ssh+[' '.join(map(shlex.quote,argv))],**kwargs)
    processes=command(['ps'],capture_output=True,text=True,check=True,timeout=30).stdout
    if any('/measure-run ' in line or '/modular-ds9-iq-v1/leo-recorded-' in line for line in processes.splitlines()):
        raise ValueError('another device measurement is active')
    for path,sha in protocol['payloads'].items():
        actual=command(['sha256sum',path],capture_output=True,text=True,check=True,timeout=30).stdout.split()[0]
        if actual!=sha:raise ValueError('changed device payload: '+path)
    for job in protocol['jobs'].values():
        if job.get('cpu_mask') is not None:
            command([job['affinity_launcher'],str(job['cpu_mask']),'/bin/true'],
                    check=True,timeout=30)
    # Refuse overwrite before either workload starts.
    for path in protocol['downloads'].values():
        if command(['test','-e',path],timeout=30).returncode!=1:
            raise ValueError('output exists or device check failed')
    origin=time.monotonic()
    def run(name):
        job=protocol['jobs'][name]
        argv=workload_argv(job)
        receipt={'argv':argv,'launch_offset_s':time.monotonic()-origin}
        with (report/(name+'.stdout')).open('x') as out,(report/(name+'.stderr')).open('x') as err:
            try:
                result=command(argv,stdout=out,stderr=err,timeout=job['timeout_s']+45)
                receipt['exit_code']=result.returncode
            except subprocess.TimeoutExpired:
                receipt.update(exit_code=None,error='SSH observation timeout; inspect remote process before any restart')
        receipt['finish_offset_s']=time.monotonic()-origin
        return receipt
    results=concurrent_results(protocol['jobs'],run)
    write_json(report/'execution.json',{'protocol_sha256':digest(report/'protocol.json'),'jobs':results,
        'scope':protocol.get('scope','Concurrent recorded GLRT and previous-scan regional-search contention experiment; excludes remaining stages and sustained cadence')})
    if results['detector'].get('exit_code') in (0,3):
        for name,path in protocol['downloads'].items():
            with (report/(name+'.tsv')).open('x') as out:
                command(['cat',path],stdout=out,check=True,timeout=90)
    print(results)


if __name__=='__main__':main()
