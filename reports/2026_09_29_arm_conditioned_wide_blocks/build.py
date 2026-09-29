"""Test longer conditioned Taylor blocks without dropping frames or bins."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
REPORTS=ROOT.parent
BASE=REPORTS/'2026_09_29_arm_wave4_combined/sources'


def build_variant(block):
    root=ROOT/str(block);source=root/'sources'
    assert not source.exists()
    shutil.copytree(BASE,source)
    p=source/'full_search.c';text=p.read_text()
    assert text.count('#define CONDITIONED_MOMENT_BLOCK 32')==1
    text=text.replace('#define CONDITIONED_MOMENT_BLOCK 32',f'#define CONDITIONED_MOMENT_BLOCK {block}')
    text=text.replace('/* Taylor tail <=8e-7.', '/* Experimental wider block: the old bound below is not applicable.\n * This variant is qualified by direct DFT tests and cohort audits.\n * Historical 32-sample bound: Taylor tail <=8e-7.')
    p.write_text(text)
    shutil.copyfile(ROOT/'test_wide_moments.c',source/'test_wide_moments.c')
    spec=importlib.util.spec_from_file_location('wide_builder',REPORTS/'2026_09_29_arm_resampled_omit_fused/build.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    builder.ROOT=root;builder.SOURCE=source;records={}
    for target in ['host','sanitizer','arm']:
        record=builder.build(target)
        path=root/record['receipt'];receipt=json.loads(path.read_text());out=path.parent
        name='test_wide_moments_'+target
        command=builder.link_command(out,target,['test_wide_moments.c'],name,target=='sanitizer',0)
        receipt['commands'].append(builder.run(command));receipt['binaries'][name]=builder.sha(out/name)
        if target!='arm':
            run=subprocess.run([str(out/name)],capture_output=True,text=True,check=True)
            receipt['units'].append({'binary':name,'executed':True,'stdout':run.stdout,'stderr':run.stderr})
        receipt.update(schema='arm-conditioned-wide-blocks/v1',conditioned_block_samples=block,
                       approximation='fourth-order Taylor approximation on longer blocks; no near-max FP64 fallback',
                       invariants='all 16 frames, all 41 bins and FP64 final GLRT retained')
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target]={'receipt':str(path.relative_to(ROOT)),'sha256':builder.sha(path)}
    return records


if __name__=='__main__':
    records={str(block):build_variant(block) for block in [64,128]}
    (ROOT/'build-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
