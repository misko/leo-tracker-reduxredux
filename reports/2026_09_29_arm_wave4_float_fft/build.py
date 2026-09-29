"""Qualify FP32 final-scorer FFTs on the current fused pipeline."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT.parent
BASE = REPORTS/'2026_09_29_arm_wave3_combined/sources'
OLD = REPORTS/'2026_09_29_arm_float_glrt_fft'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def prepare():
    source = ROOT/'sources'
    assert not source.exists()
    shutil.copytree(BASE, source)
    p = source/'src/native_presence/presence.c'
    text = p.read_text()
    text = once(text, '#include <time.h>', '#include <time.h>\n#include <fftw3.h>')
    text = once(text, '    leo_fft fine_fft, short_fft, glrt_fft;', '''    leo_fft fine_fft, short_fft, glrt_fft;
    fftwf_complex *glrt_f32_input[2], *glrt_f32_output[2];
    fftwf_plan glrt_f32_plan[2];''')
    old = '    leo_fft_free(&w->fine_fft); leo_fft_free(&w->short_fft); leo_fft_free(&w->glrt_fft);'
    text = once(text, old, old+'''
    for(int q=0;q<2;++q){if(w->glrt_f32_plan[q])fftwf_destroy_plan(w->glrt_f32_plan[q]);fftwf_free(w->glrt_f32_input[q]);fftwf_free(w->glrt_f32_output[q]);}''')
    helper = (ROOT/'float_fft.h').read_text()
    old = 'static int glrt(leo_presence_workspace *w, size_t count, int epoch,'
    text = once(text, old, helper+'\n'+old)
    old = 'leo_fft_forward(&w->short_fft, w->input);'
    assert text.count(old) == 2
    text = text.replace(old, 'if(glrt_float_fft_forward(w,&w->short_fft,w->input,128,0))return -1;')
    text = once(text, 'leo_fft_forward(&w->glrt_fft, w->input);',
                'if(glrt_float_fft_forward(w,&w->glrt_fft,w->input,512,1))return -1;')
    p.write_text(text)
    shutil.copyfile(OLD/'tests/test_float_glrt_fft.c', source/'test_float_glrt_fft.c')
    p = source/'fused_probe.c'
    text = p.read_text().replace('\\"final_scorer\\":\\"fp64\\"',
                                '\\"final_scorer\\":\\"fp64-dots-fp32-fft\\"')
    p.write_text(text)
    return source


if __name__ == '__main__':
    spec = importlib.util.spec_from_file_location('float_builder', REPORTS/'2026_09_29_arm_resampled_omit_fused/build.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.ROOT = ROOT
    builder.SOURCE = prepare()
    records = {}
    for target in ['host', 'sanitizer', 'arm']:
        record = builder.build(target)
        path = ROOT/record['receipt']
        receipt = json.loads(path.read_text())
        out = path.parent
        name = 'test_float_glrt_fft_'+target
        command = builder.link_command(out,target,['test_float_glrt_fft.c'],name,target=='sanitizer',0)
        receipt['commands'].append(builder.run(command))
        receipt['binaries'][name] = builder.sha(out/name)
        if target != 'arm':
            run = subprocess.run([str(out/name)],capture_output=True,text=True,check=True)
            receipt['units'].append({'binary':name,'executed':True,'stdout':run.stdout,'stderr':run.stderr})
        receipt.update(schema='arm-wave4-float-glrt-fft/v1',
                       search_feature='Wave3 combined; FP64 matched dots, ceilings and spectra accumulation; FP32 128/512-point GLRT FFTs without fallback',
                       plan_setup='lazy FFTWf plan creation remains inside timed first GLRT call')
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target] = {'receipt':str(path.relative_to(ROOT)),'sha256':builder.sha(path)}
    (ROOT/'build-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
