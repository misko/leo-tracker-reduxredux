"""Independent, digest-bound presentation evidence for recorded optimizer paths."""
import math
from leo.contracts.position_grid import binding

ARMS=('c0','fitted_c')


def validate(path, publication):
    def point(value):
        return (isinstance(value,list) and len(value)==2 and all(isinstance(v,(float,int))
            and not isinstance(v,bool) and math.isfinite(v) and abs(v)<=12.5+1e-8 for v in value))
    try:
        if (path['schema_version']!=1 or path['kind']!='recorded-position-path'
                or path['binding']!=binding(publication)
                or path['selected_model']!=publication['selected_model']
                or path['region_center']!=[37.906,-122.545] or path['box_width_km']!=25.
                or not path['stages'] or path['stages'][-1]['model_version']!=path['selected_model']):
            raise ValueError('Recorded path provenance differs from publication')
        for stage in path['stages']:
            if set(stage['arms'])!=set(ARMS):raise ValueError('Both recorded path arms required')
            for row in stage['arms'].values():
                if not point(row['endpoint']) or row['history_available']!=bool(row['rounds']):
                    raise ValueError('Invalid path endpoint or history flag')
                previous_round=0
                for r in row['rounds']:
                    if (not isinstance(r['round'],int) or r['round']<=previous_round
                            or not r['points'] or not point(r['endpoint'])
                            or any(not point(p) for p in r['points']) or r['points'][-1]!=r['endpoint']
                            or r['detail'] not in ('accepted_optimizer_iterates','phase_round_endpoint')):
                        raise ValueError('Invalid recorded phase round')
                    previous_round=r['round']
                if row['rounds'] and any(abs(a-b)>1e-6 for a,b in zip(row['rounds'][-1]['endpoint'],row['endpoint'])):
                    raise ValueError('Recorded history ends at another point')
        for arm in ARMS:
            east,north=path['stages'][-1]['arms'][arm]['endpoint']
            lat=37.906+north/111.;lon=-122.545+east/(111.32*math.cos(math.radians(37.906)))
            if any(abs(a-b)>1e-9 for a,b in zip((lat,lon),publication['arms'][arm]['endpoint_latlon'])):
                raise ValueError('Recorded path endpoint differs from published coordinates')
        return path
    except (KeyError,TypeError,IndexError) as error:
        raise ValueError('Malformed recorded position path') from error
