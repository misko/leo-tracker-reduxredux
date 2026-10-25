"""RF metrics from saved endpoints only; generator arms are different datasets."""
from pathlib import Path
import numpy as np
import components as c


def main():
    execution = c.r.read(c.HERE / 'execution.json')
    rows = execution['rows']
    saved_controls = {}
    for row in rows:
        key = (row['case'], row['site_index'], row['variant'], row['arm'])
        if key not in saved_controls:
            path = c.OLD / 'fits' / key[0] / f'site{key[1]}' / key[2] / key[3] / 'result.json'
            assert c.r.sha(path) == row['control_result_sha256']
            saved_controls[key] = dict(c.r.read(path), intervention='original_all_deviations')
    summary = []
    for method in ('original_all_deviations',) + c.INTERVENTIONS:
        for arm in c.control.ARMS:
            chosen = [row for row in list(saved_controls.values()) + rows if row['arm'] == arm
                and row['intervention'] == method and row['status'] == 'complete']
            summary.append(dict(intervention=method, arm=arm, n=len(chosen),
                mean_curved_conditional_RMS_hz=float(np.mean([row['RMS_hz'] for row in chosen])),
                minimum_curved_conditional_RMS_hz=min(row['RMS_hz'] for row in chosen),
                maximum_curved_conditional_RMS_hz=max(row['RMS_hz'] for row in chosen),
                mean_negative_twice_elbo=float(np.mean([row['negative_twice_elbo'] for row in chosen]))))
    start = c.r.read(c.HERE / 'scientific_start.json')
    run_start = c.r.read(c.HERE / 'execution_start.json')
    result = dict(rows=summary, not_cross_model_selection='interventions change generating observations; compare truth/endpoint score components only within each final reference',
        fit_batch_wall_seconds=execution['wall_seconds_since_first_preparation'] - (run_start['started_utc_ns'] - start['started_utc_ns']) / 1e9,
        minimum_fit_seconds=min(row['seconds'] for row in rows), maximum_fit_seconds=max(row['seconds'] for row in rows),
        summed_fit_worker_seconds=sum(row['seconds'] for row in rows), source_sha256=c.r.sha(__file__),
        scientific_seal_sha256=c.r.sha(c.HERE / 'scientific_seal.json'), position_fits=0, real_GPS_used=False)
    c.r.write_new(c.HERE / 'rf_summary.json', result)
    print(result)


if __name__ == '__main__': main()
