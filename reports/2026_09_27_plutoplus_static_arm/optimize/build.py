"""Isolated optimization builds; existing scientific snapshots stay immutable."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
BASE=Path('/tmp/leo-static-arm15-20260927-v3')


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build(name, root=None, extra=(), host=False, sanitize=False):
    root=Path(root) if root else HERE/'work'/name
    if not root.exists():
        root.mkdir(parents=True)
        shutil.copytree(BASE/'src',root/'src')
    config=json.loads((BASE/'arm/build.json').read_text())
    command=config['methods']['D']['command'][:]
    command=[x.replace(str(BASE/'src'),str(root/'src')) for x in command]
    output=root/('host-asan' if sanitize else 'host' if host else 'arm')
    command[-1]=str(output)
    command[command.index('-DPROBE_METHOD="D"')]='-DPROBE_METHOD="'+name+'"'
    if host:
        command[0]='gcc'
        command=[x for x in command if not x.startswith(('--sysroot=','-mcpu=','-mfpu=','-mfloat-abi='))]
        archive='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
        command[command.index(archive)]='-lfftw3f'
    command[1:1]=list(extra)
    if sanitize: command[1:1]=['-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie']
    run=subprocess.run(command,capture_output=True,text=True,timeout=120)
    (root/(output.name+'.build.stderr')).write_text(run.stderr)
    if run.returncode: raise RuntimeError(run.stderr)
    (root/(output.name+'.build.json')).write_text(json.dumps({'command':command,'binary_sha256':sha(output),
        'sources':{str(p.relative_to(root)):sha(p) for p in sorted((root/'src').rglob('*')) if p.is_file()},
        'baseline_build_sha256':sha(BASE/'arm/build.json')},indent=2)+'\n')
    print(output,flush=True)
    return root


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--root',type=Path)
    p.add_argument('--unroll',action='store_true');p.add_argument('--host',action='store_true');p.add_argument('--sanitize',action='store_true')
    a=p.parse_args()
    # Append override after inherited flags; compiler option order is significant.
    extra=[]
    root=build(a.name,a.root,extra,a.host or a.sanitize,a.sanitize)
    if a.unroll:
        receipt=json.loads((root/'arm.build.json').read_text());cmd=receipt['command'];cmd[-2:-2]=['-funroll-loops','-fpeel-loops']
        run=subprocess.run(cmd,capture_output=True,text=True,timeout=120);run.check_returncode()
        receipt['command']=cmd;receipt['binary_sha256']=sha(root/'arm');(root/'arm.build.json').write_text(json.dumps(receipt,indent=2)+'\n')
