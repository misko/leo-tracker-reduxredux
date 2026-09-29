#!/usr/bin/env python3
"""Compile and execute host/sanitizer component checks for the frozen source."""
import importlib.util,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
origin=ROOT.parent/'2026_09_29_arm_wave5_final'/'build_v2.py'
spec=importlib.util.spec_from_file_location('wave5_build',origin);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.ROOT=ROOT;m.SOURCE=ROOT/'sources'
records={}
for target in ('host','sanitizer'):
    record=m.build(target)
    old=ROOT/'builds-v2'/target;new=ROOT/'checks'/target
    new.parent.mkdir(parents=True,exist_ok=True)
    if new.exists():shutil.rmtree(new)
    shutil.move(old,new)
    record['receipt']=str((new/'build-receipt.json').relative_to(ROOT));records[target]=record
if (ROOT/'builds-v2').exists(): (ROOT/'builds-v2').rmdir()
(ROOT/'checks-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
