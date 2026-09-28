"""Build one source-receipted sparse coarse-proposal budget."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASELINE=Path('/var/tmp/leo-host-verify-fusion-v1')
CROSS=Path('/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc')
ARM_FFTWF=Path('/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,commands):subprocess.run(cmd,check=True);commands.append([str(x) for x in cmd])

def build(out,frames,symbols,centers=32,arm=False,sanitize=False):
    if (frames,symbols) not in {(1,3),(2,6),(4,12),(8,12),(16,12)}:raise ValueError('supported budgets: 1/3, 2/6, 4/12, 8/12, 16/12')
    if centers<1:raise ValueError('centers must be positive')
    if arm and sanitize:raise ValueError('sanitizers are host-only')
    out.mkdir(parents=True,exist_ok=False);shutil.copytree(BASELINE/'src',out/'src')
    names=('full_search.c','full_search.h','probe_main.c','cohort_probe.c','conditioned_czt.c','conditioned_czt.h','fft_full.c','test_conditioned_czt.c','test_conditioned_integration.c','test_verify_fusion.c','test_sparse_proposal.c')
    for n in names:shutil.copyfile(HERE/n,out/n)
    cc=str(CROSS) if arm else 'gcc'
    flags=['-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN',f'-DLEO_SPARSE_COARSE_FRAMES={frames}',f'-DLEO_SPARSE_COARSE_SYMBOLS={symbols}',f'-DLEO_SPARSE_CENTERS={centers}']
    if arm:flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize:flags+=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    inc=['-I',str(out/'src/native_presence'),'-I',str(out)];libs=[str(ARM_FFTWF),'-lfftw3'] if arm else ['-lfftw3','-lfftw3f'];commands=[]
    common=[cc,*flags,*inc,str(out/'full_search.c'),str(out/'conditioned_czt.c')]
    for main,target in (('probe_main.c','probe'),('cohort_probe.c','cohort')):
        run([*common,str(out/main),str(out/'fft_full.c'),*libs,'-lm','-o',str(out/target)],commands)
    unit_float=[str(ARM_FFTWF)] if arm else ['-lfftw3f']
    run([cc,*flags,'-I',str(out),str(out/'test_conditioned_czt.c'),str(out/'conditioned_czt.c'),*unit_float,'-lm','-o',str(out/'test_conditioned_czt')],commands)
    for main,target in (('test_conditioned_integration.c','test_conditioned_integration'),('test_verify_fusion.c','test_verify_fusion'),('test_sparse_proposal.c','test_sparse_proposal')):
        run([cc,*flags,*inc,str(out/main),str(out/'conditioned_czt.c'),str(out/'fft_full.c'),*libs,'-lm','-o',str(out/target)],commands)
    if not arm:
        for n in ('test_conditioned_czt','test_conditioned_integration','test_verify_fusion','test_sparse_proposal'):subprocess.run([str(out/n)],check=True)
    sources={str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.suffix in {'.c','.h'}}
    binaries={n:digest(out/n) for n in ('probe','cohort','test_conditioned_czt','test_conditioned_integration','test_verify_fusion','test_sparse_proposal')}
    receipt={'schema':'arm-sparse-coarse-proposal-build/v1','arm':arm,'sanitize':sanitize,'baseline_build':str(BASELINE),'baseline_receipt_sha256':digest(BASELINE/'build.json'),'budget':{'frames':frames,'symbols':symbols,'centers':centers,'repair_radius':2},'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'commands':commands,'source_sha256':sources,'binary_sha256':binaries,'precision':'Sparse proposal only; retained candidates use original full coarse_fp32_cell repair and unchanged downstream scoring'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--frames',required=True,type=int);p.add_argument('--symbols',required=True,type=int);p.add_argument('--centers',type=int,default=32);p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true');a=p.parse_args();build(a.output.resolve(),a.frames,a.symbols,a.centers,a.arm,a.sanitize)
