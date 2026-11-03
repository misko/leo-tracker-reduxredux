"""Stage, verify, run and retrieve one bounded PLUTO recorded-load experiment."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]


def layout(protocol):
    argv=protocol['controller_argv'];count=len(protocol['scans'])
    if not 2<=count<=4 or len(argv)!=5 or argv[2:]!=['300000','5000',str(protocol['memory_sample_ms'])]:
        raise ValueError('invalid fixed-cadence scope')
    if not 100<=protocol['memory_sample_ms']<=60000:raise ValueError('invalid memory interval')
    remote=str(Path(argv[0]).parent)
    if not re.fullmatch('/mnt/glrtbench/[A-Za-z0-9_-]+',remote) or argv[:2]!=[remote+'/controller',remote+'/plan.tsv']:
        raise ValueError('invalid diagnostic root')
    files=['controller','detector','plan.tsv',*[f'scan-{i}/chain.sh' for i in range(count)]]
    for name in files:
        sha=protocol['payloads'].get(remote+'/'+name,'')
        if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('missing pinned staged payload')
    return remote,count,files


def allowed_products(count):
    names=['observations.tsv','graph.tsv','detector.stdout','detector.stderr','downstream.stdout','downstream.stderr',
           *[f'results/{s}.{e}' for s in ['seeds','tracks','search'] for e in ['stdout','stderr']],
           'results/associations.json']
    return {f'scan-{i}/'+n for i in range(count) for n in names}


def save_products(data,directory,allowed):
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        members=archive.getmembers();seen=set()
        for member in members:
            if not member.isfile() or member.name not in allowed or member.name in seen:
                raise ValueError('unexpected product archive entry')
            seen.add(member.name)
        for member in members:
            target=directory/member.name;target.parent.mkdir(parents=True,exist_ok=True)
            with target.open('xb') as output:output.write(archive.extractfile(member).read())
    return sorted(seen)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('report',type=Path);args=parser.parse_args()
    report=args.report.resolve();protocol=json.loads((report/'protocol.json').read_text())
    remote,count,files=layout(protocol)
    for name in ['controller.stdout','controller.stderr','execution.json','verified-payloads.txt']:
        if (report/name).exists():raise ValueError('preserve existing execution')
    for name in files:
        if hashlib.sha256((report/name).read_bytes()).hexdigest()!=protocol['payloads'][remote+'/'+name]:
            raise ValueError('changed local payload: '+name)
    prefix=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
             '-o','UserKnownHostsFile='+str(ROOT/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    def ssh(argv,**kwargs):
        return subprocess.run(prefix+['ssh',*options,'root@192.168.1.15',shlex.join(argv)],**kwargs)
    processes=ssh(['ps'],check=True,capture_output=True,text=True,timeout=30).stdout
    if any('/measure-run ' in line or (remote+'/' in line) for line in processes.splitlines()):
        raise ValueError('device diagnostic still running')
    ssh(['mkdir',remote,*[remote+f'/scan-{i}' for i in range(count)]],check=True,timeout=30)
    for name in files:
        subprocess.run(prefix+['scp','-O',*options,str(report/name),'root@192.168.1.15:'+remote+'/'+name],check=True,timeout=60)
    ssh(['chmod','755',*[remote+'/'+name for name in files if name!='plan.tsv']],check=True,timeout=30)
    measure='/mnt/glrtbench/native-adaptive/current/measure-run'
    measured=ssh(['sha256sum',measure],capture_output=True,text=True,check=True,timeout=30).stdout.split()[0]
    if measure in protocol['payloads'] and protocol['payloads'][measure]!=measured:raise ValueError('measurement wrapper changed')
    protocol['payloads'][measure]=measured
    hashes=ssh(['sha256sum',*protocol['payloads']],capture_output=True,text=True,check=True,timeout=60).stdout
    for line in hashes.splitlines():
        sha,path=line.split()
        if protocol['payloads'][path]!=sha:raise ValueError('changed device payload: '+path)
    (report/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    (report/'verified-payloads.txt').write_text(hashes)
    receipt={'protocol_sha256':hashlib.sha256((report/'protocol.json').read_bytes()).hexdigest()}
    print('Payloads verified; starting fixed-cadence controller',flush=True)
    try:
        with (report/'controller.stdout').open('x') as out,(report/'controller.stderr').open('x') as err:
            result=ssh(protocol['controller_argv'],stdout=out,stderr=err,timeout=(count+2)*300+50)
        receipt['exit_code']=result.returncode
    except subprocess.TimeoutExpired:
        receipt.update(exit_code=None,error='SSH observation timed out; inspect remote processes before any restart')
        (report/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
        raise
    (report/'execution.json').write_text(json.dumps(receipt,indent=2)+'\n')
    processes=ssh(['ps'],check=True,capture_output=True,text=True,timeout=30).stdout
    (report/'terminal-device-processes.txt').write_text(processes)
    if any(remote+'/' in line for line in processes.splitlines()):raise ValueError('remote processes remain active; do not restart')
    if result.returncode not in (0,2):raise ValueError('unconfirmed controller termination; inspect SSH receipt')
    paths=ssh(['find',remote,'-type','f'],check=True,capture_output=True,text=True,timeout=30).stdout.splitlines()
    allowed=allowed_products(count)
    selected=[p[len(remote)+1:] for p in paths if p.startswith(remote+'/') and p[len(remote)+1:] in allowed]
    if not selected:raise ValueError('no products to retrieve')
    data=ssh(['tar','-C',remote,'-cf','-',*selected],check=True,capture_output=True,timeout=90).stdout
    products=save_products(data,report,allowed)
    (report/'retrieved-products.json').write_text(json.dumps(products,indent=2)+'\n')
    print(json.dumps({'controller_exit':result.returncode,'products_retrieved':len(products)}),flush=True)
    if result.returncode:raise SystemExit(result.returncode)


if __name__=='__main__':main()
