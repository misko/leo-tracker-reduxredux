#!/usr/bin/env python3
import importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent/'2026_09_29_arm_resampled_omit_fused'
spec=importlib.util.spec_from_file_location('half_rate_builder',BASE/'build.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder);builder.ROOT=ROOT;builder.SOURCE=ROOT/'sources'
def build(target):
 record=builder.build(target);path=ROOT/record['receipt'];receipt=json.loads(path.read_text());out=path.parent;name='test_half_rate_'+target
 command=builder.link_command(out,target,['test_half_rate.c','proposal_core.c'],name,target=='sanitizer',0);receipt['commands'].append(builder.run(command));receipt['binaries'][name]=builder.sha(out/name)
 if target!='arm':
  p=subprocess.run([str(out/name)],text=True,capture_output=True,check=True);receipt['units'].append({'binary':name,'executed':True,'stdout':p.stdout,'stderr':p.stderr})
 receipt.update(schema='arm-half-rate-analysis-build/v1',analysis_decimation=2,anti_alias_filter=False,original_rates_hz=[2500000,5000000,7500000,10000000],effective_rates_hz=[1250000,2500000,3750000,5000000],epoch_output_scale=2,timing='one-time input/template decimation CPU amortized across 22 fused outer timers',approximation='even-sample selection without anti-alias filtering; experimental only')
 path.write_text(json.dumps(receipt,indent=2)+'\n');return {'receipt':str(path.relative_to(ROOT)),'sha256':builder.sha(path)}
if __name__=='__main__':
 records={t:build(t) for t in ('host','sanitizer','arm')};(ROOT/'build-manifest.json').write_text(json.dumps({'schema':'arm-half-rate-analysis-matrix/v1','builds':records},indent=2)+'\n')
