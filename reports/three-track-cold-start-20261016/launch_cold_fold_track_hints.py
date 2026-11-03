"""Training-only use of the user's three supplied coherent trajectory groups."""
import json,hashlib,sys
from pathlib import Path
from dataclasses import replace
import numpy as np
import leo.cli.shared_fast_position as cli
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.contracts.digests import canonical_digest

fold=sys.argv[1];assert fold in ['early_to_late','late_to_early']
base=Path('/tmp/three-track-investigation')/('cold-fold-'+fold+'-v1')
dest=Path('/tmp/three-track-investigation')/('cold-fold-'+fold+'-hints-v3')
if dest.exists():raise FileExistsError('Existing attempt namespace; inspect its live process/terminal before relaunch')
manifest=json.loads((base/'derivation.json').read_text());payload=(base/'training-input.json').read_bytes();assert hashlib.sha256(payload).hexdigest()==manifest['derived_input_sha256']
full=cli.load_input(json.loads(Path('/srv/bulk/leo/fast-scan-tracking-inputs/fast-9571943d3dccdf4f327e1346d1bf34b8.json').read_text()))
winners={}
for p in project_scanner_candidates(full):
    old=winners.get(p.source_group_id)
    if old is None or (-p.margin,p.candidate_rank,p.candidate_id)<(-old.margin,old.candidate_rank,old.candidate_id):winners[p.source_group_id]=p
points=sorted(winners.values(),key=lambda p:(p.support_center_utc_ns,p.source_group_id));hints=[]
for target in manifest['targets']:
    hints.append((target['track'],{points[i].source_group_id for i in target['training_rows']}))
dest.mkdir();(dest/'training-input.json').write_bytes(payload)
manifest.update(scope='Research-only supplied-track experiment. Same training input bytes as v1; add only training halves of the three predeclared user-identified trajectory groups to bootstrap evidence. Satellite identities, timing corrections and withheld measurements are not supplied. This does not test blind track extraction.',bootstrap_policy='supplied-training-track-groups-v1',baseline_directory=str(base))
(dest/'derivation.json').write_text(json.dumps(manifest,indent=2)+'\n')
original=cli.prepare_views
def hint_prepare(source):
    prepared,nodes=original(source);proof=[]
    for view in ['all','low','high']:
        item=prepared[view];obs=item.observations;hint_rows=[];records=[]
        for label,ids in hints:
            rows=np.array([i for i,key in enumerate(obs.window_ids) if key in ids])
            if not len(rows):continue
            assert len(rows)==len(ids)
            t=obs.times_s[rows];values=np.unwrap(obs.measured_hz[rows]*2*np.pi/(1/4.4e-6))*(1/4.4e-6)/(2*np.pi)
            rr=values-np.polyval(np.polyfit(t-t.mean(),values,2),t-t.mean());rms=float(np.sqrt(np.mean(rr**2)))
            assert len(rows)>=8 and np.ptp(t)>=4 and rms<=400
            hint_rows.append(tuple(rows.tolist()));records.append(dict(track=label,count=len(rows),span_s=float(np.ptp(t)),raw_quadratic_rms_hz=rms))
        if not hint_rows:continue
        used=set().union(*(set(rows) for rows in hint_rows));assert len(used)==sum(map(len,hint_rows))
        retained=[track for track in item.bootstrap_tracks if not set(track)&used]
        tracks=tuple(hint_rows+retained)
        digest=canonical_digest(dict(parent_evidence=item.evidence_sha256,bootstrap_policy=manifest['bootstrap_policy'],bootstrap_tracks=tracks))
        prepared[view]=replace(item,bootstrap_tracks=tracks,evidence_sha256=digest)
        assert prepared[view].observations is item.observations
        proof.append(dict(view=view,observations=len(obs.times_s),original_tracks=len(item.bootstrap_tracks),modified_tracks=len(tracks),training_hints=records,unchanged_observation_object=True,parent_evidence_sha256=item.evidence_sha256,new_evidence_sha256=digest))
    (dest/'bootstrap_track_hints_receipt.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof),flush=True)
    return prepared,nodes
cli.prepare_views=hint_prepare
result=cli.run(dest/'training-input.json',dest/'output',maximum_seconds=480,tle_root=Path('/tmp/three-track-investigation/space-track-pipeline-rerun/pinned-tle'))
print(json.dumps({key:result.get(key) for key in ['state','reason','elapsed_seconds','position','selection']}),flush=True)
