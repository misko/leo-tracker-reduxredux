"""Check the newly supplied Compass location without adopting antenna height."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent

def main():
    lat = 37 + 50/60 + 57/3600
    lon = -(122 + 29/60 + 9/3600)
    previous_path = HERE/'external-evidence.json'
    previous = json.loads(previous_path.read_text())
    terrain = next(q for q in previous['queries'] if q['service']=='usgs_terrain')
    old = terrain['response']['location']
    p1, p2 = math.radians(old['y']), math.radians(lat)
    dl = math.radians(lon-old['x'])
    a = math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    distance = 6371000*2*math.atan2(math.sqrt(a),math.sqrt(1-a))
    url = 'https://epqs.nationalmap.gov/v1/json?'+urlencode(dict(x=lon,y=lat,units='Meters',wkid=4326,includeDate='true'))
    with urlopen(url,timeout=20) as response:
        body = response.read(2_000_000)
        status = response.status
    data = json.loads(body)
    elevation = float(data['value'])
    result = dict(user_coordinate_dms='37 50 57 N 122 29 9 W',latitude_deg=lat,longitude_deg=lon,
        distance_from_saved_location_m=distance,query_url=url,http_status=status,
        retrieved_utc=datetime.now(timezone.utc).isoformat(),response=data,
        response_sha256=hashlib.sha256(body).hexdigest(),terrain_elevation_m=elevation,
        terrain_elevation_ft=elevation/.3048,
        terrain_change_from_saved_coordinate_m=elevation-float(terrain['response']['value']),
        reported_phone_elevation_ft=56,reported_antenna_offset_ft=10,
        reported_antenna_elevation_m=66*.3048,
        terrain_minus_reported_antenna_m=elevation-66*.3048,
        adopted_antenna_ellipsoidal_height_m=None,
        limitations=['Phone coordinates are displayed to whole arcseconds and are not a survey.',
                    'Terrain is not antenna or roof height.',
                    'Phone unit report remains feet; do not reinterpret as metres without confirmation.',
                    'No height correction, historical metadata change, or DS11 reference relocation.'],
        sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),previous_path)})
    with (HERE/'compass-location-evidence.json').open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
