"""Combine exact proposal preplanning and revised top-four selection."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
REPORTS=ROOT.parent
PREPLAN=REPORTS/'2026_09_29_arm_proposal_preplan'
RANK=REPORTS/'2026_09_29_arm_proposal_rank_fast_v2/sources'


def prepare():
    source=ROOT/'sources'
    assert not source.exists()
    shutil.copytree(PREPLAN/'sources',source)
    p=source/'proposal_core.c'
    text=p.read_text()
    rank=(RANK/'proposal_core.c').read_text()
    start=text.index('static int top4_linear(')
    end=text.index('\nstatic void emit_ints',start)
    replacement=rank[rank.index('static __attribute__((unused)) int top4_sort_reference('):rank.index('\nstatic void emit_ints')]
    text=text[:start]+replacement+text[end:]
    old='    for(int m=0;m<LAG_COUNT;m++){int lag=lags[m];'
    assert text.count(old)==1
    text=text.replace(old,'    for(size_t rank=0;rank<z;rank++)b->scores[3][rank]=(float)rank/(float)(z-1);\n'+old)
    old='for(int m=0;m<METHODS;m++)memset(b->scores[m],0,z*sizeof(*b->scores[m]));'
    assert text.count(old)==1
    text=text.replace(old,'memset(b->scores[4],0,z*sizeof(*b->scores[4]));')
    old='b->scores[4][b->ranking[rank].index]+=(float)rank/(float)(z-1);'
    assert text.count(old)==1
    text=text.replace(old,'b->scores[4][b->ranking[rank].index]+=b->scores[3][rank];')
    p.write_text(text)
    shutil.copyfile(RANK/'test_rank_fast.c',source/'test_rank_fast.c')


if __name__=='__main__':
    prepare()
    spec=importlib.util.spec_from_file_location('preplan_builder',PREPLAN/'build.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=ROOT;module.builder.ROOT=ROOT;module.builder.SOURCE=ROOT/'sources'
    records={}
    for target in ['host','sanitizer','arm']:
        record=module.build(target)
        path=ROOT/record['receipt'];receipt=json.loads(path.read_text());out=path.parent
        name='test_rank_fast_'+target
        command=module.builder.proposal_test_command(out,target,'test_rank_fast.c',name,target=='sanitizer')
        receipt['commands'].append(module.builder.run(command));receipt['binaries'][name]=module.builder.sha(out/name)
        if target!='arm':
            run=subprocess.run([str(out/name)],capture_output=True,text=True,check=True)
            receipt['units'].append({'binary':name,'executed':True,'stdout':run.stdout,'stderr':run.stderr})
        receipt.update(schema='arm-wave4-combined/v1',top4='exact four-pass selection with score gate before coordinate mapping',rank_values='precomputed exact float rank fractions')
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target]={'receipt':str(path.relative_to(ROOT)),'sha256':module.builder.sha(path)}
    (ROOT/'build-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
