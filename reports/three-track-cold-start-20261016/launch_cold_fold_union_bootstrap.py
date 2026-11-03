"""Controlled view-retention test: same training input, union of band bootstraps."""
import json,hashlib,sys
from pathlib import Path
from dataclasses import replace
import leo.cli.shared_fast_position as cli
from leo.contracts.digests import canonical_digest

fold=sys.argv[1];assert fold in ['early_to_late','late_to_early']
base=Path('/tmp/three-track-investigation')/('cold-fold-'+fold+'-v1')
dest=Path('/tmp/three-track-investigation')/('cold-fold-'+fold+'-union-v2')
if dest.exists():raise FileExistsError('Existing controlled-attempt namespace; inspect before relaunch')
payload=(base/'training-input.json').read_bytes();manifest=json.loads((base/'derivation.json').read_text())
assert hashlib.sha256(payload).hexdigest()==manifest['derived_input_sha256']
dest.mkdir();(dest/'training-input.json').write_bytes(payload)
manifest.update(scope='Controlled research-only bootstrap retention test. Identical training-input bytes, TLE snapshot and pipeline budgets as v1. Replace combined-view bootstrap retention with union of original low/high view tracks. No satellite hints, observation changes, production publication or RF collection.',bootstrap_policy='union-of-existing-low-high-bootstrap-tracks-v1',baseline_directory=str(base))
(dest/'derivation.json').write_text(json.dumps(manifest,indent=2)+'\n')
original=cli.prepare_views
def union_prepare(source):
    prepared,nodes=original(source);all_view=prepared['all'];ids={key:i for i,key in enumerate(all_view.observations.window_ids)}
    tracks=[]
    for view in ['low','high']:
        part=prepared[view]
        for track in part.bootstrap_tracks:
            mapped=tuple(ids[part.observations.window_ids[i]] for i in track)
            if mapped not in tracks:tracks.append(mapped)
    before=all_view.bootstrap_tracks;newtracks=tuple(tracks)
    digest=canonical_digest(dict(parent_evidence=all_view.evidence_sha256,bootstrap_policy=manifest['bootstrap_policy'],bootstrap_tracks=newtracks))
    prepared['all']=replace(all_view,bootstrap_tracks=newtracks,evidence_sha256=digest)
    assert prepared['all'].observations is all_view.observations
    proof=dict(policy=manifest['bootstrap_policy'],observations=len(all_view.observations.times_s),original_track_count=len(before),union_track_count=len(newtracks),original_bootstrap_rows=len(set().union(*(set(t) for t in before))),union_bootstrap_rows=len(set().union(*(set(t) for t in newtracks))),unchanged_observation_object=True,parent_evidence_sha256=all_view.evidence_sha256,new_evidence_sha256=digest)
    (dest/'bootstrap_retention_receipt.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof),flush=True)
    return prepared,nodes
cli.prepare_views=union_prepare
result=cli.run(dest/'training-input.json',dest/'output',maximum_seconds=480,tle_root=Path('/tmp/three-track-investigation/space-track-pipeline-rerun/pinned-tle'))
print(json.dumps({key:result.get(key) for key in ['state','reason','elapsed_seconds','position','selection']}),flush=True)
