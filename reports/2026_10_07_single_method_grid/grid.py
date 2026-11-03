"""Budgeted center scoring on aligned grids with arbitrary refinement ratios.

Child squares intersect their parent with positive area. Noninteger ratios may
overlap adjacent parents; each child and each geographic evaluation is unique.
Batch evaluation changes scheduling only, not which scores choose the next cell.
"""
import heapq
import math
from dataclasses import dataclass
from leo.analysis.regional_position_search import SpatialEvaluation, SpatialSearch

@dataclass(frozen=True)
class Cell:
    depth: int
    ix: int
    iy: int

    def center(self, levels):
        s = levels[self.depth]
        return (self.ix + .5) * s - 500, (self.iy + .5) * s - 500


def intersects_circle(e, n, spacing, radius):
    return math.hypot(max(abs(e)-spacing/2, 0), max(abs(n)-spacing/2, 0)) <= radius


def children(cell, levels):
    e, n = cell.center(levels)
    parent = levels[cell.depth]
    child = levels[cell.depth + 1]
    xs = range(math.floor((e-parent/2+500)/child + 1e-10),
               math.ceil((e+parent/2+500)/child - 1e-10))
    ys = range(math.floor((n-parent/2+500)/child + 1e-10),
               math.ceil((n+parent/2+500)/child - 1e-10))
    return [Cell(cell.depth+1, x, y) for x in xs for y in ys]


def search(evaluate_batch, *, levels, budget=400, radius=250.):
    if not levels or any(not math.isfinite(s) or s <= 0 or
                         not math.isclose(1000/s, round(1000/s)) for s in levels):
        raise ValueError("levels must tile the fixed enclosing square")
    if any(a <= b for a, b in zip(levels, levels[1:])) or budget < 1:
        raise ValueError("strictly decreasing levels and positive budget required")
    side = round(1000/levels[0])
    initial = [Cell(0, x, y) for y in range(side) for x in range(side)
               if intersects_circle(*Cell(0, x, y).center(levels), levels[0], radius)]
    inside = [c for c in initial if math.hypot(*c.center(levels)) <= radius]
    if len(inside) > budget:
        raise ValueError(f"initial grid needs {len(inside)} points; budget is {budget}")
    rows, seen, heap = {}, set(initial), []

    def evaluate(cells):
        pending = []
        for c in cells:
            xy = c.center(levels)
            if xy not in rows and math.hypot(*xy) <= radius and len(rows)+len(pending) < budget:
                pending.append(c)
        values = evaluate_batch([c.center(levels) for c in pending]) if pending else []
        if len(values) != len(pending):
            raise ValueError("missing point scores")
        for c, score in zip(pending, values):
            if not math.isfinite(score):
                raise ValueError("nonfinite point score")
            e, n = c.center(levels)
            rows[(e,n)] = SpatialEvaluation(e, n, levels[c.depth], float(score))

    def push(c, fallback):
        e, n = c.center(levels)
        row = rows.get((e,n))
        heapq.heappush(heap, (row.score if row else fallback, e, n, c.depth, c.ix, c.iy))

    evaluate(inside)
    for c in initial:
        push(c, 0.)  # Same boundary-cell priority as the deployed hierarchy.
    while heap and len(rows) < budget:
        score, e, n, depth, ix, iy = heapq.heappop(heap)
        if depth == len(levels)-1:
            continue
        candidates = []
        for child in children(Cell(depth, ix, iy), levels):
            if child in seen:
                continue
            seen.add(child)
            if intersects_circle(*child.center(levels), levels[child.depth], radius):
                candidates.append(child)
        evaluate(candidates)
        for child in candidates:
            push(child, score)
    return SpatialSearch(tuple(rows.values()), len(heap), "point-budget" if heap else "frontier-exhausted")
