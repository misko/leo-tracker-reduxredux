"""Isolated exact-CI16 preparation microbenchmark; no radio operations."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for target in ('host','sanitizer','arm'):
    out=ROOT/'builds'/target
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(ROOT/'bench.c',out/'bench.c')
    shutil.copy2(ROOT.parent/'2026_09_29_arm_wave7_frontier_pgo/sources/dwell_input.h',out/'dwell_input.h')
    flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math']
    if target=='arm':flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
    if target=='sanitizer':flags+=['-O1','-g','-fsanitize=address,undefined']
    cmd=[CC if target=='arm' else 'gcc',*flags,str(out/'bench.c'),'-lm','-o',str(out/'bench')]
    subprocess.run(cmd,check=True)
    result=None if target=='arm' else subprocess.run([str(out/'bench')],capture_output=True,text=True,check=True).stdout
    (out/'build-receipt.json').write_text(json.dumps({'target':target,'command':cmd,'sources':{p.name:sha(p) for p in out.iterdir() if p.suffix in ('.c','.h')},'binary_sha256':sha(out/'bench'),'output':result},indent=2)+'\n')
