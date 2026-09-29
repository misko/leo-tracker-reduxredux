#!/usr/bin/env python3
"""Build the isolated 2.5 MHz .312 loss-budget variant."""
import json
import types
from pathlib import Path

ROOT=Path(__file__).resolve().parent
source=(ROOT/'build.py').read_text()
source=source.replace("SOURCE=ROOT/'sources'", "SOURCE=ROOT/'sources-312'")
source=source.replace("ROOT/'builds'/target", "ROOT/'builds-312'/target")
source=source.replace("THRESHOLDS={'2500000':.300", "THRESHOLDS={'2500000':.312")
assert "sources-312" in source and "builds-312" in source
module=types.ModuleType('rate_coarse_gate_312')
module.__file__=str(ROOT/'build.py')
exec(compile(source,str(ROOT/'build.py'),'exec'),module.__dict__)

if __name__=='__main__':
    records={target:module.build(target) for target in ('host','sanitizer','arm')}
    (ROOT/'build-manifest-312.json').write_text(json.dumps(records,indent=2)+'\n')
