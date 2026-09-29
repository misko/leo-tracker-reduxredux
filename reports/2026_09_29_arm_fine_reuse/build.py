"""Build the exact epoch-keyed fine-FFT reuse prototype from frozen regional V1."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'2026_09_29_arm_lag_discovery'/'regional-builds'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def replace_once(path, old, new):
    text=path.read_text()
    if text.count(old)!=1:
        raise RuntimeError(f'{path}: expected one replacement, got {text.count(old)}')
    path.write_text(text.replace(old,new))

def main():
    arm='--arm' in sys.argv
    sanitize='--sanitize' in sys.argv
    if arm and sanitize:
        raise SystemExit('--sanitize is host-only')
    flavor='arm-v1' if arm else 'host-v1'
    output_flavor='arm-v3' if arm else ('host-asan-v1' if sanitize else 'host-v4')
    out=HERE/'builds'/output_flavor
    if out.exists():
        raise SystemExit(f'refusing to overwrite {out}')
    shutil.copytree(SOURCE/flavor,out)
    shutil.copy2(HERE/'fine_reuse.h',out/'fine_reuse.h')
    shutil.copy2(HERE/'test_fine_reuse.c',out/'test_fine_reuse.c')

    source=out/'full_search.c'
    replace_once(source,'#include "presence.c"','#include "presence.c"\n#include "fine_reuse.h"')
    replace_once(source,'    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);\n    for (size_t r=0; r<nr; ++r) {',
        '    started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);\n'
        '    leo_fine_reuse_cache fine_cache;\n'
        '    leo_fine_reuse_init(&fine_cache,w->fine_fft.size);\n'
        '    for (size_t r=0; r<nr; ++r) {')
    replace_once(source,'        fine_scores(w,count,refined,frequencies[0],nf,scores);',
        '        if (leo_fine_reuse_scores(w,count,refined,frequencies[0],nf,scores,&fine_cache)) {\n'
        '            leo_fine_reuse_free(&fine_cache); return -1;\n'
        '        }')
    replace_once(source,'    out.acquisition_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;',
        '    out.fine_fft_cache_entries=fine_cache.count;\n'
        '    out.fine_fft_cache_hits=fine_cache.hits;\n'
        '    leo_fine_reuse_free(&fine_cache);\n'
        '    out.acquisition_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;')

    header=out/'full_search.h'
    replace_once(header,'    double fine_fft_cpu_ms;',
        '    double fine_fft_cpu_ms;\n    int32_t fine_fft_cache_entries;\n    int32_t fine_fft_cache_hits;')
    runner=out/'cohort_probe.c'
    replace_once(runner,'\\\"conditioned_fallback_count\\\":%d,\\\"timings_ms\\\"',
        '\\\"conditioned_fallback_count\\\":%d,\\\"fine_fft_cache_entries\\\":%d,\\\"fine_fft_cache_hits\\\":%d,\\\"timings_ms\\\"')
    replace_once(runner,'r->conditioned_fallback_count,r->total_cpu_ms',
        'r->conditioned_fallback_count,r->fine_fft_cache_entries,r->fine_fft_cache_hits,r->total_cpu_ms')

    old=json.loads((SOURCE/flavor/'regional-build.json').read_text())['command']
    old_root=str(SOURCE/flavor)
    cohort=[arg.replace(old_root,str(out)) for arg in old]
    if sanitize:
        cohort=['-O1' if arg=='-O3' else arg for arg in cohort]
        cohort[1:1]=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
        cohort.insert(-2,'-fsanitize=address,undefined')
    cohort[-1]=str(out/'cohort_fine_reuse')
    test=[]
    skip_next=False
    for arg in cohort:
        if arg.endswith('/cohort_probe.c'):
            test.append(str(out/'test_fine_reuse.c'))
        elif arg==str(out/'cohort_fine_reuse'):
            test.append(str(out/'test_fine_reuse'))
        else:
            test.append(arg)
    commands=[cohort,test]
    results=[]
    for command in commands:
        run=subprocess.run(command,capture_output=True,text=True,check=True)
        results.append({'command':command,'compiler_stdout':run.stdout,'compiler_stderr':run.stderr})
    if arm:
        unit_stdout='cross-build only; execute test_fine_reuse on ARM target\n'
        unit_stderr=''
    else:
        env=None
        if sanitize:
            import os
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        unit=subprocess.run([str(out/'test_fine_reuse')],capture_output=True,text=True,
            check=True,env=env)
        unit_stdout=unit.stdout;unit_stderr=unit.stderr
    receipt={'schema':'arm-fine-reuse-build/v1','source_baseline':str(SOURCE/flavor),
        'commands':results,'unit_stdout':unit_stdout,'unit_stderr':unit_stderr,
        'binaries':{p.name:sha(p) for p in (out/'cohort_fine_reuse',out/'test_fine_reuse')},
        'sources':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.suffix in ('.c','.h')}}
    (out/'fine-reuse-build.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    main()
