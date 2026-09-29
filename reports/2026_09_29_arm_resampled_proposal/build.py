#!/usr/bin/env python3
"""Build the bounded periodic-linear power-of-two proposal experiment."""
import hashlib,json,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent; SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include'
ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def invoke(command):
    result=subprocess.run(command,text=True,capture_output=True,check=True)
    return {'command':command,'stdout':result.stdout,'stderr':result.stderr}
def build(target):
    out=ROOT/'builds'/target
    if out.exists():shutil.rmtree(out)
    shutil.copytree(SOURCE,out);arm=target=='arm';cc=ARM_CC if arm else 'gcc'
    flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math']
    if arm:flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_LAG_ARM_AFFINITY','-DLEO_PROPOSAL_NEON_FOLD',f'-I{ARM_INCLUDE}']
    records=[];binaries=[]
    for source,name in [('proposal_probe.c',f'proposal_probe_{target}'),('test_neon_fold.c',f'test_neon_fold_{target}'),('test_resampling.c',f'test_resampling_{target}')]:
        binary=out/name;command=[cc,*flags,str(out/source)]+([ARM_FFTW] if arm else ['-lfftw3f'])+['-lm','-o',str(binary)]
        records.append(invoke(command));binaries.append(binary)
    tests=[]
    if not arm:
        for binary in binaries[1:]:tests.append({'binary':binary.name,**invoke([str(binary)])})
    receipt={'schema':'arm-resampled-proposal-build/v1','target':target,
      'algorithm':{'fold_features':['lag1','lag3','lag5','power'],'resampling':'periodic-linear','fft_length':'next-power-of-two','peak_mapping':'round(k*original_length/fft_length)','minimum_peak_distance_original_samples':5},
      'implementation':'scalar host; NEON CI16 folding on ARM; stable radix rank both targets',
      'commands':records,'tests':tests,'binaries':{p.name:sha(p) for p in binaries},
      'sources':{p.name:sha(p) for p in sorted(out.glob('*.c'))}}
    receipt_path=out/'build-receipt.json';receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    return {'receipt':str(receipt_path.relative_to(ROOT)),'sha256':sha(receipt_path)}
def main():
    builds={target:build(target) for target in ('host','arm')}
    (ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-resampled-proposal-matrix/v1','builds':builds},indent=2)+'\n')
if __name__=='__main__':main()
