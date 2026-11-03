"""Independent presentation evidence for an ALGO07 conditional position grid."""
import math

ARMS=('c0','fitted_c')


def binding(publication):
    return dict(run_id=publication['run_id'],model_version=publication['model_version'],
        terminal_sha256=publication['terminal_sha256'],input_sha256=publication['input_sha256'],
        owner_sha256={a:publication['arms'][a]['owner_sha256'] for a in ARMS},
        position_png_sha256=next(x['sha256'] for x in publication['artifacts'] if x['name']=='position'))


def validate(grid, publication):
    def finite(v):return isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v)
    try:
        if (grid['schema_version']!=1 or grid['kind']!='conditional-position-grid'
                or grid['matched_c_grid'] is not True or grid['binding']!=binding(publication)
                or grid['conditioning']!='published satellite ownership and phase linearization fixed'):
            raise ValueError('Position grid provenance differs from the published result')
        if grid['endpoint_latlon']!={a:publication['arms'][a]['endpoint_latlon'] for a in ARMS}:
            raise ValueError('Position grid uses different published endpoints')
        rows=grid['points'];width=grid['box_width_km']
        if (not finite(width) or width<=0 or not isinstance(rows,list)
                or len(rows)!=grid['evaluated_points'] or not len(rows)<=grid['planned_points']
                or grid['complete']!=(len(rows)==grid['planned_points'])):
            raise ValueError('Position grid accounting is invalid')
        seen=set()
        for p in rows:
            xy=(p['east_km'],p['north_km'])
            if (not all(finite(v) and abs(v)<=width/2 for v in xy) or xy in seen
                    or len(p['latlon'])!=2 or not all(finite(v) for v in p['latlon'])
                    or set(p['scores'])!=set(ARMS)
                    or any(v is not None and not finite(v) for v in p['scores'].values())):
                raise ValueError('Position grid point or paired scores are invalid')
            seen.add(xy)
        return grid
    except (KeyError,TypeError,IndexError) as error:
        raise ValueError('Malformed position grid') from error
