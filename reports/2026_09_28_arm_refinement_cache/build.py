"""Build source-receipted per-window refinement-cache binaries."""
import argparse,hashlib,importlib.util,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
BUILDER=HERE.parent/'2026_09_28_arm_verify_fusion/build.py'
BASELINE=Path('/var/tmp/leo-host-verify-fusion-v1')
ARM_FFTWF=Path('/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build(out,arm=False,sanitize=False):
    spec=importlib.util.spec_from_file_location('verify_builder',BUILDER);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.HERE=HERE;m.BASELINE=BASELINE;m.build(out,arm,sanitize)
    shutil.copyfile(HERE/'test_refinement_cache.c',out/'test_refinement_cache.c')
    receipt=json.loads((out/'build.json').read_text());cc=receipt['commands'][0][0]
    flags=['-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN']
    if arm:flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize:flags+=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    libs=[str(ARM_FFTWF),'-lfftw3'] if arm else ['-lfftw3','-lfftw3f']
    cmd=[cc,*flags,'-I',str(out/'src/native_presence'),'-I',str(out),str(out/'test_refinement_cache.c'),str(out/'conditioned_czt.c'),str(out/'fft_full.c'),*libs,'-lm','-o',str(out/'test_refinement_cache')]
    subprocess.run(cmd,check=True)
    if not arm:subprocess.run([str(out/'test_refinement_cache')],check=True)
    receipt['schema']='arm-refinement-cache-build/v1';receipt['baseline_build']=str(BASELINE);receipt['baseline_receipt_sha256']=digest(BASELINE/'build.json');receipt['commands'].append(cmd)
    receipt['source_sha256']['test_refinement_cache.c']=digest(out/'test_refinement_cache.c');receipt['binary_sha256']['test_refinement_cache']=digest(out/'test_refinement_cache')
    receipt['precision']='Per-run eight-entry caches with bitwise exact keys; scalar result copies only; unchanged candidate inventory and downstream ordering'
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true');a=p.parse_args();build(a.output.resolve(),a.arm,a.sanitize)
