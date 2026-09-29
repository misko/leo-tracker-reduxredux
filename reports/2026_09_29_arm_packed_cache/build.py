"""Build immutable Q15 block-floating fine-spectrum cache snapshots."""
import hashlib, json, shutil, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_29_arm_fine_precision'/'builds'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def replace_once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1: raise RuntimeError(f'{path}: replacement count {text.count(old)} for {old!r}')
    path.write_text(text.replace(old,new))

def main():
    arm='--arm' in sys.argv; sanitize='--sanitize' in sys.argv
    version=2 if '--v2' in sys.argv else 1
    if arm and sanitize: raise SystemExit('--sanitize is host-only')
    baseline='arm-raw-v2' if arm else 'host-raw-v2'
    flavor=('arm-pack-q15-' if arm else 'host-asan-pack-q15-' if sanitize else 'host-pack-q15-')+f'v{version}'
    out=HERE/'builds'/flavor
    if out.exists(): raise SystemExit(f'refusing to overwrite {out}')
    shutil.copytree(BASE/baseline,out)
    shutil.copy2(HERE/'fine_pack.h',out/'fine_pack.h');shutil.copy2(HERE/'test_fine_pack.c',out/'test_fine_pack.c')
    source=out/'full_search.c'
    replace_once(source,'#include "fine_precision.h"','#include "fine_pack.h"')
    replace_once(source,'leo_fine_precision_cache fine_cache;','leo_fine_pack_cache fine_cache;')
    replace_once(source,'leo_fine_precision_init(&fine_cache,w->fine_fft.size)','leo_fine_pack_init(&fine_cache,w->fine_fft.size)')
    replace_once(source,'leo_fine_precision_scores(w,count,refined,frequencies[0],nf,scores,&fine_cache)',
        'leo_fine_pack_scores(w,count,refined,frequencies[0],nf,scores,&fine_cache)')
    text=source.read_text()
    if text.count('leo_fine_precision_free(&fine_cache);')!=2: raise RuntimeError('unexpected free call count')
    source.write_text(text.replace('leo_fine_precision_free(&fine_cache);','leo_fine_pack_free(&fine_cache);'))
    replace_once(source,
        '    out.fine_precision_calls=fine_cache.calls;\n'
        '    out.fine_precision_guard_checks=fine_cache.guard_checks;\n'
        '    out.fine_precision_fallbacks=fine_cache.fallbacks;\n'
        '    out.fine_precision_nonfinite_fallbacks=fine_cache.nonfinite_fallbacks;\n'
        '    out.fine_precision_near_tie_fallbacks=fine_cache.near_tie_fallbacks;\n'
        '    out.fine_precision_interpolation_fallbacks=fine_cache.interpolation_fallbacks;',
        '    out.fine_pack_calls=fine_cache.calls;\n'
        '    out.fine_pack_frames=fine_cache.frames;\n'
        '    out.fine_pack_values=fine_cache.values;\n'
        '    out.fine_pack_bytes=fine_cache.bytes;\n'
        '    out.fine_pack_zero_frames=fine_cache.zero_frames;\n'
        '    out.fine_pack_clipped_values=fine_cache.clipped_values;\n'
        '    out.fine_pack_scale_scan_ms=fine_cache.scale_scan_ms;\n'
        '    out.fine_pack_packing_ms=fine_cache.packing_ms;\n'
        '    out.fine_pack_dequant_ms=fine_cache.dequant_ms;')
    header=out/'full_search.h'
    replace_once(header,
        '    int32_t fine_precision_calls, fine_precision_guard_checks;\n'
        '    int32_t fine_precision_fallbacks, fine_precision_nonfinite_fallbacks;\n'
        '    int32_t fine_precision_near_tie_fallbacks, fine_precision_interpolation_fallbacks;',
        '    int32_t fine_pack_calls;\n'
        '    uint64_t fine_pack_frames, fine_pack_values, fine_pack_bytes;\n'
        '    uint64_t fine_pack_zero_frames, fine_pack_clipped_values;\n'
        '    double fine_pack_scale_scan_ms, fine_pack_packing_ms, fine_pack_dequant_ms;')
    runner=out/'cohort_probe.c'
    old='\\"fine_precision_mode\\":\\"raw\\",\\"fine_precision_calls\\":%d,\\"fine_precision_guard_checks\\":%d,\\"fine_precision_fallbacks\\":%d,\\"fine_precision_nonfinite_fallbacks\\":%d,\\"fine_precision_near_tie_fallbacks\\":%d,\\"fine_precision_interpolation_fallbacks\\":%d,'
    new='\\"fine_precision_mode\\":\\"pack_q15\\",\\"fine_pack_calls\\":%d,\\"fine_pack_frames\\":%llu,\\"fine_pack_values\\":%llu,\\"fine_pack_bytes\\":%llu,\\"fine_pack_zero_frames\\":%llu,\\"fine_pack_clipped_values\\":%llu,\\"fine_pack_scale_scan_ms\\":%.17g,\\"fine_pack_packing_ms\\":%.17g,\\"fine_pack_dequant_ms\\":%.17g,'
    replace_once(runner,old,new)
    replace_once(runner,
        'r->fine_precision_calls,r->fine_precision_guard_checks,r->fine_precision_fallbacks,r->fine_precision_nonfinite_fallbacks,r->fine_precision_near_tie_fallbacks,r->fine_precision_interpolation_fallbacks,r->total_cpu_ms',
        'r->fine_pack_calls,(unsigned long long)r->fine_pack_frames,(unsigned long long)r->fine_pack_values,(unsigned long long)r->fine_pack_bytes,(unsigned long long)r->fine_pack_zero_frames,(unsigned long long)r->fine_pack_clipped_values,r->fine_pack_scale_scan_ms,r->fine_pack_packing_ms,r->fine_pack_dequant_ms,r->total_cpu_ms')
    base_receipt=json.loads((BASE/baseline/'fine-precision-build.json').read_text());commands=[]
    for record in base_receipt['commands']:
        cmd=[arg.replace(str(BASE/baseline),str(out)) for arg in record['command']]
        if version==2: cmd.insert(1,'-DLEO_FINE_PACK_NEON=1')
        if any(arg.endswith('/test_fine_precision.c') for arg in cmd):
            cmd=[str(out/'test_fine_pack.c') if arg.endswith('/test_fine_precision.c') else arg for arg in cmd]
            cmd=[str(out/'test_fine_pack') if arg.endswith('/test_fine_precision') else arg for arg in cmd]
        else: cmd=[str(out/'cohort_fine_pack') if arg.endswith('/cohort_fine_precision') else arg for arg in cmd]
        if sanitize:
            cmd=['-O1' if arg=='-O3' else arg for arg in cmd];cmd[1:1]=['-g','-fno-omit-frame-pointer','-fsanitize=address,undefined'];cmd.insert(-2,'-fsanitize=address,undefined')
        run=subprocess.run(cmd,capture_output=True,text=True,check=True)
        commands.append({'command':cmd,'compiler_stdout':run.stdout,'compiler_stderr':run.stderr})
    test=out/'test_fine_pack'
    if arm: unit_stdout='cross-build only; ARM workload execution is delegated to the serialized evaluator\n';unit_stderr=''
    else:
        import os
        env=None if not sanitize else dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        run=subprocess.run([str(test)],capture_output=True,text=True,check=True,env=env);unit_stdout=run.stdout;unit_stderr=run.stderr
    binaries=[out/'cohort_fine_pack',test]
    sources={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in ('.c','.h')}
    result={'schema':f'arm-packed-cache-build/v{version}','mode':'pack_q15_neon' if version==2 else 'pack_q15','arm':arm,'sanitize':sanitize,
        'source_baseline':str(BASE/baseline),'source_baseline_receipt_sha256':sha(BASE/baseline/'fine-precision-build.json'),
        'algorithm':{'fft':'FP32 FFTW unchanged','cache':'interleaved signed int16 real/imag with one FP32 scale per frame','quantization':'nearbyintf(value*32767/max_component), symmetric clamp [-32767,32767]','scoring':'only requested bins dequantized; magnitude and normalized accumulation in FP64','packing':'ARM NEON four-component peak scan and pack with nearest-even magic bias' if version==2 else 'scalar'},
        'commands':commands,'unit_stdout':unit_stdout,'unit_stderr':unit_stderr,
        'binaries':{p.name:sha(p) for p in binaries},'sources':sources}
    (out/'build-receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'fine-precision-build.json').unlink()

if __name__=='__main__':main()
