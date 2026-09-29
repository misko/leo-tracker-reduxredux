"""Build separate NEON exact-widening candidate, retaining scalar evidence."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CC='/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
s=(ROOT/'bench.c').read_text().replace('/* CI16 component', '#include "neon_widen.h"\n\n/* CI16 component')
s=s.replace('for(size_t k=0;k<count;++k){', 'size_t first=0;\n#if defined(__ARM_NEON)\n        first=prepare_neon_prefix(d,iq,count,rx,&sum);\n#endif\n        for(size_t k=first;k<count;++k){')
s=s.replace('for(size_t k=0;k<128;++k)iq[k]=INT16_MIN;', 'for(size_t k=0;k<65536;++k){iq[4*k]=(int16_t)k;iq[4*k+1]=(int16_t)(65535-k);iq[4*k+2]=(int16_t)k;iq[4*k+3]=(int16_t)k;}')
for target in ('host','sanitizer','arm'):
    out=ROOT/'builds-v3'/target;out.mkdir(parents=True,exist_ok=False)
    (out/'bench.c').write_text(s)
    shutil.copy2(ROOT/'neon_widen.h',out/'neon_widen.h')
    shutil.copy2(ROOT/'builds/host/dwell_input.h',out/'dwell_input.h')
    flags=['-std=c11','-O3','-Wall','-Wextra','-Werror','-fno-fast-math']
    if target=='arm':flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
    if target=='sanitizer':flags+=['-O1','-g','-fsanitize=address,undefined']
    cmd=[CC if target=='arm' else 'gcc',*flags,str(out/'bench.c'),'-lm','-o',str(out/'bench')]
    subprocess.run(cmd,check=True)
    result=None if target=='arm' else subprocess.run([str(out/'bench')],capture_output=True,text=True,check=True).stdout
    (out/'build-receipt.json').write_text(json.dumps({'target':target,'command':cmd,'sources':{p.name:sha(p) for p in out.iterdir() if p.suffix in ('.c','.h')},'binary_sha256':sha(out/'bench'),'output':result},indent=2)+'\n')
