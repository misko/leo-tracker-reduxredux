#!/usr/bin/env python3
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parent; I=R/'implementation'; T=R/'tests/test_coarse_winograd.c'
ARM='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def build(target):
 out=R/'builds'/target;out.mkdir(parents=True,exist_ok=True);cc=ARM if target=='arm' else 'gcc'
 flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math']
 if target=='arm':flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
 if target=='sanitizer':flags+=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
 binary=out/f'test_coarse_winograd_{target}';cmd=[cc,*flags,'-I',str(I),str(I/'coarse_winograd.c'),str(T),'-lm','-o',str(binary)]
 p=subprocess.run(cmd,text=True,capture_output=True,check=True);run=None
 if target!='arm':run=subprocess.run([str(binary)],text=True,capture_output=True,check=True).stdout.strip()
 receipt={'schema':'arm-wave7-coarse-winograd/v1','target':target,'command':cmd,'compiler_stderr':p.stderr,'run':run,'binary_sha256':sha(binary),'sources':{str(x.relative_to(R)):sha(x) for x in [I/'coarse_winograd.c',I/'coarse_winograd.h',T]}}
 (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt
if __name__=='__main__':
 data={x:build(x) for x in ['host','sanitizer','arm']};(R/'build-manifest.json').write_text(json.dumps(data,indent=2)+'\n')
