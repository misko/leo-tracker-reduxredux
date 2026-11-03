"""Read public elevation/geoid services; preserve raw responses and provenance."""
import concurrent.futures
import datetime
import hashlib
import json
import math
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

HERE=Path(__file__).resolve().parent
LAT,LON=37.849056280893684,-122.48575489722863


def requests():
    rows=[]
    for label,east,north in [('center',0,0),('east10',10,0),('west10',-10,0),('north10',0,10),('south10',0,-10)]:
        lat=LAT+north/111195
        lon=LON+east/(111195*math.cos(math.radians(LAT)))
        url='https://epqs.nationalmap.gov/v1/json?'+urlencode(dict(x=lon,y=lat,units='Meters',wkid=4326,includeDate='True'))
        rows.append((label,url))
    rows.append(('geoid','https://geodesy.noaa.gov/api/geoid/ght?'+urlencode(dict(lat=LAT,lon=LON,model=14))))
    rows.append(('raster','https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/121893?f=pjson'))
    rows.append(('service','https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer?f=pjson'))
    return rows


def fetch(item):
    label,url=item
    receipt=dict(label=label,url=url,requested_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    try:
        with urllib.request.urlopen(url,timeout=25) as response:
            raw=response.read()
            receipt.update(status=response.status,final_url=response.url,headers=dict(response.headers.items()))
        parsed=json.loads(raw)
        with (HERE/f'{label}.json').open('xb') as out:out.write(raw)
        receipt.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),response_error_field=parsed.get('error'))
    except Exception as exc:
        receipt['exception']=repr(exc)
    return receipt


if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        receipts=list(pool.map(fetch,requests()))
    with (HERE/'receipts.json').open('x') as out:json.dump(receipts,out,indent=2)
    print(json.dumps([{k:r.get(k) for k in ['label','status','bytes','exception','response_error_field']} for r in receipts],indent=2))
