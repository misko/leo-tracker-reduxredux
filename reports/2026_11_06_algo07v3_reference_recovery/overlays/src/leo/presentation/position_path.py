"""Extract recorded fits from the accepted terminal chain without inventing steps."""
import math

ARMS=('c0','fitted_c')


def _point(value):
    if not isinstance(value,(tuple,list)) or len(value)!=2 or not all(
            isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<=12.5+1e-8 for v in value):
        raise ValueError('Invalid recorded position')
    return list(value)


def _accepted_rows(stage):
    model=stage['model_version'].split('-')[0]
    decision=stage.get('decision')
    if model=='algo02':return stage['arms']
    if model=='algo03' and decision in ('ALGO03_single','ALGO03_joint'):
        return stage['selected']['arms']
    if model=='algo04' and decision=='ALGO04_additive':
        return stage['candidate']['selected']['arms']
    if model in ('algo05','algo06') and decision==model.upper()+'_additive':
        return stage['candidate']['trial']['arms']
    if model=='algo07' and decision=='ALGO07_reassociation':return stage['candidate']['arms']
    return None


def recorded_position_path(terminal, selected_model):
    chain=[];stage=terminal
    while stage:
        chain.append(stage);stage=stage.get('incumbent',stage.get('baseline'))
    stages=[]
    for stage in reversed(chain):
        rows=_accepted_rows(stage)
        if rows is None:continue
        arms={}
        for arm in ARMS:
            row=rows[arm];rounds=[]
            for number,epoch in enumerate(row.get('history',[]),1):
                fit=epoch.get('fit',epoch)
                # Least-squares histories explicitly record accepted iterates.
                # Other solvers may record only a completed phase-round endpoint.
                steps=[_point(p['parameters']) for p in fit.get('history',[]) if 'parameters' in p]
                endpoint=fit.get('parameters',epoch.get('x'))
                if endpoint is None and not steps:continue
                endpoint=_point(endpoint) if endpoint is not None else steps[-1]
                if steps and steps[-1]!=endpoint:
                    raise ValueError('Recorded optimizer endpoint differs from its history')
                rounds.append(dict(round=number,points=steps or [endpoint],endpoint=endpoint,
                    detail='accepted_optimizer_iterates' if steps else 'phase_round_endpoint',
                    phase_change_s=epoch.get('phase_change_s')))
            endpoint=row.get('endpoint_east_north_km',row.get('x'))
            if endpoint is None:
                lat,lon=row['endpoint_latlon']
                endpoint=[(lon+122.545)*111.32*math.cos(math.radians(37.906)),(lat-37.906)*111.]
            endpoint=_point(endpoint)
            if rounds and any(abs(a-b)>1e-6 for a,b in zip(rounds[-1]['endpoint'],endpoint)):
                raise ValueError('Recorded fit history differs from published endpoint')
            arms[arm]=dict(endpoint=endpoint,rounds=rounds,history_available=bool(rounds))
        stages.append(dict(model_version=stage['model_version'],arms=arms))
    if not stages or stages[-1]['model_version']!=selected_model:
        raise ValueError('Recorded path does not end at the selected published model')
    return dict(schema_version=1,kind='recorded-position-path',selected_model=selected_model,
        region_center=[37.906,-122.545],box_width_km=25.,
        semantics='recorded accepted fits; no inferred links between separate fits',
        stages=stages)
