"""Training-only selection for all crossed diagnostic cells."""
import json
from pathlib import Path
from fixed_model import digest,read
HERE=Path(__file__).resolve().parent


def main():
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'PROTOCOL.md')};rows=[]
    for i in (22,23):
        for states in ('original','offline'):
            for labels in ('original','offline'):
                attempts=[]
                for start in ('iid','center'):
                    path=HERE/f'fit-{i:02d}-{states}-{labels}-{start}.json';rp=path.with_suffix('.receipt.json');receipt=read(rp);sources[str(rp)]=digest(rp)
                    assert receipt['log_sha256']==digest(path.with_suffix('.log'))
                    for p,h in receipt['sources'].items():assert digest(p)==h,p
                    if receipt['exit_code'] or not path.exists():attempts.append(dict(start=start,qualified=False,exit_code=receipt['exit_code']));continue
                    fit=read(path)
                    for p,h in fit['sources'].items():assert digest(p)==h,p
                    sources[str(path)]=digest(path);attempts.append(dict(path=str(path),start=start,qualified=fit['qualified'],score=fit['score']))
                good=[a for a in attempts if a['qualified']]
                rows.append(dict(index=i,states=states,labels=labels,attempts=attempts,selected=max(good,key=lambda a:a['score']) if good else None))
    with (HERE/'sealed.json').open('x') as f:json.dump(dict(rows=rows,sources=sources,reference_used=False),f,indent=2,allow_nan=False)
    print(json.dumps(dict(cells=len(rows),qualified_cells=sum(r['selected'] is not None for r in rows),qualified_starts=sum(a['qualified'] for r in rows for a in r['attempts']))))


if __name__=='__main__':main()
