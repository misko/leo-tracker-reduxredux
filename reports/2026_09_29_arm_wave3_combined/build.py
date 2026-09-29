"""Combine measured resampling, rank-only magnitude and .1 boundary gating."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT.parent
BASE = REPORTS/'2026_09_29_arm_resampled_omit_fused'
RANK = REPORTS/'2026_09_29_arm_rank_only_proposal/builds/host'
GATE = REPORTS/'2026_09_29_arm_boundary_gate/variants/100/builds-v4/host'


def prepare():
    source = ROOT/'sources'
    assert not source.exists()
    shutil.copytree(BASE/'sources', source)
    for name in ['full_search.c', 'test_boundary_margin_allowed.c']:
        shutil.copyfile(GATE/name, source/name)
    shutil.copyfile(RANK/'test_rank_only.c', source/'test_rank_only.c')
    rank = (RANK/'proposal_core.c').read_text()
    helper = rank[rank.index('static float rank_squared_magnitude'):rank.index('static void correlate')]
    p = source/'proposal_core.c'
    text = p.read_text()
    assert text.count('static void correlate') == 1
    text = text.replace('static void correlate', helper+'static void correlate')
    old = 'hypotf(b->corr[k][0],b->corr[k][1])*scale'
    assert text.count(old) == 1
    text = text.replace(old, 'rank_squared_magnitude(b->corr[k][0],b->corr[k][1],scale)')
    for arr in ['scores[m]', 'b->scores[m]']:
        old = (f'float lo={arr}[0],hi=lo;for(size_t k=1;k<z;k++){{'
               f'if({arr}[k]<lo)lo={arr}[k];if({arr}[k]>hi)hi={arr}[k];}}'
               'if(hi-lo<=16*FLT_EPSILON*fmaxf(fmaxf(fabsf(lo),fabsf(hi)),1.0f))continue;')
        assert text.count(old) == 1
        text = text.replace(old, f'if(rank_feature_flat({arr},z))continue;')
    p.write_text(text)
    return source


if __name__ == '__main__':
    spec = importlib.util.spec_from_file_location('combined_builder', BASE/'build.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.ROOT = ROOT
    builder.SOURCE = prepare()
    records = {}
    for target in ['host', 'sanitizer', 'arm']:
        record = builder.build(target)
        path = ROOT/record['receipt']
        receipt = json.loads(path.read_text())
        out = path.parent
        for src, stem, proposal in [('test_rank_only.c','test_rank_only',True),
                                    ('test_boundary_margin_allowed.c','test_boundary_margin_allowed',False)]:
            name = stem+'_'+target
            command = (builder.proposal_test_command(out,target,src,name,target=='sanitizer') if proposal
                       else builder.link_command(out,target,[src],name,target=='sanitizer',0))
            receipt['commands'].append(builder.run(command))
            receipt['binaries'][name] = builder.sha(out/name)
            if target != 'arm':
                run = subprocess.run([str(out/name)],capture_output=True,text=True,check=True)
                receipt['units'].append({'binary':name,'executed':True,'stdout':run.stdout,'stderr':run.stderr})
        receipt.update(schema='arm-wave3-combined/v1', boundary_min_margin=.1,
                       proposal_magnitude='normalized squared magnitude, magnitude-space flat gate')
        path.write_text(json.dumps(receipt,indent=2)+'\n')
        records[target] = {'receipt':str(path.relative_to(ROOT)),'sha256':builder.sha(path)}
    (ROOT/'build-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
