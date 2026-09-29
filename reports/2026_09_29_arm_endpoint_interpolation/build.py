"""Create immutable host or ARM endpoint-interpolation build snapshots."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
FROZEN=ROOT/'reports/2026_09_28_arm_boundary_fallback/builds/arm-v1'
CROSS=Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc')
FFTW_F=Path('/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a')

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()

def build(out:Path,arm:bool,sanitize:bool)->None:
    out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(FROZEN/'src',out/'src')
    for name in ('full_search.c','full_search.h','conditioned_czt.c','conditioned_czt.h','fft_full.c'):
        shutil.copy2(FROZEN/name,out/name)
    for name in ('endpoint.c','endpoint.h','endpoint_probe.c','test_endpoint.c'):
        shutil.copy2(HERE/name,out/name)
    cc=str(CROSS if arm else 'gcc')
    flags=['-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-Werror',
           '-fno-fast-math','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN',
           '-DLEO_FULL_REFINEMENT_MODE=2']
    if arm:flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize:
        if arm:raise ValueError('sanitizers are host-only')
        flags+=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    inc=['-I',str(out/'src/native_presence'),'-I',str(out)]
    libs=([str(FFTW_F),'-lfftw3'] if arm else ['-lfftw3','-lfftw3f'])+['-lm']
    commands=[]
    command=[cc,*flags,*inc,str(out/'full_search.c'),str(out/'conditioned_czt.c'),
             str(out/'endpoint.c'),str(out/'endpoint_probe.c'),str(out/'fft_full.c'),*libs,
             '-o',str(out/'endpoint_probe')]
    subprocess.run(command,check=True);commands.append(command)
    command=[cc,*flags,*inc,str(out/'endpoint.c'),str(out/'test_endpoint.c'),'-lm','-o',str(out/'test_endpoint')]
    subprocess.run(command,check=True);commands.append(command)
    if not arm:subprocess.run([str(out/'test_endpoint')],check=True)
    sources={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.suffix in ('.c','.h')}
    receipt={'schema':'arm-endpoint-interpolation-build/v1','arm':arm,'sanitize':sanitize,
      'frozen_boundary_source':str(FROZEN),'frozen_boundary_build_sha256':sha(FROZEN/'build.json'),
      'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],
      'commands':commands,'source_sha256':sources,
      'binary_sha256':{n:sha(out/n) for n in ('endpoint_probe','test_endpoint')}}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true');a=p.parse_args()
    build(a.output.resolve(),a.arm,a.sanitize)
