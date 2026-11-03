"""Record the frozen two-arm replication gate without geographic evaluation."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WAVE = HERE.parent/'waveform_replication16'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    plan_path = WAVE/'manifest.json'
    summary_path = WAVE/'measurement_summary.json'
    measured_path = WAVE/'local/measurements.json'
    plan, summary, measured = [json.loads(p.read_text()) for p in (plan_path, summary_path, measured_path)]
    for artifact in (plan, summary):
        for path, expected in artifact['sources'].items():
            assert digest(path) == expected, path
    assert measured['plan_sha256'] == digest(plan_path)
    assert len(plan['rows']) == len(measured['rows']) == 124
    failures = []
    for planned, row in zip(plan['rows'], measured['rows'], strict=True):
        assert all(planned[k] == row[k] for k in ('ordinal', 'track_id', 'observation_index', 'visit'))
        assert row['status'] == 'ok'
        for arm in ('pilot_2_65', 'pilot_22_221'):
            if row['arms'][arm]['search_boundary']:
                failures.append(dict(ordinal=row['ordinal'], track_id=row['track_id'],
                                     visit=row['visit'], receiver_id=planned['receiver_id'], arm=arm,
                                     native_residual_hz=row['arms'][arm]['native_residual_hz']))
    assert len(failures) == 2 and all(r['arm'] == 'pilot_2_65' for r in failures)
    assert not (HERE/'plan.json').exists() and not (HERE/'runs').exists()
    paths = [plan_path, summary_path, measured_path, HERE/'PROTOCOL.md', HERE/'run.py',
             HERE/'test_run.py', Path(__file__)]
    output = dict(schema='ds11-replication16-position-gate/v1', position_fits=0,
                  geographic_errors_evaluated=False, model_promotion=False, available=False,
                  reason='Both pilot arms must be complete and free of search boundaries; short arm has two.',
                  measured_rows=124, search_boundary_failures=failures,
                  sources={str(p.resolve()):digest(p) for p in paths})
    with (HERE/'gate_outcome.json').open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
