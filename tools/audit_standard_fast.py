"""Verify every completed ALGO07 result and its eight live Web UI PNGs."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from PIL import Image
from leo.contracts.fast_graph_position_v6 import owners
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore, RENDER_REVISION
from leo.storage.graph_position_view_v6 import completed_view
from render_standard_fast import sha


def audit(bulk_root, base_url):
    source=FastGraphPositionStoreV6(bulk_root)
    target=FastStandardAnalysisStore(bulk_root)
    receipts=[]
    for job in source.completed_jobs():
        run=job['run_id'];evidence=source.plot_evidence(job);terminal=evidence['terminal']
        scientific=owners(terminal);view=completed_view(run,terminal)
        path=f'{base_url}/api/v2/fast-scans/{quote(run)}/standard-analysis'
        with urlopen(path,timeout=30) as response:
            document=json.load(response)
        assert document==target.detail(run), f'{run}: API/store mismatch'
        assert document['state']=='complete' and document['renderer_revision']==RENDER_REVISION
        assert document['terminal_sha256']==evidence['terminal_receipt']['sha256']
        assert document['input_sha256']==job['input_sha256']
        assert document['observations_sha256']==evidence['observation_sha256']
        assert document['tracks_sha256']==evidence['tracks_sha256']
        assert document['glrt_points']==len(evidence['observations'])
        assert terminal['future_TLE_used'] is False
        for arm in ('c0','fitted_c'):
            row=document['arms'][arm]
            endpoint=view['selected']['arms'][arm]['endpoint_latlon']
            assert row['endpoint_latlon']==endpoint, f'{run}/{arm}: endpoint changed'
            assert row['owner_sha256']==sha(scientific[arm])
            assert row['associated_points']==len(scientific[arm])
            assert abs(document['objective_replay'][arm])<=1e-4
        artifacts=[]
        for entry in document['artifacts']:
            url=f'{path}/{quote(entry["name"])}.png?sha256={quote(entry["sha256"],safe="")}'
            with urlopen(url,timeout=30) as response:
                data=response.read()
                assert 'immutable' in response.headers['Cache-Control']
                assert response.headers['Content-Type']=='image/png'
            digest='sha256:'+hashlib.sha256(data).hexdigest()
            assert digest==entry['sha256'] and len(data)==entry['byte_count']
            with Image.open(BytesIO(data)) as image:
                dimensions=list(image.size);image.verify()
            artifacts.append(dict(name=entry['name'],sha256=digest,dimensions=dimensions,byte_count=len(data)))
        receipts.append(dict(run_id=run,terminal_sha256=document['terminal_sha256'],
            objective_replay=document['objective_replay'],arms=document['arms'],artifacts=artifacts))
    return dict(state='passed',renderer_revision=RENDER_REVISION,scans=len(receipts),
                PNGs=sum(len(r['artifacts']) for r in receipts),results=receipts)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-root',type=Path,required=True)
    parser.add_argument('--base-url',default='http://localhost:8090')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();receipt=audit(args.bulk_root,args.base_url.rstrip('/'))
    args.output.write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='results'}))
