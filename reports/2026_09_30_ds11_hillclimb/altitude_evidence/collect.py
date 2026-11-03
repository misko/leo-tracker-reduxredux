"""Read-only external terrain/geoid evidence; never select an antenna altitude."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def main():
    station_path=ROOT/'deploy/station/gauss-r20-roof-20260926-v1.json'
    station=json.loads(station_path.read_text())
    lat,lon=station['latitude_deg'],station['longitude_deg']
    queries=[('usgs_terrain','https://epqs.nationalmap.gov/v1/json?'+urlencode(dict(x=lon,y=lat,units='Meters',wkid=4326,includeDate='true'))),
             ('noaa_geoid18','https://geodesy.noaa.gov/api/geoid/ght?'+urlencode(dict(lat=lat,lon=lon,model=14)))]
    def fetch(item):
        label,url=item
        row=dict(service=label,url=url,retrieved_utc=datetime.now(timezone.utc).isoformat())
        try:
            with urlopen(Request(url,headers={'User-Agent':'DS11-research-altitude-check/1.0'}),timeout=20) as response:
                body=response.read(2_000_000)
                row.update(status=response.status,body_sha256=hashlib.sha256(body).hexdigest(),
                           response=json.loads(body),success=True)
        except Exception as error:
            row.update(success=False,error=str(error))
        return row
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(fetch,queries))
    out=dict(station_id=station['station_id'],queries=results,
             station_altitude_m=station['altitude_m'],station_altitude_datum=station['altitude_datum'],
             selected_antenna_altitude_m=None,position_fits_run=0,
             limitations=['Ground terrain is not roof or antenna height.',
                          'GEOID18 is tied to NAD83/NAVD88, not a direct WGS84 conversion.',
                          'Current service retrieval does not establish availability at DS11 capture.',
                          'The horizontal station reference is used only to query independent elevation evidence.'],
             sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),station_path)},
             documentation=['https://www.usgs.gov/faqs/how-accurate-are-elevations-generated-elevation-point-query-service-national-map',
                            'https://www.ngs.noaa.gov/web_services/geoid.shtml'])
    with (HERE/'external-evidence.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,indent=2))


if __name__=='__main__':main()
