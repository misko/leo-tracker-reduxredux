"""Exact bounded CI16 conversion applied to immutable baseline or rank build."""
import argparse
from pathlib import Path
import shutil
from build import BASE,HERE,build
from prepare_diff import replace


def main():
    p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('--rank',action='store_true');a=p.parse_args()
    root=HERE/'work'/a.name;root.mkdir(parents=True,exist_ok=False)
    source=HERE/'work/rankfast' if a.rank else BASE
    shutil.copytree(source/'src',root/'src');n=root/'src/native_presence'
    shutil.copyfile(HERE/'fold_double.h',n/'fold_double.h')
    p=n/'blind_aligned_v5.c';s=p.read_text()
    s=replace(s,'#include <stdint.h>','#include <stdint.h>\n#include "fold_double.h"')
    s=replace(s,'(double)w->sum_real[k]','opt_fold_double(w->sum_real[k])')
    s=replace(s,'(double)w->sum_imag[k]','opt_fold_double(w->sum_imag[k])')
    p.write_text(s)
    p=n/'ci16_fold.h';s=p.read_text();s='#include "fold_double.h"\n'+s
    for var in ['energy','real','imag']:
        s=replace(s,f'(double){var}[k]',f'opt_fold_double({var}[k])')
    p.write_text(s)
    build(a.name,root);build(a.name,root,host=True,sanitize=True)


if __name__=='__main__':main()
