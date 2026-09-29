"""Collect completed Wave6 comparisons, keeping ARM timing and host recall separate."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
CASES = [
    ('Wave5 final v2', 'arm_wave5_final/arm4-v2', 'arm_wave5_final/host704-v2'),
    ('Three-pass radix ranking', 'arm_wave6_proposal_rank/arm4', 'arm_wave6_proposal_rank/host704'),
    ('Share three-lag sample loads', 'arm_wave6_proposal_fold/arm4', 'arm_wave6_proposal_fold/host704'),
    ('Reuse dwell input', 'arm_wave6_dwell_input/arm4', 'arm_wave6_dwell_input/host704'),
    ('NEON proposal products and magnitudes', 'arm_wave6_proposal_simd/arm4', 'arm_wave6_proposal_simd/host704'),
    ('Compiler points-to analysis', 'arm_wave6_compiler_matrix/arm4-ipa-pta', 'arm_wave6_compiler_matrix/host704-ipa-pta'),
    ('Compiler function alignment', 'arm_wave6_compiler_matrix/arm4-align32', 'arm_wave6_compiler_matrix/host704-align32'),
    ('Combined exact changes', 'arm_wave6_combined/arm4', 'arm_wave6_combined/host704'),
    ('Half-size proposal FFT (approximate)', 'arm_wave6_proposal_resolution/arm4', 'arm_wave6_proposal_resolution/host704'),
    ('Dwell product cache, scalar', 'arm_wave6_dwell_products/arm4', 'arm_wave6_dwell_products/host704'),
    ('Dwell product cache, NEON', 'arm_wave6_dwell_products/arm4-v2', 'arm_wave6_dwell_products/host704-v2'),
    ('Proposal-only fast-math (non-exact)', 'arm_wave6_proposal_fastmath/arm4', 'arm_wave6_proposal_fastmath/host704'),
]

def directory(short):
    return REPORTS / ('2026_09_29_' + short)

def read_cohort(short):
    folder = directory(short)
    if not (folder / 'summary.json').exists():
        return None
    summary = json.loads((folder / 'summary.json').read_text())
    manifest = json.loads((folder / 'manifest.json').read_text())
    assert manifest['complete']
    for filename, key in [('rows.jsonl', 'rows_sha256'), ('build-receipt.json', 'build_sha256')]:
        actual = hashlib.sha256((folder / filename).read_bytes()).hexdigest()
        assert actual == summary[key], (folder, filename)
    audit_path = folder / 'standard-audit.json'
    audit = json.loads(audit_path.read_text()) if audit_path.exists() else None
    if audit:
        assert audit['native_sha256'] == summary['rows_sha256']
    return {'path': str(folder.relative_to(REPORTS.parent)), 'summary': summary,
            'hits': None if audit is None else audit['totals']}

def collect():
    rows = []
    for label, arm_path, host_path in CASES:
        arm = read_cohort(arm_path)
        if arm:
            assert arm['summary']['hardware'] == 'PLUTO+ CPU0'
            rows.append({'method': label, 'arm': arm, 'host': read_cohort(host_path)})
    baseline = rows[0]['arm']['summary']['mean_timings_ms']['fused_total']
    for row in rows:
        row['arm_runtime_reduction_fraction'] = 1 - row['arm']['summary']['mean_timings_ms']['fused_total'] / baseline
    return {'schema': 'arm-wave6-comparison/v1', 'baseline_ms': baseline,
            'larger_arm_baseline': read_cohort('arm_wave5_final/arm152'),
            'larger_arm_combined': read_cohort('arm_wave6_combined/arm152'),
            'pgo_heldout32': read_cohort('arm_wave6_pgo/arm-heldout32-v2'),
            'combined_pgo_heldout32': read_cohort('arm_wave6_combined_pgo/arm-heldout32'),
            'scope': 'Four saved 2.5 MS/s dual-RX 120 ms dwells; 88 overlapping receiver/windows; CPU0; no RF; preparation and proposals included; setup and file I/O excluded. Host704 recall is a separate mixed-rate panel.',
            'rows': rows}

if __name__ == '__main__':
    result = collect()
    (HERE / 'wave6-results.json').write_text(json.dumps(result, indent=2) + '\n')
    for row in result['rows']:
        arm = row['arm']
        hits = arm['hits']
        print(row['method'], round(arm['summary']['mean_timings_ms']['fused_total'], 3),
              None if hits is None else (hits['recovered_positive_hits'], hits['reference_positive_hits']))
