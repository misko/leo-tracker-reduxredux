"""Collect completed third-wave measurements without mixing timing scopes."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
METHODS = [
    ('fused-v4', 'arm_fused_pipeline', 'host704-v4', ['arm4-v4', 'arm4-v4-repeat']),
    ('rank-only', 'arm_rank_only_proposal', 'host704', ['arm4']),
    ('resampled', 'arm_resampled_omit_fused', 'host704', ['arm4']),
    ('boundary-025', 'arm_boundary_gate', 'host704-gate-025', ['arm4-gate-025']),
    ('boundary-100', 'arm_boundary_gate', 'host704-gate-100', ['arm4-gate-100']),
    ('combined', 'arm_wave3_combined', 'host704', ['arm4', 'arm4-repeat']),
    ('two-lag-1-5', 'arm_two_lag_proposals', 'host704-lag1_lag5', ['arm4-lag1_lag5']),
    ('loop-unroll', 'arm_wave3_unroll', 'host704', ['arm4', 'arm4-repeat']),
    ('coarse-gate-015', 'arm_native_coarse_gate', 'host704', ['arm4']),
]


def collect():
    evidence = {}

    def read(path):
        raw = path.read_bytes()
        evidence[str(path.relative_to(REPORTS))] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)

    methods = []
    for name, directory, host, arms in METHODS:
        root = REPORTS / ('2026_09_29_' + directory)
        quality = read(root / host / 'standard-audit.json')
        assert quality['totals']['reference_positive_hits'] == 19581
        assert quality['totals']['windows'] == 15488
        runs = []
        for arm in arms:
            manifest = read(root / arm / 'manifest.json')
            assert manifest['complete']
            summary = read(root / arm / 'summary.json')
            audit = read(root / arm / 'standard-audit.json')
            assert audit['totals']['reference_positive_hits'] == 119
            runs.append({'cohort': arm, 'timings_ms': summary['mean_timings_ms'],
                         'quality': audit['totals']})
        methods.append({'method': name, 'host_quality': quality['totals'],
                        'host_quality_by_rate': quality['by_rate'], 'arm_runs': runs,
                        'mean_outer_cpu_ms': sum(r['timings_ms']['fused_total'] for r in runs)/len(runs)})
    return {'scope': '704 mixed-rate host quality; four 2.5 MS/s saved dwells per ARM CPU0 run; outer CPU includes proposals, regions, conversion and search; excludes initial setup, file reads and capture',
            'methods': methods, 'evidence_sha256': evidence}


if __name__ == '__main__':
    (HERE / 'wave3-results.json').write_text(json.dumps(collect(), indent=2) + '\n')
