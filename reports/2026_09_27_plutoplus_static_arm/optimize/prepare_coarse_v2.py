"""Isolate exact register-resident coarse fold from qualified rankunroll."""
import shutil
from build import HERE,build
from prepare_diff import replace

root=HERE/'work/coarsev2'
root.mkdir(exist_ok=False)
shutil.copytree(HERE/'work/rankunroll/src',root/'src')
n=root/'src/native_presence'
shutil.copyfile(HERE/'coarse_fold_v2.h',n/'coarse_fold_v2.h')
p=n/'coarse_differential.h';s=p.read_text()
s=replace(s,'#include "ci16_fold.h"','#include "ci16_fold.h"\n#include "coarse_fold_v2.h"')
s=replace(s,'if (iq) coarse_fold_ci16(w,iq,count);','if (iq) opt_coarse_fold_ci16(w,iq,count);')
p.write_text(s)
build('coarsev2',root);build('coarsev2',root,host=True,sanitize=True)
