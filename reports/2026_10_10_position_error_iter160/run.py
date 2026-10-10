"""One serial public metadata load per member; no IQ or numerical model ports."""
import importlib.util
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def main():
    plan=json.loads((HERE/'protocol.json').read_text())
    freezer=module('freeze160',HERE/'freeze.py')
    base=module('run155_for160',HERE.parent/'2026_10_10_position_error_iter155/run.py')
    base.verify(plan,freezer.POLICY)
    from leo.contracts.digests import canonical_digest
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    prep=module('preparation160',HERE/'preparation.py')
    if prep.SEED!=plan['policy']['seed']:raise ValueError('fold seed differs')
    digest=canonical_digest(plan);folder=HERE/'results';folder.mkdir(exist_ok=True)
    for member in plan['members']:
        label=member['label'];path=folder/(label+'.json');claim=folder/(label+'.claim.json')
        identity=dict(label=label,protocol_sha256=digest)
        if path.exists():
            old=json.loads(path.read_text());old_claim=json.loads(claim.read_text())
            if any(old.get(k)!=v or old_claim.get(k)!=v for k,v in identity.items()) or old.get('status') not in ('complete','failed'):
                raise ValueError('foreign/nonterminal existing receipt')
            continue
        with claim.open('x') as stream:json.dump(identity,stream)
        begun=time.monotonic();row=dict(identity,status='failed',source_loads=0)
        try:
            support=json.loads((ROOT/member['support_path']).read_text())['support']
            store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
            try:
                row['source_loads']+=1
                source=store.load(member['binding']['session_id'])
            finally:store.close()
            row['groups']=prep.join(support,source,member['binding'])
            row['status']='complete'
        except Exception as error:row['error']=repr(error)
        row['elapsed_s']=time.monotonic()-begun
        with path.open('x') as stream:json.dump(row,stream,indent=2,allow_nan=False)
        print(label,row['status'],flush=True)


if __name__=='__main__':main()
