import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    receipts=json.loads((HERE/'receipts.json').read_text())
    for row in receipts:
        assert row['status']==200 and 'exception' not in row
        assert hashlib.sha256((HERE/f"{row['label']}.json").read_bytes()).hexdigest()==row['sha256']
    def read(name):return json.loads((HERE/f'{name}.json').read_text())
    raster=read('raster')['attributes'];geoid=read('geoid')
    assert raster['VerticalDatum']=='North American Vertical Datum of 1988 (NAVD 88)'
    assert geoid['geoidModel']=='GEOID18' and geoid['units']=='m'
    rows=[]
    for name in ['center','east10','west10','north10','south10']:
        data=read(name)
        assert data['rasterId']==raster['OBJECTID'] and data['resolution']==1
        rows.append(dict(point=name,navd88_ground_m=float(data['value']),location=data['location']))
    value=rows[0]['navd88_ground_m']+geoid['geoidHeight']
    result=dict(points=rows,geoid18_undulation_m=geoid['geoidHeight'],geoid_service_error_field_m=geoid['error'],
                approximate_nad83_ellipsoidal_ground_height_m=value,
                ground_height_range_at_five_points_navd88_m=[min(r['navd88_ground_m'] for r in rows),max(r['navd88_ground_m'] for r in rows)],
                antenna_height_above_ground_m=None,wgs84_antenna_ellipsoidal_height_m=None,
                raster_name=raster['Name'],vertical_datum=raster['VerticalDatum'])
    with (HERE/'summary.json').open('x') as out:json.dump(result,out,indent=2,allow_nan=False)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
