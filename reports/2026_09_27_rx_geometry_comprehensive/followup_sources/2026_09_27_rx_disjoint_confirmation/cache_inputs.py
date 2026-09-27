"""Read-only public input loading for the already-frozen four-recording cohort."""
import json
from pathlib import Path
import pickle
import sys
from select_cohort import sha

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_27_roof_geometry_confirmation'))
from select_confirmation import validate_pose


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    target=HERE/'inventory.json'
    if target.exists():raise FileExistsError(target)
    manifest=json.loads((HERE/'manifest.json').read_text())
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    captures=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    cache=HERE/'cache';cache.mkdir(exist_ok=True)
    inventory=[]
    try:
        for item in manifest['sessions']:
            pose=item['pose'];sid=item['capture']['session_id'];validate_pose(pose)
            cap=captures.inspect(sid)
            if cap.manifest_sha256!=item['capture']['manifest_sha256'] or pose['manifest_sha256']!=cap.manifest_sha256:
                raise ValueError('manifest mismatch')
            raw=store.load(sid)
            if not raw.qualified or raw.input_manifest_sha256!=cap.manifest_sha256:raise ValueError('unqualified/mismatched source')
            expected={e.visit_index for e in cap.manifest.receipt.events}
            if {p.visit_index for p in raw.probes}!=expected:raise ValueError('incomplete visits')
            probes={(p.visit_index,p.probe_index,p.receiver_id):p for p in raw.probes}
            if len(probes)!=len(raw.probes):raise ValueError('duplicate probes')
            for p in raw.probes:
                other=probes.get((p.visit_index,p.probe_index,1-p.receiver_id))
                if other is None or any(getattr(p,k)!=getattr(other,k) for k in ('channel','edge','valid_start_counter','probe_start_ms')):
                    raise ValueError('unpaired receiver opportunity')
            payload=pickle.dumps(raw,protocol=5);path=cache/f'{sid}.pickle'
            if path.exists():
                if path.read_bytes()!=payload:raise ValueError('cache changed')
            else:
                with path.open('xb') as stream:stream.write(payload)
            inventory.append({'session_id':sid,'ready':True,'input_manifest_sha256':cap.manifest_sha256,
                'analysis_manifest_sha256':raw.analysis_manifest_sha256,'sample_rate_hz':raw.sample_rate_hz,
                'cache_file':str(path),'cache_sha256':sha(payload),'visits':len(expected)})
            print('CACHED',sid,len(expected),flush=True)
        with target.open('x') as stream:json.dump(inventory,stream,indent=2);stream.write('\n')
    finally:store.close();captures.close()


if __name__=='__main__':main()
