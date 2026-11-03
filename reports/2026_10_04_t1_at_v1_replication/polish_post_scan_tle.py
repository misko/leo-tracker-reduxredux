"""Matched cross-ephemeris starts and continuation without changing the model."""
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import post_scan_tle_localization as experiment
from post_scan_tle_bank import OUT as SOURCE, load_variant
from audit_post_scan_tle import diagnostics
from subset_positions import serial
from timing_bound_comparison import digest, feasible_start
from convergence_fisher import fit
from resume_position_convergence import best_record

OUT = SOURCE/'polished'
BUDGET = dict(cross_start=8., continuation=8., final_polish=8.)


def run(task):
    scan, arm = task
    sources = {v: SOURCE/scan/f'{arm}-{v}.json' for v in experiment.VARIANTS}
    originals = {v: json.loads(p.read_text()) for v, p in sources.items()}
    data = {v: load_variant(scan, v) for v in experiment.VARIANTS}
    (OUT/scan).mkdir(exist_ok=True)
    for variant in experiment.VARIANTS:
        target = OUT/scan/sources[variant].name
        if target.exists():continue
        other = 'post-scan' if variant == 'original' else 'original'
        d, meta, _, _ = data[variant]; obj = experiment.make_objective(d, meta, arm)
        original = originals[variant]; records = list(original['records'])
        cross, alignment = experiment.aligned_start(data[other][0], d, originals[other]['best'])
        for stage, budget in BUDGET.items():
            seed = cross if stage == 'cross_start' else best_record(records)
            r = fit(obj, feasible_start(obj, seed, 20., arm), seed['point_km'], budget, False, radius_km=4.)
            r['stage'] = stage; records.append(r)
        best = best_record(records); obj.base.deadline = float('inf')
        metrics = diagnostics(obj, d, best)
        assert metrics['objective'] <= original['objective'] + 1e-7
        result = dict(original, best=best, records=records, **metrics,
            polish_scope=__doc__, polish_maximum_budgets_s=BUDGET,
            polish_sources_sha256={v:digest(p) for v,p in sources.items()},
            cross_alignment_diagnostics=alignment, polish_implementation_sha256=digest(Path(__file__)))
        target.write_text(json.dumps(result, default=serial, indent=2, allow_nan=False))
        print('POLISHED TLE', scan, arm, variant, round(result['distance_m']), result['converged'], result['kkt'], flush=True)


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(run, (s,a)) for s in experiment.SCANS for a in experiment.ARMS]):f.result()
    experiment.OUT = OUT; experiment.render()
