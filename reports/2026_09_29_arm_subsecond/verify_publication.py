#!/usr/bin/env python3
"""Verify receipt sources and content-addressed archives in a staged tree."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;CHECKOUT=ROOT.parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
index=json.loads((ROOT/'publication-index.json').read_text());failed=[];checks=0
for identity,record in index['archives'].items():
    archive=CHECKOUT/record['path'];checks+=1
    if sha(archive)!=record['sha256']:failed.append(f'archive:{identity}');continue
    with tarfile.open(archive,'r:gz') as stream:
        members={m.name:m for m in stream.getmembers() if m.isfile()}
        for name,expected in record['files'].items():
            checks+=1;item=members.get(name);handle=stream.extractfile(item) if item else None
            actual=hashlib.sha256(handle.read()).hexdigest() if handle else None
            if actual!=expected:failed.append(f'{identity}:{name}')
for original,record in index['receipts'].items():
    checks+=1;receipt=CHECKOUT/record['published_path']
    if not receipt.is_file() or sha(receipt)!=record['receipt_sha256']:failed.append(f'receipt:{original}')
print(json.dumps({'passed':not failed,'checks':checks,'failed':failed},indent=2))
if failed:raise SystemExit(1)
