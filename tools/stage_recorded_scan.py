"""Stage a complete verified recording on an idle PLUTO, then rehash every dwell."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

from run_arm_cadence import device_is_busy


def validated_files(directory, rows):
    if not 1 <= len(rows) <= 10000:
        raise ValueError('invalid visit inventory size')
    names = []
    for i, row in enumerate(rows):
        name = f'visit-{i:06d}.ci16'
        if row['visit'] != i or row['path'] != name or row['size_bytes'] != 2400000:
            raise ValueError('invalid visit inventory')
        path = directory/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != 2400000:
            raise ValueError('invalid full dwell file')
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['raw_sha256']:
            raise ValueError('local IQ hash differs')
        names.append(name)
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('iq', type=Path)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('remote')
    parser.add_argument('--reuse-device-iq')
    args = parser.parse_args()
    if not re.fullmatch(r'/mnt/glrtbench/three-scan-iq-v1/scan-fw-[0-9a-f]{16}',args.remote):
        raise ValueError('invalid staging directory')
    iq_remote = args.reuse_device_iq or args.remote
    if not re.fullmatch(r'/mnt/glrtbench/[A-Za-z0-9_/-]+',iq_remote):
        raise ValueError('invalid IQ directory')
    receipt = json.loads((args.iq/'receipt.json').read_text())
    rows = json.loads((args.iq/'inventory.json').read_text())
    if receipt.get('status') != 'complete' or receipt['visits'] != len(rows):
        raise ValueError('incomplete export')
    names = validated_files(args.iq, rows)
    manifest = (args.prepared/'manifest.tsv').read_text().splitlines()
    if len(manifest) != len(rows) or any(line.split('\t')[-1] != iq_remote+'/'+name for line,name in zip(manifest,names)):
        raise ValueError('prepared manifest points to different IQ')
    root = Path(__file__).resolve().parents[1]
    prefix = ['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options = ['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
               '-o','UserKnownHostsFile='+str(root/'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    ssh = prefix+['ssh',*options,'root@192.168.1.15']
    def remote(argv, timeout=60):
        return subprocess.run(ssh+[shlex.join(argv)],capture_output=True,check=True,timeout=timeout)
    ps = remote(['ps']).stdout.decode()
    if device_is_busy(ps):
        raise ValueError('device experiment is still active')
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'preflight-ps.txt').write_text(ps)
    disk = remote(['df','-Pk','/mnt/glrtbench']).stdout.decode()
    (args.output/'device-disk.txt').write_text(disk)
    if not args.reuse_device_iq:
        available = int(disk.splitlines()[-1].split()[3])*1024
        if available < len(rows)*2400000+1024**3:
            raise ValueError('insufficient device space with 1 GiB reserve')
    remote(['mkdir','-p','/mnt/glrtbench/three-scan-iq-v1'])
    remote(['mkdir',args.remote])
    if not args.reuse_device_iq:
        # Only validated numeric regular filenames enter this tar stream.
        with (args.output/'tar.stderr').open('xb') as error:
            producer = subprocess.Popen(['tar','-C',str(args.iq),'-cf','-',*names],stdout=subprocess.PIPE,stderr=error)
            try:
                result = subprocess.run(ssh+[shlex.join(['tar','-C',args.remote,'-xf','-'])],
                    stdin=producer.stdout,capture_output=True,timeout=900)
                producer.stdout.close()
                producer_code = producer.wait(timeout=30)
                result.check_returncode()
                if producer_code:
                    raise RuntimeError('local archive producer failed')
            finally:
                if producer.poll() is None:
                    producer.terminate();producer.wait(timeout=30)
    checksums = ''.join(f"{row['raw_sha256']}  {name}\n" for row,name in zip(rows,names))
    (args.output/'inputs.sha256').write_text(checksums)
    payloads = {}
    for name,path in [('inputs.sha256',args.output/'inputs.sha256'),
                      ('manifest.tsv',args.prepared/'manifest.tsv'),('authority.tsv',args.prepared/'authority.tsv')]:
        subprocess.run(prefix+['scp','-O',*options,str(path),'root@192.168.1.15:'+args.remote+'/'+name],check=True,timeout=60)
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        actual = remote(['sha256sum',args.remote+'/'+name]).stdout.decode().split()[0]
        if actual != expected:
            raise ValueError('staged metadata differs')
        payloads[args.remote+'/'+name] = expected
    checked = remote(['sh','-c','cd "$1" && sha256sum -c "$2"','verify',iq_remote,args.remote+'/inputs.sha256'],600).stdout
    if checked.decode().splitlines() != [name+': OK' for name in names]:
        raise ValueError('incomplete device verification')
    (args.output/'verification.log').write_bytes(checked)
    subprocess.run(prefix+['scp','-O',*options,str(args.output/'verification.log'),
                          'root@192.168.1.15:'+args.remote+'/verification.log'],check=True,timeout=60)
    payloads[args.remote+'/verification.log'] = hashlib.sha256(checked).hexdigest()
    result = {'status':'complete','session':receipt['session'],'capture_digest':receipt['capture_digest'],
              'visits':len(names),'bytes':len(names)*2400000,'iq_directory':iq_remote,
              'reused_device_iq':bool(args.reuse_device_iq),'payloads':payloads,
              'scope':'Full local and device IQ hashes checked before execution; no radio access'}
    (args.output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
