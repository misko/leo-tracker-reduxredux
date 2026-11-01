import json
import pytest
from algo06_cache import relocate,digest

def test_nested_exports_remain_opaque_but_active_receipts_relocate(tmp_path):
    source=tmp_path/'source';historical=source/'current/source-export/descriptor.json'
    historical.parent.mkdir(parents=True)
    historical.write_text(json.dumps(dict(root='/old/recovery',files={'unavailable-original.json':'a'*64})))
    active=source/'current/protocol.json'
    active.write_text(json.dumps({'proof':{'/active/current/source-export/descriptor.json':digest(historical)}}))
    files={str(p.relative_to(source)):digest(p) for p in source.rglob('*.json')}
    out=tmp_path/'out';relocate(source,out,'/active',files)
    assert (out/'current/source-export/descriptor.json').read_bytes()==historical.read_bytes()
    assert json.loads((out/'current/protocol.json').read_text())['proof']=={str(out/'current/source-export/descriptor.json'):digest(historical)}
    historical.write_text('corrupt')
    with pytest.raises(ValueError,match='bytes changed'):relocate(source,tmp_path/'bad','/active',files)

def test_active_missing_snapshot_still_fails(tmp_path):
    source=tmp_path/'source';source.mkdir();p=source/'descriptor.json'
    p.write_text(json.dumps(dict(root='/active/missing',files={'bank.npz':'a'*64})))
    with pytest.raises(ValueError,match='missing'):relocate(source,tmp_path/'out','/active',{'descriptor.json':digest(p)})
