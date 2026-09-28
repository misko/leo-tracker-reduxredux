"""Build the isolated verification-fusion experiment from screen rotation V1."""
import argparse,hashlib,importlib.util,json,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
BUILDER=HERE.parent/'2026_09_28_arm_conditioned_czt/build.py'
BASELINE=Path('/var/tmp/leo-host-screen-rotation-v1')
ARM_FFTWF=Path('/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def build(output,arm=False,sanitize=False):
    spec=importlib.util.spec_from_file_location('frozen_czt_build',BUILDER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.HERE=HERE;module.BASELINE=BASELINE
    module.build(output,arm,sanitize)
    shutil.copyfile(HERE/'test_verify_fusion.c',output/'test_verify_fusion.c')
    receipt=json.loads((output/'build.json').read_text())
    cc=receipt['commands'][0][0]
    flags=['-DLEO_PRESENCE_FFTW=1','-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN']
    if arm:flags += ['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
    if sanitize:flags += ['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    libs=[str(ARM_FFTWF),'-lfftw3'] if arm else ['-lfftw3','-lfftw3f']
    cmd=[cc,*flags,'-I',str(output/'src/native_presence'),'-I',str(output),str(output/'test_verify_fusion.c'),str(output/'conditioned_czt.c'),str(output/'fft_full.c'),*libs,'-lm','-o',str(output/'test_verify_fusion')]
    subprocess.run(cmd,check=True)
    if not arm:subprocess.run([str(output/'test_verify_fusion')],check=True)
    receipt['schema']='arm-verify-fusion-build/v1';receipt['baseline_build']=str(BASELINE)
    receipt['baseline_receipt_sha256']=digest(BASELINE/'build.json')
    receipt['commands'].append(cmd)
    receipt['source_sha256']['test_verify_fusion.c']=digest(output/'test_verify_fusion.c')
    receipt['binary_sha256']['test_verify_fusion']=digest(output/'test_verify_fusion')
    receipt['precision']='Exact per-result FP64 ordering; shared phasor and odd-symbol received energy across verification scores'
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--arm',action='store_true');p.add_argument('--sanitize',action='store_true');a=p.parse_args()
    build(a.output.resolve(),a.arm,a.sanitize)
