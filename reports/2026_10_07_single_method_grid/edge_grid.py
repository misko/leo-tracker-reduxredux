"""Controlled alternative to the deployed zero score for unmeasured edge cells."""
import heapq
import math
import grid
from leo.analysis.regional_position_search import SpatialEvaluation, SpatialSearch

def search(evaluate_batch, *, levels=(50.,20.,5.), budget=400, radius=250., edge_policy="nearest"):
    if edge_policy not in ("nearest", "legacy-zero"):
        raise ValueError(edge_policy)
    if not levels or any(not math.isfinite(s) or s <= 0 or
                         not math.isclose(1000/s, round(1000/s)) for s in levels):
        raise ValueError("levels must tile enclosing square")
    if any(a <= b for a,b in zip(levels,levels[1:])) or budget < 1:
        raise ValueError("invalid levels or budget")
    side=round(1000/levels[0])
    initial=[grid.Cell(0,x,y) for y in range(side) for x in range(side)
             if grid.intersects_circle(*grid.Cell(0,x,y).center(levels),levels[0],radius)]
    inside=[c for c in initial if math.hypot(*c.center(levels))<=radius]
    if len(inside)>budget:raise ValueError("initial grid exceeds budget")
    rows,seen,heap={},set(initial),[]
    trace=[]
    def evaluate(cells,parent_unmeasured=False):
        pending=[]
        for c in cells:
            xy=c.center(levels)
            if xy not in rows and math.hypot(*xy)<=radius and len(rows)+len(pending)<budget:
                pending.append(c)
        values=evaluate_batch([c.center(levels) for c in pending]) if pending else []
        if len(values)!=len(pending):raise ValueError("missing scores")
        for c,value in zip(pending,values):
            if not math.isfinite(value):raise ValueError("nonfinite score")
            e,n=c.center(levels)
            rows[(e,n)]=SpatialEvaluation(e,n,levels[c.depth],float(value))
            trace.append(dict(east_km=e,north_km=n,parent_unmeasured=parent_unmeasured))
    def push(c,fallback):
        e,n=c.center(levels);row=rows.get((e,n))
        heapq.heappush(heap,(row.score if row else fallback,e,n,c.depth,c.ix,c.iy))
    evaluate(inside)
    edge_priorities=[]
    for c in initial:
        e,n=c.center(levels)
        fallback=0.
        if (e,n) not in rows:
            nearest=min(rows.values(),key=lambda r:((r.east_km-e)**2+(r.north_km-n)**2,
                                                     r.score,r.east_km,r.north_km))
            if edge_policy=="nearest":fallback=nearest.score
            edge_priorities.append(dict(point=[e,n],priority=fallback,
                                        nearest_measured=[nearest.east_km,nearest.north_km],
                                        nearest_score=nearest.score))
        push(c,fallback)
    while heap and len(rows)<budget:
        value,e,n,depth,ix,iy=heapq.heappop(heap)
        if depth==len(levels)-1:continue
        candidates=[]
        for child in grid.children(grid.Cell(depth,ix,iy),levels):
            if child in seen:continue
            seen.add(child)
            if grid.intersects_circle(*child.center(levels),levels[child.depth],radius):
                candidates.append(child)
        evaluate(candidates,(e,n) not in rows)
        for child in candidates:push(child,value)
    return SpatialSearch(tuple(rows.values()),len(heap),"point-budget" if heap else "frontier-exhausted"),dict(
        edge_policy=edge_policy,edge_priorities=edge_priorities,trace=trace)
