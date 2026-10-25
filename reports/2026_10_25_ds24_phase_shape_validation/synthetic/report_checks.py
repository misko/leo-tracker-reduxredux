"""Saved-artifact RF table and algebra checks; no geometry or fit imports."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    for name in ('scientific_seal.json', 'report_data_seal.json'):
        for path, expected in json.loads((HERE / name).read_text())['files'].items(): assert sha(path) == expected
    rows = list(csv.DictReader((HERE / 'all_cell_results.csv').open()))
    rf = []
    for cell in ('11','01','10','00'):
        for arm in ('c0','fitted_c'):
            chosen = [row for row in rows if row['cell'] == cell and row['arm'] == arm and row['status'] == 'complete']
            values = [json.loads(Path(row['source_path']).read_text()) for row in chosen]
            endpoint = [row['fixed_objective_diagnostics']['endpoint_at_final_reference'] for row in values]
            rf.append(dict(cell=cell, arm=arm, completed=len(chosen),
                mean_curved_RMS_hz=float(np.mean([row['parent_conditional_RMS_hz'] for row in endpoint])),
                mean_negative_twice_ELBO=float(np.mean([row['total_negative_twice_elbo'] for row in endpoint])),
                maximum_absolute_parent_decomposition_closure=float(max(abs(row['parent_decomposition_closure']) for row in endpoint))))
    factorials = json.loads((HERE / 'factorial_contrasts.json').read_text())['factorials']
    for row in factorials:
        if not row['all_cells_complete']: continue
        cells = row['source_bindings']
        for metric, values in row['contrasts'].items():
            if metric == 'vector':
                total = np.asarray([cells['00'][key] - cells['11'][key] for key in ('error_east_km','error_north_km')])
            else:
                key = 'error_km' if metric == 'error' else 'squared_error_km2'
                total = cells['00'][key] - cells['11'][key]
            np.testing.assert_allclose(np.asarray(values['marginal_phase_removal']) + values['marginal_shape_removal'], total, atol=1e-12, rtol=0.)
    result = dict(all_passed=True, artifact_only_no_propagation_or_fits=True, RF_summaries=rf,
        score_interpretation='different observations across cells: raw ELBOs are not same-data model comparisons',
        source_sha256=sha(__file__), scientific_seal_sha256=sha(HERE / 'scientific_seal.json'),
        report_data_seal_sha256=sha(HERE / 'report_data_seal.json'))
    path = HERE / 'report_checks.json'
    with path.open('x') as stream: json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
