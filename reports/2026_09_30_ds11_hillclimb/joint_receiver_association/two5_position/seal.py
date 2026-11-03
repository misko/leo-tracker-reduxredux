"""Freeze qualified training selections before loading geographic reference."""
import json
from common import HERE,JOBS,read,digest,verify_sources


def main():
    sources={str(p):digest(p) for p in (HERE/'seal.py',HERE/'PROTOCOL.md',HERE/'common.py')}
    cells=[]
    for cohort,index,family in JOBS:
        for arm in ('doppler','signed'):
            attempts=[]
            for seed in (0,1):
                stem=HERE/f'fit-{cohort}-{index:02d}-{arm}-{seed}';rp=stem.with_suffix('.receipt.json');receipt=read(rp);verify_sources(receipt)
                sources[str(rp)]=digest(rp);result=None
                if receipt['exit_code']==0:
                    path=stem.with_suffix('.json');result=read(path);verify_sources(result);sources[str(path)]=digest(path)
                    assert (result['cohort'],result['index'],result['arm'],result['seed'])==(cohort,index,arm,seed)
                attempts.append(dict(receipt=receipt,result=result))
            qualified=[a['result'] for a in attempts if a['result'] and a['result']['qualified']]
            cells.append(dict(cohort=cohort,index=index,family=family,arm=arm,attempts=attempts,selected=max(qualified,key=lambda r:r['score']) if qualified else None))
    result=dict(cells=cells,sources=sources,reference_used=False)
    with (HERE/'sealed.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(cells=len(cells),qualified_cells=sum(c['selected'] is not None for c in cells))))


if __name__=='__main__':main()
