"""Read only: inspect the first segment of each fast acquisition."""
import json
import hashlib
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
paths={
    'DS24':Path('/srv/bulk/leo/research/ds24-20261024-extension/manifest.json'),
    'DS26':Path('/srv/bulk/leo/research/ds26-20261030/dataset/manifest.json'),
    'DS27':Path('/srv/bulk/leo/research/ds27-algo04-20261031/dataset/manifest.json'),
    'DS28':ROOT/'2026_11_01_ds28_revision2/dataset/manifest.json'}
out={}
for ds,path in paths.items():
    configurations={};counts=Counter();failures=[]
    for member in json.loads(path.read_text())['members']:
        if not member['recording_id'].startswith('fast8-'):
            continue
        try:
            segment=Path(member['raw_recording']['segments'][0]['path'])
            m=json.loads(segment.read_text())
            config=m['configuration']
            sha=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
            configurations[sha]=config;counts[sha]+=1
        except (OSError,KeyError,IndexError) as exc:
            failures.append({'recording':member['recording_id'],'reason':str(exc)})
    out[ds]={'counts':dict(counts),'configurations':configurations,'failures':failures}
print(json.dumps(out,indent=2))
