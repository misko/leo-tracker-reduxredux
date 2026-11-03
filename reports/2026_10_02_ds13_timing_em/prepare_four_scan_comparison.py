"""Read-only DS13 cohort pull and frozen proposal replay for four new singles."""
import json
import sys
from pathlib import Path
import numpy as np
from curvature_position_profile import ROOT

OUTPUT=ROOT.parent/'2026_10_03_ds13_four_scan_curvature'
INDICES=(3,6,10,13)


def selection(manifest):
    rows=sorted(manifest['captures'],key=lambda r:(r['capture_start_utc_ns'],r['session_id']))
    if manifest['dataset_id']!='DS13' or len(rows)!=17:raise ValueError('unexpected frozen cohort')
    return [rows[i] for i in INDICES]


def run():
    import prepare_scans as prep
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from check_capture_pointing import digest,canonical
    manifest=json.loads(prep.POPULATION.read_text());captures=selection(manifest)
    OUTPUT.mkdir(exist_ok=False)
    protocol=json.loads((ROOT/'protocol.json').read_text())
    protocol.update(sessions=[r['session_id'] for r in captures],selection='Fixed chronological indices 3,6,10,13 of frozen 17-scan DS13 cohort; excludes previous endpoints. No score-based selection.')
    (OUTPUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    hashes=snapshot_files([__file__,prep.POPULATION,ROOT/'prepare_scans.py'])
    poses=[]
    for capture in captures:
        sid=capture['session_id'];path=Path('/srv/bulk/leo/capture-pose/gauss-r20-lt3d-004b-20261001-v1')/(sid+'.json')
        pose=json.loads(path.read_text());authority=pose['pose_authority']
        published=prep.POPULATION.parent/'published'/(sid+'.json');m=json.loads(published.read_text())
        assert pose['binding_digest']==digest(canonical({k:v for k,v in pose.items() if k!='binding_digest'}))
        assert pose['pose_authority_digest']==digest(canonical(authority))
        assert pose['session_id']==sid and pose['manifest_sha256']==capture['manifest_sha256']
        assert pose['capture_start_earliest_utc_ns']==m['timing']['first_sample_earliest_utc_ns']
        assert pose['capture_end_utc_ns']==m['timing']['terminal_realtime_ns']
        assert authority['valid_from_utc_ns']<=pose['capture_start_earliest_utc_ns']<pose['capture_end_utc_ns']<authority['valid_until_utc_ns']
        hashes.update(snapshot_files([path,published,prep.POPULATION.parent/'analysis'/(sid+'.json')]))
        poses.append(dict(session=sid,latitude=authority['latitude_deg'],longitude=authority['longitude_deg'],bindings_verified=True,pose=pose))
    (OUTPUT/'selection.json').write_text(json.dumps(dict(captures=captures,poses=poses,source_hashes=hashes),indent=2))
    # Reuse the original export/init functions, with a separate output namespace
    # and an explicit cohort selection override; no source module is modified.
    prep.ROOT=OUTPUT;prep.select_scans=selection
    results=[]
    for capture in captures:
        sid=capture['session_id'];print('EXPORT',sid,flush=True)
        exported=prep.export_scan(sid);print(exported,flush=True)
        initialized=prep.initialize_scan(sid);print(initialized,flush=True)
        results.append(dict(exported=exported,initialized=initialized))
        (OUTPUT/'preparation-progress.json').write_text(json.dumps(results,indent=2))
    assert_snapshot_unchanged(hashes)
    (OUTPUT/'preparation.json').write_text(json.dumps(dict(results=results,source_hashes=hashes,
        scope='Existing local metadata/GLRT corpus only; no IQ collection. Original proposal reconstruction and initialization. '
        'New scans have independently initialized candidate pools; original A/B all-visible expansion is not reused as a candidate whitelist.'),indent=2))


if __name__=='__main__':run()
