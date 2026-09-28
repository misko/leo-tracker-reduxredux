"""Exploratory development-only scoring of the frozen secondary selection rule."""
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
CONFIRMATION=HERE.parent/'2026_09_27_roof_geometry_confirmation'
sys.path.insert(0,str(CONFIRMATION))
from guided_selection import select_rx_guided_doppler
from score_distances import distance_km
import hashlib


def main():
    original=json.loads((HERE/'robust_distance_results.json').read_text())
    if not original['complete']:raise ValueError('all development searches must finish first')
    rows=[]
    for row in original['rows']:
        sid=row['session_id'];prior=row['prior']
        result=json.loads((HERE/f'robust-search-{sid}.json').read_text())
        selection=select_rx_guided_doppler(result['branches'][prior])
        point=selection['selected']
        error=distance_km((point['latitude_deg'],point['longitude_deg']),
            (row['truth_latitude_deg'],row['truth_longitude_deg']))
        rows.append(dict(session_id=sid,prior=prior,doppler_error_km=row['doppler_error_km'],
            joint_error_km=row['geometry_error_km'],geometry_guided_doppler_error_km=error,
            guidance_minus_doppler_km=error-row['doppler_error_km'],selection=selection))
    out=dict(scope='Exploratory development data; original pre-topology calibration. Not fresh confirmation. Same160-point budget; final D selection uses only J trace points.',
        rows=rows,search_artifact_sha256=original['search_artifact_sha256'],
        selection_code_sha256='sha256:'+hashlib.sha256((CONFIRMATION/'guided_selection.py').read_bytes()).hexdigest())
    (HERE/'development_guidance_results.json').write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
    for row in rows:print(row['session_id'],row['prior'],row['doppler_error_km'],row['joint_error_km'],row['geometry_guided_doppler_error_km'])


if __name__=='__main__':main()
