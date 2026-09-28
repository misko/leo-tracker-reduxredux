"""Exact integer energy for unconditioned CI16; floating/tone path unchanged."""
import shutil
from build import HERE,build
from prepare_diff import replace
root=HERE/'work/energyv2';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/conditionedv2/src',root/'src')
n=root/'src/native_presence';p=n/'presence.c';s=p.read_text()
s=replace(s,'static void select_acquisition_support(leo_presence_workspace *w, size_t count, int epoch)',
    '#include "ci16_energy_v2.h"\n\nstatic void select_acquisition_support(leo_presence_workspace *w, size_t count, int epoch, const int16_t *iq)')
s=replace(s,'        for (size_t k=0; k<w->n; ++k) energy+=power(w->samples[start+k]);',
    '        if(iq) energy=opt_ci16_energy(iq+2*start,w->n);\n        else for (size_t k=0; k<w->n; ++k) energy+=power(w->samples[start+k]);')
s=replace(s,'            for (int k=begin; k<end; ++k) energy[region]+=power(w->samples[start+k]);',
    '            if(iq) energy[region]=opt_ci16_energy(iq+2*(start+begin),(size_t)(end-begin));\n            else for (int k=begin; k<end; ++k) energy[region]+=power(w->samples[start+k]);')
s=replace(s,'        select_acquisition_support(w,count,refined);',
    '        select_acquisition_support(w,count,refined,w->nuisance.applied ? NULL : original_ci16);')
p.write_text(s)
p=n/'tone_nuisance.h';s=replace(p.read_text(),'if (iq) energy=creal(ci16_lag_sum(iq,count,0));',
    'if (iq) energy=opt_ci16_energy(iq,count);');p.write_text(s)
shutil.copyfile(HERE/'ci16_energy_v2.h',n/'ci16_energy_v2.h')
build('energyv2',root);build('energyv2',root,host=True,sanitize=True)
