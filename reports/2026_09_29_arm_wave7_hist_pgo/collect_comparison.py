#!/usr/bin/env python3
"""Bind same-panel held-out PGO comparisons without rerunning hardware."""
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT.parent
CASES = {
    'wave5_reference': REPORTS/'2026_09_29_arm_wave6_pgo/heldout32-reference',
    'wave6_combined_pgo': REPORTS/'2026_09_29_arm_wave6_combined_pgo/arm-heldout32',
    'wave7_hist_pgo': ROOT/'arm-heldout32',
}

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def bind(path):
    summary = json.loads((path/'summary.json').read_text())
    audit_path = path/'standard-audit.json'
    audit = json.loads(audit_path.read_text()) if audit_path.exists() else None
    assert summary['dwells'] == 32 and summary['windows'] == 704
    if 'complete' in summary: assert summary['complete']
    assert sha(path/'rows.jsonl') == summary['rows_sha256']
    if audit: assert audit['native_sha256'] == summary['rows_sha256']
    # The filtered reference retains its source's per-window mean. Evaluator
    # outputs record the sum of 22 row times as the per-dwell outer mean.
    time = summary['mean_timings_ms']['fused_total'] * (22 if not audit else 1)
    result = {
        'path': str(path.relative_to(REPORTS.parent)),
        'mean_outer_cpu_ms_per_dwell': time,
        'candidate_entries': summary['candidate_entries'],
        'hashes': {name: sha(path/name) for name in
                   ('summary.json', 'rows.jsonl', 'manifest.json', 'build-receipt.json')},
    }
    if audit:
        result.update(scientific_outputs_identical=summary['scientific_outputs_identical'],
                      standard_hits=audit['totals']['recovered_positive_hits'],
                      standard_hit_denominator=audit['totals']['reference_positive_hits'])
        result['hashes']['standard-audit.json'] = sha(audit_path)
    return result

data = {name: bind(path) for name, path in CASES.items()}
base = data['wave5_reference']['mean_outer_cpu_ms_per_dwell']
prior = data['wave6_combined_pgo']['mean_outer_cpu_ms_per_dwell']
current = data['wave7_hist_pgo']['mean_outer_cpu_ms_per_dwell']
result = {
    'schema': 'arm-wave7-hist-pgo-comparison/v1',
    'scope': 'Same disjoint held-out 32 saved 2.5 MS/s dwells; outer CPU ms/dwell; training four contexts excluded',
    'cases': data,
    'reduction_vs_wave5': 1-current/base,
    'reduction_vs_wave6_combined_pgo': 1-current/prior,
}
(ROOT/'heldout-comparison.json').write_text(json.dumps(result, indent=2)+'\n')
