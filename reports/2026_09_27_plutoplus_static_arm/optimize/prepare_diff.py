"""Prepare separately identifiable FP32 differential-correlation experiment."""
import shutil
from pathlib import Path
from build import BASE, HERE, build


def replace(text,old,new):
    if text.count(old)!=1: raise ValueError('source changed: '+old[:70])
    return text.replace(old,new)


def prepare():
    root=HERE/'work/diffdot';root.mkdir(parents=True,exist_ok=False)
    shutil.copytree(BASE/'src',root/'src')
    n=root/'src/native_presence';p=n/'presence.c';s=p.read_text()
    s=replace(s,'    leo_presence_profile profile;', '    float *opt_template, *opt_fold;\n    leo_presence_profile profile;')
    s=replace(s,'    free(w->weighted); free(w->base); free(w->conditioned_offsets);',
        '    free(w->opt_template); free(w->opt_fold);\n    free(w->weighted); free(w->base); free(w->conditioned_offsets);')
    s=replace(s,'    ALLOC(exact, n); ALLOC(control, n); ALLOC(samples, w->max_samples);',
        '    ALLOC(opt_template,3*n); ALLOC(opt_fold,3*n);\n    ALLOC(exact, n); ALLOC(control, n); ALLOC(samples, w->max_samples);')
    p.write_text(s)
    p=n/'coarse_differential.h';s=p.read_text()
    s=replace(s,'    w->power_template_energy=diff_projection(w,w->diff_template);',
        '    for(size_t k=0;k<w->n;++k) {\n'
        '        w->opt_template[3*k]=(float)creal(w->diff_template[k]);\n'
        '        w->opt_template[3*k+1]=(float)cimag(w->diff_template[k]);\n'
        '        w->opt_template[3*k+2]=(float)w->power_native_template[k];\n'
        '    }\n    w->power_template_energy=diff_projection(w,w->diff_template);')
    start=s.index('static double diff_native_cell(');end=s.index('\n#if LEO_PRESENCE_DIFFERENTIAL_CI16',start)
    s=s[:start]+'#include "diff_dot.h"\n#define diff_native_cell opt_diff_cell\n'+s[end:]
    s=replace(s,'    double energy=diff_projection(w,w->diff_folded);',
        '    for(size_t k=0;k<w->n;++k) {\n'
        '        w->opt_fold[3*k]=(float)creal(w->diff_folded[k]);\n'
        '        w->opt_fold[3*k+1]=(float)cimag(w->diff_folded[k]);\n'
        '        w->opt_fold[3*k+2]=(float)w->power_native_folded[k];\n'
        '    }\n    double energy=diff_projection(w,w->diff_folded);')
    p.write_text(s);shutil.copyfile(HERE/'diff_dot.h',n/'diff_dot.h')
    build('diffdot',root)
    build('diffdot',root,host=True,sanitize=True)


if __name__=='__main__': prepare()
