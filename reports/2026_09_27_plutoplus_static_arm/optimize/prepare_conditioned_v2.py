"""Separate FP32 conditioned dot experiment, retaining FP64 science scoring."""
import shutil
from build import HERE,build
from prepare_diff import replace
root=HERE/'work/conditionedv2';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/coarsev2/src',root/'src')
n=root/'src/native_presence';p=n/'presence.c';s=p.read_text()
s=replace(s,'    leo_presence_profile profile;', '    float *opt_conditioned_offsets,*opt_weighted;\n    leo_presence_profile profile;')
s=replace(s,'    free(w->weighted); free(w->base); free(w->conditioned_offsets);',
    '    free(w->opt_conditioned_offsets);free(w->opt_weighted);\n    free(w->weighted); free(w->base); free(w->conditioned_offsets);')
s=replace(s,'    ALLOC(exact, n); ALLOC(control, n); ALLOC(samples, w->max_samples);',
    '    ALLOC(opt_conditioned_offsets,2*CONDITIONED_TABLES*n);ALLOC(opt_weighted,2*n);\n    ALLOC(exact, n); ALLOC(control, n); ALLOC(samples, w->max_samples);')
s=replace(s,'            w->conditioned_offsets[f*n+k] = rotate(-TAU * (f * 100.0) * k / rate);',
    '''        {
            w->conditioned_offsets[f*n+k] = rotate(-TAU * (f * 100.0) * k / rate);
            w->opt_conditioned_offsets[2*(f*n+k)]=(float)creal(w->conditioned_offsets[f*n+k]);
            w->opt_conditioned_offsets[2*(f*n+k)+1]=(float)cimag(w->conditioned_offsets[f*n+k]);
        }''')
s=replace(s,'static void conditioned_scores(', '#include "conditioned_dot.h"\n\nstatic void conditioned_scores(')
s=replace(s,'            w->weighted[k] = w->samples[start+k] * w->base[k];',
    '''            w->weighted[k] = w->samples[start+k] * w->base[k];
            w->opt_weighted[2*k]=(float)creal(w->weighted[k]);
            w->opt_weighted[2*k+1]=(float)cimag(w->weighted[k]);''')
s=replace(s,'''            for (size_t k = 0; k < w->n; ++k)
                total += w->weighted[k] * (regular ? w->conditioned_offsets[f*w->n+k] :
                    rotate(-TAU*(frequencies[f]-frequencies[0])*k/w->rate));''',
    '''            if (regular) total=opt_conditioned_dot(w->opt_weighted,w->opt_conditioned_offsets+2*f*w->n,w->n);
            else for (size_t k = 0; k < w->n; ++k)
                total += w->weighted[k] * rotate(-TAU*(frequencies[f]-frequencies[0])*k/w->rate);''')
p.write_text(s);shutil.copyfile(HERE/'conditioned_dot.h',n/'conditioned_dot.h')
build('conditionedv2',root);build('conditionedv2',root,host=True,sanitize=True)
