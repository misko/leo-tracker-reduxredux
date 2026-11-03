import hashlib
import json
from pathlib import Path
from model import transfer
HERE=Path(__file__).resolve().parent
JOBS=[(2,16,17),(3,18,20),(4,7,11),(5,4,19),(6,0,10),(7,5,14)]


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    sources={str(p):digest(p) for p in (Path(__file__),HERE/'model.py',HERE/'PROTOCOL.md')};rows=[]
    for family,cal,val in JOBS:
        docs=[]
        for index in (cal,val):
            path=HERE/f'export-{index:02d}.receipt.json';receipt=json.loads(path.read_text());sources[str(path)]=digest(path)
            assert digest(HERE/f'export-{index:02d}.log')==receipt['log_sha256']
            for p,h in receipt['sources'].items():assert digest(p)==h,p
            if receipt['exit_code']!=0:docs.append(None);continue
            path=HERE/f'input-{index:02d}.json';doc=json.loads(path.read_text());sources[str(path)]=digest(path)
            for p,h in doc['sources'].items():assert digest(p)==h,p
            docs.append(doc)
        outcome=dict(passed=False,qualified=False,reason='export_failed') if any(d is None for d in docs) else transfer(docs[0]['groups'],docs[1]['groups'])
        rows.append(dict(family=family,calibration=cal,validation=val,**outcome))
    result=dict(families=rows,sources=sources,position_improvement_established=False)
    with (HERE/'summary.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('predicted_validation_slope','cyclic_shift_errors')} for r in rows],indent=2))


if __name__=='__main__':main()
