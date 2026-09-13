"""Compare actual ARM jobs/fits to independently checked host feedback replay."""
import json
from pathlib import Path
import numpy as np
from check_adjacent_c_validity import BASE, digest


def main():
    output = BASE / 'adjacent-arm-v1-results'
    operator = json.loads((output / 'operator.json').read_text())
    assert operator['status'] == 'complete_review_pending' and operator['exit_code'] == 0
    assert operator['serial'] == '1040005e0b100007100010000bf33a5d4d'
    assert operator['before'] == operator['after'] and operator['temporary_files_removed']
    assert digest(output / 'stdout.jsonl') == operator['stdout_sha256']
    prior = json.loads((BASE / 'adjacent-c-trend-long-v1.json').read_text())
    expected = next(r['measurements'] for r in prior['cases'] if r['label']=='positive' and r['feedback'])
    statistics = {}
    for name, path in [('host', BASE / 'adjacent-host-bench-v1.jsonl'), ('arm', output / 'stdout.jsonl')]:
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        summary = rows.pop(); assert summary['summary'] and len(rows) == 1768
        assert len(rows) == len(expected)
        for row, reference in zip(rows, expected):
            for key in ('frame', 'start', 'phase', 'step', 'rejection'):
                assert row[key] == reference[key], (name, row['frame'], key)
            for key in ('coherence', 'delay_s', 'cfo_hz'):
                np.testing.assert_allclose(row[key], reference[key], rtol=2e-10, atol=1e-12)
            assert row['elapsed_ns'] > 0
        assert summary['accepted'] == sum(r['rejection']==0 for r in rows) == 1367
        assert summary['compute_ns'] == sum(r['elapsed_ns'] for r in rows)
        assert summary['maximum_ns'] == max(r['elapsed_ns'] for r in rows)
        elapsed = np.array([r['elapsed_ns'] for r in rows])
        statistics[name] = dict(compute_seconds=summary['compute_ns']/1e9,
            mean_ms=float(elapsed.mean()/1e6), median_ms=float(np.median(elapsed)/1e6),
            p99_ms=float(np.quantile(elapsed,.99)/1e6), maximum_ms=summary['maximum_ns']/1e6,
            over_frame_period=int(np.count_nonzero(elapsed > 1e9/750)),
            compute_to_source_time_ratio=summary['compute_ns']/1e9/(1768/750))
    result = dict(status='pass', scope='ARM_host_jobs_and_fits_against_independently_checked_replay',
        matched_measurements_per_platform=1768, accepted=1367, statistics=statistics,
        receiver_paced=False, RF_collection_and_DMA_cost_included=False,
        timing_excludes_input_loading_and_output_serialization=True, native_tracking_qualified=False,
        reviewer_sha256=digest(Path(__file__)), operator_sha256=digest(output/'operator.json'))
    with (output/'review.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
