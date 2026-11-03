"""Seal training-score selections from all terminal receipts before geography."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def choose(attempts):
    qualified=[r for r in attempts if r.get('qualified')]
    return max(qualified,key=lambda r:r['score']) if qualified else None


def main():
    selection=json.loads((HERE/'selection.json').read_text());sources={str(p):digest(p) for p in (Path(__file__),HERE/'selection.json',HERE/'PROTOCOL.md')};rows=[]
    for index in selection['selected']:
        for arm in ('original','offline'):
            attempts=[]
            for start in ('iid','center'):
                path=HERE/f'fit-{index:02d}-{arm}-{start}.json';rp=path.with_suffix('.receipt.json');receipt=json.loads(rp.read_text());sources[str(rp)]=digest(rp)
                assert digest(path.with_suffix('.log'))==receipt['log_sha256']
                for p,h in receipt['sources'].items():assert digest(p)==h,p
                if receipt['exit_code'] or not path.exists():attempts.append(dict(start=start,qualified=False,exit_code=receipt['exit_code']));continue
                fit=json.loads(path.read_text());sources[str(path)]=digest(path)
                for p,h in fit['sources'].items():assert digest(p)==h,p
                attempts.append(dict(start=start,path=str(path),qualified=fit['qualified'],score=fit['score']))
            rows.append(dict(index=index,arm=arm,attempts=attempts,selected=choose(attempts)))
    with (HERE/'sealed.json').open('x') as f:json.dump(dict(rows=rows,sources=sources,reference_used=False),f,indent=2,allow_nan=False)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
