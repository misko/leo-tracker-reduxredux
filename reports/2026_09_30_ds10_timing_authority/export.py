import hashlib
import inspect
import json
from pathlib import Path


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    here=Path(__file__).resolve().parent
    path=here.parent/'2026_09_30_ds10_scale_weighting/plan.json'
    plan=json.loads(path.read_text());store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    rows=[];hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest()};runtime={}
    for i,entry in enumerate(plan['inputs']):
        artifact=next(a for a in entry['artifacts'] if a['kind']=='observations')
        obs_path=Path(artifact['path']);payload=obs_path.read_bytes();digest=hashlib.sha256(payload).hexdigest()
        assert 'sha256:'+digest==artifact['sha256'];hashes[str(obs_path)]=digest
        obs=json.loads(payload);capture=store.inspect(entry['session_id'])
        assert capture.manifest_sha256==obs['manifest_sha256']==entry['manifest_sha256']
        t=capture.manifest.timing
        rows.append(dict(session_id=entry['session_id'],manifest_sha256=capture.manifest_sha256,
                         observation_start_utc_ns=obs['start_utc_ns'],fitted_tau_s=plan['baseline']['x'][i+2],
                         timing=t.model_dump(mode='json') if t else None,
                         terminal=capture.manifest.receipt.terminal.model_dump(mode='json')))
        if t:
            p=Path(inspect.getfile(type(t)));runtime[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    assert [r['session_id'] for r in rows]==plan['sessions'] and len(rows)==24
    p=Path(inspect.getfile(AdaptiveHopIqStore));runtime[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    print(json.dumps(dict(rows=rows,hashes=hashes,runtime=runtime),indent=2))


if __name__=='__main__':main()
