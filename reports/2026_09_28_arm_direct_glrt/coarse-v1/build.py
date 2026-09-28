"""Build the bounded direct-coarse-CFO GLRT experiment."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASELINE=Path('/var/tmp/leo-host-verify-fusion-v1')
CROSS=Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc')
ARM_FFTWF=Path('/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a')
SOURCES=('full_search.c','full_search.h','probe_main.c','cohort_probe.c',
         'conditioned_czt.c','conditioned_czt.h','fft_full.c','test_direct_glrt.c')

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def run(command,commands):
    subprocess.run(command,check=True)
    commands.append([str(value) for value in command])

def build(output,arm=False,sanitize=False):
    if arm and sanitize: raise ValueError('sanitizers are host-only')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(BASELINE/'src',output/'src')
    for name in SOURCES: shutil.copyfile(HERE/name,output/name)
    cc=str(CROSS) if arm else 'gcc'
    flags=['-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-Werror',
           '-fno-fast-math','-DLEO_PRESENCE_COARSE_FP32',
           '-DLEO_FULL_CONDITIONED_SCREEN']
    if arm: flags += ['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize: flags += ['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    inc=['-I',str(output/'src/native_presence'),'-I',str(output)]
    libs=[str(ARM_FFTWF),'-lfftw3'] if arm else ['-lfftw3','-lfftw3f']
    commands=[]
    def program(name,macro,target):
        run([cc,*flags,f'-DLEO_FULL_DIRECT_GLRT={macro}',*inc,
             str(output/'full_search.c'),str(output/'conditioned_czt.c'),str(output/name),
             str(output/'fft_full.c'),*libs,'-lm','-o',str(output/target)],commands)
    program('probe_main.c',1,'probe_direct')
    program('cohort_probe.c',1,'cohort_direct')
    program('probe_main.c',0,'probe_control')
    program('cohort_probe.c',0,'cohort_control')
    run([cc,*flags,'-DLEO_FULL_DIRECT_GLRT=1',*inc,str(output/'test_direct_glrt.c'),
         str(output/'conditioned_czt.c'),str(output/'fft_full.c'),*libs,'-lm','-o',
         str(output/'test_direct_glrt')],commands)
    if not arm: subprocess.run([str(output/'test_direct_glrt')],check=True)
    source_sha={str(path.relative_to(output)):digest(path) for path in sorted(output.rglob('*'))
                if path.suffix in {'.c','.h'}}
    binaries={name:digest(output/name) for name in ('probe_direct','cohort_direct',
              'probe_control','cohort_control','test_direct_glrt')}
    receipt={'schema':'arm-direct-coarse-cfo-glrt-build/v1','arm':arm,'sanitize':sanitize,
      'baseline_build':str(BASELINE),'baseline_receipt_sha256':digest(BASELINE/'build.json'),
      'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],
      'commands':commands,'source_sha256':source_sha,'binary_sha256':binaries,
      'mode':{'direct':'LEO_FULL_DIRECT_GLRT=1: full coarse then GLRT at coarse CFO; refinement fields are explicitly skipped','control':'LEO_FULL_DIRECT_GLRT=0: original refinement path'},
      'precision':'Approximate CFO conditioning; direct GLRT result is exact for its coarse-CFO call'}
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--arm',action='store_true')
    parser.add_argument('--sanitize',action='store_true')
    args=parser.parse_args();build(args.output.resolve(),args.arm,args.sanitize)
