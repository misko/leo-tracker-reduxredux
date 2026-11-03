"""Read-only corpus staging for local-IQ replay (maintained-server environment).

This evaluation adapter is not a runtime dependency. Each exported visit must
match the prior independently inventoried bytes before it is published locally.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',required=True,type=Path)
    parser.add_argument('--session',required=True)
    parser.add_argument('--manifest-digest',required=True)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    inventory=json.loads(args.inventory.read_text())
    if [r['visit'] for r in inventory]!=list(range(len(inventory))):
        raise ValueError('inventory visits are not contiguous')
    args.output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic();entries=[]
    store=AdaptiveHopIqStore('/srv/bulk/leo',read_only=True)
    try:
        session=store.inspect(args.session)
        if session.manifest_sha256!=args.manifest_digest:
            raise ValueError('capture digest differs')
        manifest=session.manifest.model_dump(mode='json')
        if len(manifest['receipt']['events'])!=len(inventory):
            raise ValueError('inventory does not cover full capture')
        (args.output/'capture-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        with store.reader(args.session,expected=session) as reader:
            for row in inventory:
                if time.monotonic()-started>300:raise TimeoutError('bounded corpus export exceeded 300s')
                visit,values=reader.read_visit_ci16(row['visit'])
                if visit.event.model_dump(mode='json')!=row['event']:
                    raise ValueError('visit authority differs')
                raw=np.asarray(values,dtype='<i2',order='C').tobytes()
                if hashlib.sha256(raw).hexdigest()!=row['raw_sha256']:
                    raise ValueError('IQ differs from independent inventory')
                path=args.output/f"visit-{row['visit']:06d}.ci16"
                path.write_bytes(raw)
                entries.append(dict(row,path=path.name,size_bytes=len(raw)))
                if len(entries)%256==0:print(json.dumps({'exported':len(entries)}),flush=True)
        (args.output/'inventory.json').write_text(json.dumps(entries,indent=2)+'\n')
        (args.output/'inputs.sha256').write_text(''.join(f"{r['raw_sha256']}  {r['path']}\n" for r in entries))
        receipt={'status':'complete','session':args.session,'capture_digest':args.manifest_digest,
                 'visits':len(entries),'bytes':sum(r['size_bytes'] for r in entries),
                 'source_inventory_sha256':hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
                 'wall_s':time.monotonic()-started,'scope':'Read-only recorded IQ staging; no RF'}
        (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt))
    finally:store.close()


if __name__=='__main__':main()
