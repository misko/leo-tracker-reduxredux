"""Fixed training-selected points: real-data quadrature convergence, no truth."""
import importlib.util
import json
import sys
from pathlib import Path

root = Path(__file__).parent
source = root / 'tools/research/refine_joint_circular_position.py'
spec = importlib.util.spec_from_file_location('grid_model', source)
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)
rows = []
for cohort in ('single', 'set'):
    path = Path(f'/tmp/recent-five-block-regional-v1/sacramento-{cohort}-refinement-v2/result.json')
    cache = model.build_state_cache(path, Path('/tmp/recent-regional-evidence-v1'),
        Path('/tmp/recent-position-rf-shards-v1'),
        Path('/home/mouse9911/gits/leo-standard-position-methods/reports/2026_09_22_alias_offset_audit/audit.json'))
    baseline = json.loads(path.read_text())['selected']
    point = [baseline['east_km'], baseline['north_km']]
    for sigma in (3000., 10000., 30000.):
        for outlier in (.05, .2):
            scores = {}
            for size in (512, 1024, 2048):
                result = model.evaluate_position(cache, point, model.CircularArm(sigma, outlier, size))
                scores[str(size)] = {key: result[key] for key in ('training_score', 'heldout_score', 'pruning_log_error_bound')}
            row = dict(cohort=cohort, sigma_hz=sigma, outlier_probability=outlier, scores=scores)
            rows.append(row)
            print(json.dumps(row), flush=True)
output = dict(scope='Quadrature at sealed baseline training-selected points only; no optimization or truth',
    source_digest=model.digest(source), driver_digest=model.digest(Path(__file__)), rows=rows)
(root / 'grid-check.json').write_text(json.dumps(output, indent=2)+'\n')
