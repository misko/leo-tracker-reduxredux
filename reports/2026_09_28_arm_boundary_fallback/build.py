"""Build the bounded boundary-conditioned fallback experiment."""
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASELINE=Path('/var/tmp/leo-host-fine-direct-glrt-v1')
CROSS=Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc')
ARM_FFTWF=Path('/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a')
SOURCES=('full_search.c','full_search.h','probe_main.c','cohort_probe.c',
         'conditioned_czt.c','conditioned_czt.h','fft_full.c','test_direct_glrt.c')

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def run(command,commands):
    subprocess.run(command,check=True); commands.append([str(x) for x in command])

def build(output,arm=False,sanitize=False):
    if arm and sanitize: raise ValueError('sanitizers are host-only')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(BASELINE/'src',output/'src')
    for name in SOURCES: shutil.copyfile(HERE/name,output/name)
    cc=str(CROSS) if arm else 'gcc'
    flags=['-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-Werror',
           '-fno-fast-math','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN',
           '-DLEO_FULL_REFINEMENT_MODE=2']
    if arm: flags += ['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize: flags += ['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    inc=['-I',str(output/'src/native_presence'),'-I',str(output)]
    libs=[str(ARM_FFTWF),'-lfftw3'] if arm else ['-lfftw3','-lfftw3f']
    commands=[]
    def program(source,target):
        run([cc,*flags,*inc,str(output/'full_search.c'),str(output/'conditioned_czt.c'),
             str(output/source),str(output/'fft_full.c'),*libs,'-lm','-o',str(output/target)],commands)
    program('probe_main.c','probe_boundary')
    program('cohort_probe.c','cohort_boundary')
    run([cc,*flags,*inc,str(output/'test_direct_glrt.c'),str(output/'conditioned_czt.c'),
         str(output/'fft_full.c'),*libs,'-lm','-o',str(output/'test_boundary')],commands)
    if not arm: subprocess.run([str(output/'test_boundary')],check=True)
    source_sha={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.suffix in {'.c','.h'}}
    binaries={n:digest(output/n) for n in ('probe_boundary','cohort_boundary','test_boundary')}
    receipt={'schema':'arm-boundary-fallback-build/v1','arm':arm,'sanitize':sanitize,
      'baseline_build':str(BASELINE),'baseline_receipt_sha256':digest(BASELINE/'build.json'),
      'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],
      'commands':commands,'source_sha256':source_sha,'binary_sha256':binaries,
      'mode':'fine-direct with exact residual-boundary conditioned fallback'}
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true')
    a=p.parse_args();build(a.output.resolve(),a.arm,a.sanitize)
