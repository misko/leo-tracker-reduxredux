#!/usr/bin/env python3
"""Build moment-screen host, sanitizer and ARM cross-build artifacts."""
from __future__ import annotations
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent; SOURCE=ROOT/'sources/conditioned-moments'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'; ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cmd(out,target,source,name):
 arm=target=='arm'; san=target=='sanitizer'
 x=[ARM_CC if arm else 'gcc','-DLEO_PRESENCE_FFTW=1','-std=c11','-O1' if san else '-O3','-Wall','-Wextra','-fno-fast-math','-flto','-fno-math-errno','-fno-trapping-math','-fcx-limited-range','-DLEO_PRESENCE_COARSE_FP32','-DLEO_FULL_CONDITIONED_SCREEN','-DLEO_FULL_REFINEMENT_MODE=2']
 if arm:x+=['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY']
 if san:x+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
 x+=['-I',str(out/'src/native_presence'),'-I',str(out),str(out/'conditioned_czt.c'),str(out/source),str(out/'fft_full.c')]
 x+=[ARM_FFTW,'-lfftw3','-lm'] if arm else ['-lfftw3f','-lfftw3','-lm']
 if san:x+=['-fsanitize=address,undefined']
 return x+['-o',str(out/name)]
def build(target):
 out=ROOT/'builds'/target
 if out.exists():shutil.rmtree(out)
 shutil.copytree(SOURCE,out); records=[]; bins=[]
 for source,name in [('cohort_probe.c','cohort_moments_'+target),('test_moments.c','test_moments_'+target),('test_direct_glrt.c','test_direct_glrt_'+target)]:
  if target=='sanitizer' and source=='cohort_probe.c':continue
  command=cmd(out,target,source,name); p=subprocess.run(command,text=True,capture_output=True,check=True);records.append({'command':command,'stdout':p.stdout,'stderr':p.stderr});bins.append(out/name)
  if target!='arm' and source!='cohort_probe.c':
   q=subprocess.run([str(out/name)],text=True,capture_output=True,check=True);records.append({'command':[str(out/name)],'stdout':q.stdout,'stderr':q.stderr})
 receipt={'schema':'arm-conditioned-moments-build/v1','target':target,'description':'32-sample fourth-order conditioned moment screen','scientific_semantics':'Finite-input approximate screen only. FP64 near-max rechecks and 16-frame final GLRT remain unchanged; no universal parity claim.','commands':records,'binaries':{p.name:sha(p) for p in bins},'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.suffix in ('.c','.h')}}
 (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'receipt_sha256':sha(out/'build-receipt.json')}
def main():
 records={x:build(x) for x in ('host','sanitizer','arm')};(ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-conditioned-moments-matrix/v1','source':str(SOURCE),'builds':records},indent=2)+'\n')
if __name__=='__main__':main()
