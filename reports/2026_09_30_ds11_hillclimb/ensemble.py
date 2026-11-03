"""Reference-free same-scan model combinations, with separate metric reveal."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
from harness import BASE, HERE, SCREEN, distance, percentile


def combine(points, variant):
    if variant == 'iid_corr_mean':
        chosen = [points[0], points[2]]
    elif variant == 'three_mean':
        chosen = points
    elif variant == 'three_median':
        # For three points the geometric median is a >=120-degree vertex,
        # otherwise the interior Fermat point obtained by Weiszfeld iteration.
        for i, p in enumerate(points):
            others = [q for j,q in enumerate(points) if j != i]
            vectors = [[q[k]-p[k] for k in range(2)] for q in others]
            lengths = [math.hypot(*v) for v in vectors]
            if min(lengths) < 1e-12:
                return list(p)
            cosine = sum(a*b for a,b in zip(*vectors))/(lengths[0]*lengths[1])
            if cosine <= -.5:
                return list(p)
        x = [sum(p[k] for p in points)/3 for k in range(2)]
        for _ in range(10000):
            weights = [1/max(math.dist(x,p),1e-12) for p in points]
            new = [sum(w*p[k] for w,p in zip(weights,points))/sum(weights) for k in range(2)]
            if math.dist(new,x) < 1e-10:
                return new
            x = new
        raise RuntimeError('Geometric median did not converge')
    else:
        raise ValueError(variant)
    return [sum(p[k] for p in chosen)/len(chosen) for k in range(2)]


def main(stage, variants):
    indices = SCREEN if stage=='screen' else list(range(32))
    center = json.loads((BASE/'plan.json').read_text())['config']['geographic_prior_center_deg']
    summaries, rows = [], []
    sources = {}
    for variant in variants:
        cells = []
        for index in indices:
            components = []
            for method in ('iid','shared','correlated'):
                path = BASE/'runs'/f'{index:02d}_{method}.json'
                sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
                selected = json.loads(path.read_text())['selected']
                assert selected and selected['qualified']
                components.append(selected)
            point = combine([r['x'][:2] for r in components], variant)
            coordinate = [center[0]+point[1]/111.195,
                          center[1]+point[0]/(111.195*math.cos(math.radians(center[0])))]
            cell = dict(index=index, variant=variant, x_en_km=point, estimate_deg=coordinate,
                        error_m=distance(coordinate), baseline_error_m=distance(components[0]['estimate_deg']))
            cells.append(cell)
        errors = [c['error_m'] for c in cells]
        old = [c['baseline_error_m'] for c in cells]
        wins = sum(c['error_m'] < c['baseline_error_m'] for c in cells)
        median, p90 = statistics.median(errors), percentile(errors,.9)
        summaries.append(dict(variant=variant, attempts=len(cells), median_m=median,p90_m=p90,
                              max_m=max(errors),wins=wins,subkm=sum(e<1000 for e in errors),
                              baseline_median_m=statistics.median(old),baseline_p90_m=percentile(old,.9),
                              screen_gate=stage=='screen' and wins>=4 and median<=.9*statistics.median(old)
                              and p90<=1.1*percentile(old,.9)))
        rows.extend(cells)
    for path in [Path(__file__), HERE/'ensemble_protocol.md',HERE/'PROTOCOL.md']:
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    output = dict(summary=summaries,rows=rows,sources=sources)
    folder = HERE/'ensemble';folder.mkdir(exist_ok=True)
    with (folder/f'{stage}.json').open('x') as stream:
        json.dump(output, stream, indent=2)
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2].split(',') if len(sys.argv)>2 else ['iid_corr_mean','three_mean','three_median'])
