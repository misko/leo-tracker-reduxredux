"""Posthoc orientation-reversal control over completed identical local grids."""
import json
import math
from pathlib import Path
import run_balanced_confirmation as runner
from score_confirmation import distance_km

HERE=Path(__file__).resolve().parent
ARMS=('D','D_plus_detection','D_plus_geometry','D_plus_reversed_geometry')


def winners(points):
    if not points: raise ValueError('empty grid')
    if any(not math.isfinite(p['scores'][arm]) for p in points for arm in ARMS):
        raise ValueError('nonfinite score')
    return {arm:min(points,key=lambda p:(p['scores'][arm],p['east_km'],p['north_km'])) for arm in ARMS}


def main():
    entries,_=runner.inputs()
    report=json.loads((HERE/'local-grid-distances.json').read_text())
    if not report['complete']: raise ValueError('requires completed primary local-grid report')
    runs={};hashes={}
    for entry in entries:
        sid=entry['session_id'];payload=(HERE/f'local-grid-{sid}.json').read_bytes()
        if runner.base.digest(payload)!=report['artifact_sha256'][sid]:raise ValueError('grid changed after verified report')
        runs[sid]=json.loads(payload);hashes[sid]=runner.base.digest(payload)
        if not runs[sid]['finished']:raise ValueError('incomplete grid')
    manifest=json.loads((HERE/'manifest.json').read_text());rows=[]
    for item in manifest['sessions']:
        sid=item['pose']['session_id'];pose=item['pose']['pose_authority'];truth=(pose['latitude_deg'],pose['longitude_deg'])
        for prior,branch in runs[sid]['branches'].items():
            selected=winners(branch['point_components'])
            errors={arm:distance_km((p['latitude_deg'],p['longitude_deg']),truth) for arm,p in selected.items()}
            rows.append(dict(session_id=sid,prior=prior,error_km=errors,
                reversed_minus_correct_km=errors['D_plus_reversed_geometry']-errors['D_plus_geometry'],
                selected_east_north={arm:[p['east_km'],p['north_km']] for arm,p in selected.items()}))
    output=dict(complete=True,rows=rows,artifact_sha256=hashes,
        source_sha256=runner.base.digest(Path(__file__).read_bytes()),
        scope='Posthoc orientation-reversal score control on identical local coordinates; no refit, no new evaluations, no untouched-validation claim. Reversal is a deliberately wrong orientation within the frozen model, not an independently calibrated model.')
    runner.base.atomic(HERE/'local-grid-direction-control.json',output)
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
