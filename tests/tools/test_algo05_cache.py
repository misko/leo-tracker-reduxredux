import json
import pytest
from algo05_cache import digest,relocate

def test_nested_historical_export_is_exact_but_active_hash_edges_rebase(tmp_path):
    src=tmp_path/'src';src.mkdir();(src/'source-export').mkdir()
    historical=src/'source-export/descriptor.json'
    historical.write_text(json.dumps(dict(root='/previous/runtime',files={'bank.npz':'a'*64})))
    active=src/'protocol.json';active.write_text(json.dumps({'root':'/active','proof':{'/active/source-export/descriptor.json':digest(historical)}}))
    files={str(p.relative_to(src)):digest(p) for p in src.rglob('*.json')}
    out=tmp_path/'out';relocate(src,out,'/active',files)
    assert (out/'source-export/descriptor.json').read_bytes()==historical.read_bytes()
    assert json.loads((out/'protocol.json').read_text())['proof']=={str(out/'source-export/descriptor.json'):digest(historical)}
    historical.write_text('changed')
    with pytest.raises(ValueError,match='bytes changed'):relocate(src,tmp_path/'bad','/active',files)

def test_active_broken_snapshot_cannot_be_hidden(tmp_path):
    src=tmp_path/'src';src.mkdir();p=src/'descriptor.json'
    p.write_text(json.dumps(dict(root='/active/missing',files={'bank.npz':'a'*64})))
    with pytest.raises(ValueError,match='missing'):relocate(src,tmp_path/'out','/active',{'descriptor.json':digest(p)})
