"""Record final artifact/input receipts without repeating any fitting."""
import hashlib
import json
from pathlib import Path
import time
import joint as j


def main():
    protocol=j.read(j.OUT/'protocol.json');sources={};summary=[]
    for case in protocol['cases']:
        root=j.ev.ROOTS[case[:4]];z=j.read(root/'inputs'/(case+'.json'));native=Path(z['native_path'])/'observations.json'
        sources[case]=dict(native_observations=dict(path=str(native),sha256=j.sha(native)),
            published_ownership_sha256=hashlib.sha256(json.dumps(z['baseline_owners'],sort_keys=True).encode()).hexdigest(),
            causal_ledger_sha256=j.sha(j.OUT/'ledgers'/case/'tle-ledger.json'))
        result=j.read(j.OUT/case/'result.json');summary.append(dict(case=case,selected=result['selected'],
            final_error_m={a:result['final'][a]['error_m'] for a in j.ARMS},production_changed=False))
    j.write(j.OUT/'summary.json',summary)
    files={}
    for path in sorted(j.OUT.rglob('*')):
        if not path.is_file() or path.name in ['run_manifest.json','publication_manifest.json']:continue
        if path.suffix=='.json':
            json.loads(path.read_text(),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON '+str(path))))
        files[str(path.relative_to(j.OUT))]=dict(bytes=path.stat().st_size,sha256=j.sha(path))
    j.write(j.OUT/'run_manifest.json',dict(revision=protocol['revision'],finalized_utc_ns=time.time_ns(),
        frozen_protocol_sha256=j.sha(j.OUT/'protocol.json'),native_and_ownership=sources,
        sources=protocol['cases'],files=files,production_changed=False))
    selected={}
    for name,record in files.items():
        path=Path(name)
        if path.suffix=='.npz' or 'ledgers' in path.parts or path.name=='curves.json':continue
        if path.name.endswith('fits.json') and record['bytes']>10000:continue
        if path.name=='publication_manifest.json':continue
        selected[name]=record
    selected['run_manifest.json']=dict(bytes=(j.OUT/'run_manifest.json').stat().st_size,sha256=j.sha(j.OUT/'run_manifest.json'))
    j.write(j.OUT/'publication_manifest.json',dict(report_sha256=j.sha(j.OUT/'report.md'),files=selected,
        total_bytes=sum(r['bytes'] for r in selected.values()),policy='Exclude NPZ/native arrays, large exact-fit records and full causal ledgers; retain references and hashes in run_manifest.json'))
    print('Validated',len(files),'finite artifacts; preserved fallback for',len(summary),'cases')


if __name__=='__main__':main()
