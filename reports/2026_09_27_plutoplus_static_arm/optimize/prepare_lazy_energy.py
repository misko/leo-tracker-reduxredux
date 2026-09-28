"""Defer tone-fit energy until the unchanged tone screen requests a fit."""
import shutil
from build import HERE,build
from prepare_diff import replace
root=HERE/'work/lazyenergy';root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/energyv2/src',root/'src')
p=root/'src/native_presence/tone_nuisance.h';s=p.read_text()
start=s.index('    double energy=0;');end=s.index('    size_t size=',start)
energy=s[start:end];s=s[:start]+s[end:]
s=replace(s,'    if (fraction<0.02) return 0;','    if (fraction<0.02) return 0;\n'+energy.rstrip())
p.write_text(s);build('lazyenergy',root);build('lazyenergy',root,host=True,sanitize=True)
