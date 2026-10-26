"""Create compact saved-result views and a lean exact-byte manifest."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def compact(value):
    if isinstance(value,list):return [compact(v) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for k,v in value.items():
        if k.endswith('observation_ids') or k=='observation_ids':
            result[k+'_count']=len(v);result[k+'_sha256']=digest(v)
        elif k in ('conditional_residual_hz','residual_hz') and isinstance(v,list):
            result[k+'_count']=len(v);result[k+'_sha256']=digest(v)
        else:result[k]=compact(v)
    return result


def main():
    if (HERE/'lean_publication.json').exists():raise FileExistsError('manifest already complete')
    for case in ('DS24-0010','DS24-0011'):
        for arm in ('c0','fitted_c'):
            for cell in ('01','10'):
                path=HERE/case/arm/cell
                raw=read(path/'raw_endpoint.json');gates=read(path/'gates.json')
                raw['summary'].pop('history',None)
                raw['summary'].pop('gates',None);raw['summary'].pop('linear_gates',None)
                write(HERE/'compact'/case/arm/(cell+'.json'),dict(raw_endpoint=compact(raw),gates=compact(gates),
                    raw_source_path=str(path/'raw_endpoint.json'),raw_source_sha256=sha(path/'raw_endpoint.json'),
                    gates_source_path=str(path/'gates.json'),gates_source_sha256=sha(path/'gates.json')))
    files=[p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py','.md','.json') and p.name not in ('lean_publication.json',)]
    files +=[p for name in ('compact','rf_report','geographic') for p in (HERE/name).rglob('*') if p.is_file()]
    published=[dict(path=str(p.relative_to(HERE)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(set(files))]
    included={str(p) for p in files};external={}
    for source in (HERE/'protocol.json',HERE/'RF_seal.json'):
        external.update({p:h for p,h in read(source)['files'].items() if p not in included})
    write(HERE/'lean_publication.json',dict(schema='lean-scientific-publication/v1',root=str(HERE),published=published,
        published_files=len(published),published_bytes=sum(x['bytes'] for x in published),
        external_inputs=[dict(path=p,sha256=h) for p,h in sorted(external.items())],
        excluded_large_local_arrays_and_raw_ledgers_are_hash_bound=True,full_replay_requires_external_inputs=True))
    print(json.dumps(dict(files=len(published),bytes=sum(x['bytes'] for x in published),external=len(external))))


if __name__=='__main__':main()
