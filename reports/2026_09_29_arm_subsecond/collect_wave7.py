"""Collect sealed Wave7 ARM timing and separate standard-hit audits."""
import json
from collect_wave6 import HERE, read_cohort

CASES = [
    ('Wave6 exact control', 'arm_wave6_combined/arm4', 'arm_wave6_combined/host704'),
    ('Single histogram scan', 'arm_wave7_rank_histograms/arm4', 'arm_wave7_rank_histograms/host704'),
    ('Histogram scan plus integer keys', 'arm_wave7_rank_histograms/arm4-v2', 'arm_wave7_rank_histograms/host704-v2'),
    ('Whole FP32 final scorer v2', 'arm_wave7_float_final/arm4-v2', 'arm_wave7_float_final/host704-v2'),
    ('Whole FP32 final scorer plus Winograd coarse', 'arm_wave7_coarse_winograd_integrated/arm4', 'arm_wave7_coarse_winograd_integrated/host704'),
    ('Winograd integration v2', 'arm_wave7_coarse_winograd_integrated/arm4-v2', 'arm_wave7_coarse_winograd_integrated/host704-v2'),
    ('Eight proposal frames', 'arm_wave7_proposal_budget/arm4', 'arm_wave7_proposal_budget/host704-budget8'),
    ('Neighbor proposal reuse min2', 'arm_wave7_proposal_tracking/arm4', 'arm_wave7_proposal_tracking/host704'),
    ('Neighbor proposal reuse min1', 'arm_wave7_proposal_tracking/arm4-min1', 'arm_wave7_proposal_tracking/host704-min1'),
    ('Radius1 plus exact rank improvements', 'arm_wave7_radius1/arm4', 'arm_wave7_radius1/host704'),
    ('Eight proposal frames/half grid/coarse8', 'arm_wave7_budget_frontier/arm4-triple', 'arm_wave7_budget_frontier/host704-triple'),
    ('Above plus neighbor reuse min1', 'arm_wave7_frontier_tracking/arm4-triple-min1', 'arm_wave7_frontier_tracking/host704'),
    ('Eight proposal frames/half grid/neighbor reuse, full coarse16', 'arm_wave7_proposal_tracking_fullcoarse/arm4', 'arm_wave7_proposal_tracking_fullcoarse/host704'),
    ('Above plus radius1', 'arm_wave7_fullcoarse_radius1/arm4', 'arm_wave7_fullcoarse_radius1/host704'),
]

def collect():
    rows = []
    for method, arm_path, host_path in CASES:
        arm, host = read_cohort(arm_path), read_cohort(host_path)
        if arm is None or host is None:
            raise ValueError(f'Missing evidence for {method}: {arm_path}, {host_path}')
        assert arm['summary']['hardware'] == 'PLUTO+ CPU0'
        assert arm['summary']['dwells'] == 4 and arm['summary']['windows'] == 88
        assert host['summary']['dwells'] == 704
        assert arm['hits'] is not None and host['hits'] is not None
        rows.append({'method': method, 'arm': arm, 'host': host})
    baseline = rows[0]['arm']['summary']['mean_timings_ms']['fused_total']
    for row in rows:
        row['reduction_from_wave6'] = 1-row['arm']['summary']['mean_timings_ms']['fused_total']/baseline
    return {'schema': 'arm-wave7-comparison/v1', 'baseline_ms': baseline,
            'scope': 'Same four saved 2.5 MS/s dual-RX 120 ms dwells, 88 overlapping 20 ms receiver/windows; CPU0, no RF. Host704 mixed-rate hit audit is separate. Initial setup and file I/O excluded; dwell preparation included.',
            'exact_pgo_heldout32': read_cohort('arm_wave7_hist_pgo/arm-heldout32'),
            'approximate_pgo_heldout32': read_cohort('arm_wave7_frontier_pgo/arm-heldout32'),
            'arm_codegen': {
                'thumb2': read_cohort('arm_wave7_codegen_matrix/arm4-thumb'),
                'O2': read_cohort('arm_wave7_codegen_matrix/arm4-o2'),
                'restrict': read_cohort('arm_wave7_compile_review/arm4-restrict'),
            },
            'rows': rows}

if __name__ == '__main__':
    result = collect()
    (HERE/'wave7-results.json').write_text(json.dumps(result, indent=2)+'\n')
    for row in result['rows']:
        a, h = row['arm'], row['host']
        print(row['method'], round(a['summary']['mean_timings_ms']['fused_total'], 3),
              a['hits']['recovered_positive_hits'], h['hits']['recovered_positive_hits'])
