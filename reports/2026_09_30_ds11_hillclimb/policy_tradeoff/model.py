"""Descriptive paired metrics with explicit missing-output denominators."""
import numpy as np


def summarize(rows):
    if len({r['session'] for r in rows})!=len(rows):raise ValueError('duplicate physical recording')
    matched=[r for r in rows if r['qualified'] and r['baseline_qualified']]
    missing=[dict(session=r['session'],policy_qualified=r['qualified'],baseline_qualified=r['baseline_qualified']) for r in rows if not (r['qualified'] and r['baseline_qualified'])]
    metrics=None
    if matched:
        base=np.array([r['baseline_error_m'] for r in matched]);policy=np.array([r['error_m'] for r in matched])
        if not np.isfinite(base).all() or not np.isfinite(policy).all() or (base<0).any() or (policy<0).any():raise ValueError('invalid qualified error')
        metrics={name:dict(baseline=float(f(base)),policy=float(f(policy))) for name,f in [('median_m',np.median),('mean_m',np.mean),('p90_m',lambda x:np.quantile(x,.9)),('maximum_m',np.max)]}
        metrics.update(paired_wins=int(np.sum(policy<base)),paired_losses=int(np.sum(policy>base)),ties=int(np.sum(policy==base)))
    return dict(attempts=len(rows),matched_qualified=len(matched),missing=missing,
                full_panel_metrics=metrics if not missing else None,matched_only_metrics=metrics)
