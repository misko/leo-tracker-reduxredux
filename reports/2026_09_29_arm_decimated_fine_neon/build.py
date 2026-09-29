#!/usr/bin/env python3
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT/'sources'
ARM_CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc';ARM_INCLUDE='/var/tmp/leo-fftw-float-20260912/install/include';ARM_FFTW='/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(c):
 p=subprocess.run(c,text=True,capture_output=True)
 if p.returncode:raise RuntimeError(json.dumps({'command':c,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr},indent=2))
 return {'command':c,'stdout':p.stdout,'stderr':p.stderr}
def command(out,target,source,name,san=False):
 arm=target=='arm';cc=ARM_CC if arm else 'gcc';f=['-std=c11','-O1' if san else '-O3','-Wall','-Wextra','-fno-fast-math','-fno-math-errno','-fno-trapping-math']
 if arm:f+=['-Werror','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard',f'-I{ARM_INCLUDE}']
 if san:f+=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
 c=[cc,*f,'-I',str(out),str(out/'decimated_fir.c'),str(out/source)]
 c+=([ARM_FFTW] if arm else ['-lfftw3f'])+['-lm']
 if san:c+=['-fsanitize=address,undefined']
 return c+['-o',str(out/name)]
def build(target):
 out=ROOT/'builds'/target
 if out.exists():shutil.rmtree(out)
 shutil.copytree(SOURCE,out);san=target=='sanitizer';commands=[];binaries=[];units=[]
 for source,stem in [('test_decimated_fir.c','test_decimated_fir'),('bench_decimated_fir.c','bench_decimated_fir')]:
  name=f'{stem}_{target}';commands.append(run(command(out,target,source,name,san)));binaries.append(out/name)
  if target!='arm' and stem=='test_decimated_fir':
   p=subprocess.run([str(out/name)],text=True,capture_output=True,check=True);units.append({'binary':name,'executed':True,'stdout':p.stdout,'stderr':p.stderr})
 receipt={'schema':'arm-decimated-fine-neon-component/v1','target':target,'base':'Wave4 for future integration; standalone gate only','filter':'factor-5 circular 24-tap FP32 FIR; 500 Hz full-frame output grid; requested band response corrected by integration layer','bounds':'NEON loads begin only after tap-23; explicit n controls every output and partial wrap','commands':commands,'units':units,'binaries':{p.name:sha(p) for p in binaries},'sources':{p.name:sha(p) for p in out.iterdir() if p.suffix in ('.c','.h')}}
 (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str((out/'build-receipt.json').relative_to(ROOT)),'sha256':sha(out/'build-receipt.json')}
if __name__=='__main__':
 records={t:build(t) for t in ('host','sanitizer','arm')};(ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-decimated-fine-neon-matrix/v1','builds':records},indent=2)+'\n')
