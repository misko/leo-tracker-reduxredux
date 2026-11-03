"""Restrict coarse timing cells; preserve every CFO lane and downstream stage."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import hashlib

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_28_arm_boundary_fallback/builds/arm-v1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    arm='--arm' in sys.argv
    out=HERE/'regional-builds'/('arm-v1' if arm else 'host-v1');out.parent.mkdir(exist_ok=True)
    shutil.copytree(BASE,out)
    header=out/'src/native_presence/coarse_fp32.h'
    text=header.read_text()
    old='for (ptrdiff_t epoch=0; epoch<valid; epoch+=epoch_stride(w)) {'
    new='''for (int active=0; active<regional_count; ++active) {
                ptrdiff_t epoch=regional_epochs[active];
                if (epoch>=valid) continue;'''
    assert text.count(old)==1;header.write_text(text.replace(old,new))
    runner=out/'cohort_probe.c';text=runner.read_text()
    text=text.replace('#include "full_search.h"','''static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"''')
    text=text.replace('if(argc!=5) return 2;','if(argc!=6) return 2;')
    text=text.replace('for(int window=0;window<11;window++) for(int rx=0;rx<2;rx++){', '''FILE *regions=fopen(argv[5],"r"); if(!regions)return 2;
    for(int window=0;window<11;window++) for(int rx=0;rx<2;rx++){
        if(fscanf(regions,"%d",&regional_count)!=1 || regional_count<0 || regional_count>(int)frame)return 5;
        for(int j=0;j<regional_count;++j) {
            if(fscanf(regions,"%d",&regional_epochs[j])!=1 || regional_epochs[j]<0 || regional_epochs[j]>=(int)frame ||
               (j && regional_epochs[j]<=regional_epochs[j-1]))return 5;
        }''')
    text=text.replace('leo_presence_destroy(w);free(samples);', 'fclose(regions);leo_presence_destroy(w);free(samples);')
    runner.write_text(text)
    cmd=json.loads((BASE/'build.json').read_text())['commands'][1]
    oldroot=str(Path(cmd[cmd.index('-I')+1]).parents[1])
    cmd=[x.replace(oldroot,str(out)) for x in cmd if not x.endswith('/full_search.c')]
    if not arm:
        cmd=[x for x in cmd if x not in ('-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-DLEO_FULL_ARM_AFFINITY','-Werror')]
        cmd[0]='gcc';cmd=['-lfftw3f' if x.endswith('/libfftw3f.a') else x for x in cmd]
    cmd[-1]=str(out/'cohort_regional')
    compiled=subprocess.run(cmd,capture_output=True,text=True,check=True)
    (out/'regional-build.json').write_text(json.dumps({'command':cmd,'compiler_stderr':compiled.stderr,
       'binary_sha256':sha(out/'cohort_regional'),'source_sha256':{str(p.relative_to(out)):sha(p)
       for p in out.rglob('*') if p.suffix in ('.c','.h')}},indent=2)+'\n')

if __name__=='__main__':main()
