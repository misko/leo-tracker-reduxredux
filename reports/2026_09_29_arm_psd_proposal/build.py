"""Build the masked CFO prototype from archived boundary-fallback sources."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_28_arm_boundary_fallback/builds/host-cohort-v1'
CROSS=Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def build(output,arm=False,sanitize=False):
    if arm and sanitize:raise ValueError('Host sanitizers only')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(BASE/'src',output/'src')
    for name in ('conditioned_czt.c','conditioned_czt.h','fft_full.c'):
        shutil.copyfile(BASE/name,output/name)
    for name in ('full_search.c','full_search.h','cohort_probe.c','test_mask.c','presence.c','coarse_fp32.h'):
        shutil.copyfile(HERE/name,output/name)
    shutil.copyfile(HERE/'coarse_fp32.h',output/'src/native_presence/coarse_fp32.h')
    flags=['-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-Werror',
           '-fno-fast-math','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN',
           '-DLEO_FULL_REFINEMENT_MODE=2']
    if arm:flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize:flags+=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    cc=str(CROSS) if arm else 'gcc'
    inc=['-I',str(output/'src/native_presence'),'-I',str(output)]
    libs=['/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a','-lfftw3'] if arm else ['-lfftw3','-lfftw3f']
    commands=[]
    for files,target in [(('full_search.c','cohort_probe.c'),'cohort_mask'),(('test_mask.c',),'test_mask')]:
        command=[cc,*flags,*inc,*[str(output/f) for f in files],str(output/'conditioned_czt.c'),str(output/'fft_full.c'),*libs,'-lm','-o',str(output/target)]
        subprocess.run(command,check=True);commands.append(command)
    if not arm:subprocess.run([str(output/'test_mask')],check=True)
    receipt=dict(schema='psd-masked-coarse-build/v1',arm=arm,sanitize=sanitize,
        baseline_receipt_sha256=sha(BASE/'build.json'),commands=commands,
        source_sha256={str(p.relative_to(output)):sha(p) for p in sorted(output.rglob('*')) if p.suffix in ('.c','.h')},
        binary_sha256={n:sha(output/n) for n in ('cohort_mask','test_mask')})
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true')
    a=p.parse_args();build(a.output.resolve(),a.arm,a.sanitize)
