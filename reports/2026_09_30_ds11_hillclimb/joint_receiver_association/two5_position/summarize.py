"""Read geographic reference only after all training selections are sealed."""
import importlib.util
import json
import numpy as np
from common import HERE,JOBS,base,read,digest,verify_sources
from load import load
from gate import assess


def main():
    sp=HERE/'sealed.json';sealed=read(sp);verify_sources(sealed)
    source=base('original')/'summarize.py'
    spec=importlib.util.spec_from_file_location('two5_geographic_reference',source);reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
    sources={str(p):digest(p) for p in (sp,source,HERE/'summarize.py',HERE/'gate.py',HERE/'PROTOCOL.md')};rows=[]
    cells={(r['cohort'],r['index'],r['arm']):r for r in sealed['cells']}
    for cohort,index,family in JOBS:
        op=base(cohort)/f'runs/{index:02d}_iid.json';original=read(op)['selected'];sources[str(op)]=digest(op)
        row=dict(cohort=cohort,index=index,family=family,original_iid=dict(qualified=original is not None and original['qualified'],error_m=reference.distance(original['estimate_deg']) if original is not None and original['qualified'] else None))
        for arm in ('doppler','signed'):
            selected=cells[cohort,index,arm]['selected']
            row[arm]=dict(qualified=selected is not None,error_m=None)
            if selected is None:continue
            model,_,_,bound=load(cohort,index,arm);sources.update(bound);x=np.array(selected['x'])
            training=model.evaluate(x,gradient=False)['score'];joint=model.evaluate(x,gradient=False,held=True)['score']
            assert abs(training-selected['score'])<1e-7
            row[arm].update(error_m=reference.distance(selected['coordinates_deg']),score=training,held_score=joint-training,x=selected['x'])
        rows.append(row)
    out=dict(rows=rows,families=assess(rows),sources=sources,scope='exposed-site conditional whole-source pilot; unsurveyed reference',
             causal_position_improvement_established=False)
    with (HERE/'summary.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(dict(rows=rows,families=out['families']),indent=2))


if __name__=='__main__':main()
