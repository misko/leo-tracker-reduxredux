"""Source-verified descriptive audit; no thresholds or geographic scoring."""
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    plan = json.loads((HERE/'plan.json').read_text())
    outcome = json.loads((HERE/'outcome.json').read_text())
    for artifact in (plan, outcome):
        for path, expected in artifact['sources'].items():
            assert digest(path) == expected, path
    rows = outcome['rows']
    assert len(rows) == 124 and all(r['status']=='ok' for r in rows)
    summary = {}
    for arm in ('pilot_2_65', 'pilot_22_221'):
        arms = [r['arms'][arm] for r in rows]
        disagreement = [r['alternating_disagreement_hz'] for r in arms]
        coherence = [r['coherent_energy_fraction'] for r in arms]
        assert all(r['replay_discrepancy_hz'] == 0 for r in arms)
        assert all(0 <= c <= 1 for c in coherence)
        summary[arm] = dict(median_disagreement_hz=float(np.median(disagreement)),
                            p90_disagreement_hz=float(np.quantile(disagreement,.9)),
                            maximum_disagreement_hz=max(disagreement),
                            median_coherent_energy_fraction=float(np.median(coherence)),
                            rows_with_alternating_search_boundary=sum(any(r['alternating_search_boundaries']) for r in arms))
    targets = [r for r in rows if r['ordinal'] in (5,60)]
    assert len(targets) == 2 and all(r['visit']==1308 for r in targets)
    result = dict(schema='ds11-pilot-stability-summary/v1', summary=summary,
                  original_short_boundary_rows=targets, replay_max_discrepancy_hz=0.,
                  thresholds_selected=False, geographic_errors_evaluated=False,
                  sources={str(p):digest(p) for p in (HERE/'plan.json',HERE/'outcome.json',Path(__file__))})
    with (HERE/'summary.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
