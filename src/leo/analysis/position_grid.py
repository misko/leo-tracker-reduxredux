"""Bounded matched-c diagnostic sampling; no optimizer or evaluation-site input."""
import math
import time

ARMS=('c0','fitted_c')


def sample_position_grid(score, endpoints, *, box_width_km=25., coarse_size=9,
                         local_size=7, local_half_width_km=1.5, maximum_seconds=30.,
                         clock=time.monotonic):
    if coarse_size<2 or local_size<2 or box_width_km<=0 or maximum_seconds<=0:
        raise ValueError('Positive grid size and budget required')
    half=box_width_km/2
    points=[];seen=set()
    def add(east,north):
        point=(float(east),float(north))
        if not all(math.isfinite(v) and abs(v)<=half for v in point):
            return
        if point not in seen:seen.add(point);points.append(point)
    for arm in ARMS:add(*endpoints[arm])
    add(0,0)
    axis=[-half+box_width_km*i/(coarse_size-1) for i in range(coarse_size)]
    for east,north in sorted(((e,n) for e in axis for n in axis),key=lambda p:p[0]**2+p[1]**2):
        add(east,north)
    offsets=[-local_half_width_km+2*local_half_width_km*i/(local_size-1)
             for i in range(local_size)]
    for arm in ARMS:
        x,y=endpoints[arm]
        for de,dn in sorted(((e,n) for e in offsets for n in offsets),key=lambda p:p[0]**2+p[1]**2):
            add(x+de,y+dn)
    began=clock();rows=[]
    for point in points:
        if clock()-began>=maximum_seconds:break
        values={};failures={}
        for arm in ARMS:
            try:
                value=float(score(arm,point))
                if not math.isfinite(value):raise ValueError('Non-finite objective')
                values[arm]=value
            except (ValueError,ArithmeticError) as error:
                values[arm]=None;failures[arm]=type(error).__name__
        rows.append(dict(east_km=point[0],north_km=point[1],scores=values,failures=failures))
    return dict(schema_version=1,kind='conditional-position-grid',
        conditioning='published satellite ownership and phase linearization fixed',
        nuisance_model='unchanged published marginal likelihood',matched_c_grid=True,
        box_width_km=float(box_width_km),coarse_size=coarse_size,local_size=local_size,
        local_half_width_km=local_half_width_km,maximum_seconds=maximum_seconds,
        planned_points=len(points),evaluated_points=len(rows),
        complete=len(rows)==len(points),elapsed_seconds=clock()-began,
        endpoints={a:list(endpoints[a]) for a in ARMS},points=rows)
