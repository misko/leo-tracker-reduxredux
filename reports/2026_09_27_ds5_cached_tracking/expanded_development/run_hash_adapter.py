"""Preserve the manifest hash prefix required by the development IQ loader."""
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('expanded_replay_hash_adapter_parent',HERE/'replay.py')
original=importlib.util.module_from_spec(spec);sys.modules[spec.name]=original;spec.loader.exec_module(original)
original_descriptor=original.descriptor


def descriptor(row):
    return replace(original_descriptor(row),raw_sha256=row['raw_npy']['sha256'])


def run():
    lock=json.loads((HERE/'source_lock.json').read_text())
    hashes=dict(lock['files'])
    assert all(original.study.digest(p)==h for p,h in hashes.items())
    for path in (Path(__file__).resolve(),HERE/'test_hash_adapter.py',HERE/'results.json'):
        hashes[str(path)]=original.study.digest(path)
    original.write(HERE/'hash_adapter_lock.json',{'files':hashes,'correction':'Restore manifest hash prefix; no detector or membership change.'})
    write=original.write
    def adapted_write(path,value):
        assert all(original.study.digest(p)==h for p,h in hashes.items())
        if path.name=='source_lock.json':
            assert value==lock
            return
        assert path.name=='results.json'
        value['hash_adapter_lock_sha256']=original.study.digest(HERE/'hash_adapter_lock.json')
        write(HERE/'results.hash_adapter.json',value)
    original.descriptor=descriptor
    original.write=adapted_write
    original.run()


if __name__=='__main__':run()
