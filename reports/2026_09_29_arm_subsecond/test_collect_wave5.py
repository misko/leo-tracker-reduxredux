import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('collect_wave5',HERE/'collect_wave5.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def make_build(root):
    root.mkdir();(root/'runner').write_bytes(b'binary');(root/'unit.c').write_bytes(b'source')
    receipt={'binaries':{'runner':hashlib.sha256(b'binary').hexdigest()},'sources':{'unit.c':hashlib.sha256(b'source').hexdigest()}}
    path=root/'build-receipt.json';path.write_text(json.dumps(receipt));return path

def test_validate_receipt_rejects_changed_binary(tmp_path):
    receipt=make_build(tmp_path/'build');copied=tmp_path/'copied.json';copied.write_bytes(receipt.read_bytes())
    summary={'build_sha256':module.sha(receipt),'binary_sha256':module.sha(receipt.parent/'runner')}
    assert module.validate_receipt(summary,copied,receipt)['source_files_verified']==1
    (receipt.parent/'runner').write_bytes(b'changed')
    try: module.validate_receipt(summary,copied,receipt)
    except AssertionError: pass
    else: raise AssertionError('changed binary accepted')
