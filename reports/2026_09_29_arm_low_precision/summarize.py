"""Collect completed low-precision experiments without mixing cohort denominators."""
import hashlib
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    results = {}
    for folder in sorted(HERE.iterdir()):
        summary = folder/'summary.json'
        audit = folder/'standard-audit.json'
        if not summary.is_file() or not audit.is_file():
            continue
        s = json.loads(summary.read_text())
        a = json.loads(audit.read_text())
        manifest = json.loads((folder/'manifest.json').read_text())
        assert s['complete'] and manifest['complete']
        digest = hashlib.sha256((folder/'rows.jsonl').read_bytes()).hexdigest()
        assert digest == s['rows_sha256'] == a['native_sha256'] == manifest['rows_sha256']
        assert hashlib.sha256((folder/'build-receipt.json').read_bytes()).hexdigest() == s['build_sha256']
        native = [json.loads(line) for line in (folder/'rows.jsonl').read_text().splitlines()]
        kernel_calls = sum(r['candidate_count'] + r['conditioned_fallback_count'] for d in native for r in d['rows'])
        results[folder.name] = {
            'hardware': s['hardware'], 'dwells': s['dwells'], 'windows': s['windows'],
            'search_cpu_ms_per_dwell': s['mean_timings_ms']['total_cpu'],
            'fine_cpu_ms_per_dwell': s['mean_timings_ms']['fine_fft'],
            'candidate_entries': s['candidate_entries'],
            'actual_glrt_kernel_calls': kernel_calls,
            'standard_hits': a['totals']['reference_positive_hits'],
            'recovered_hits': a['totals']['recovered_positive_hits'],
            'unmatched_hits': a['totals']['unmatched_positive_hits'],
            'candidate_objects_changed_vs_reference': s['changed_candidates'],
            'by_rate': {k: {n: v[n] for n in ('reference_positive_hits', 'recovered_positive_hits', 'unmatched_positive_hits')} for k,v in a['by_rate'].items()},
            'instrumentation': s['fine_instrumentation_totals'],
            'summary_sha256': hashlib.sha256(summary.read_bytes()).hexdigest(),
            'audit_sha256': hashlib.sha256(audit.read_bytes()).hexdigest(),
        }
    (HERE/'results.json').write_text(json.dumps(results, indent=2)+'\n')
    for name, r in results.items():
        print(name, round(r['search_cpu_ms_per_dwell'], 3),
              f"{r['recovered_hits']}/{r['standard_hits']}", 'extra', r['unmatched_hits'])


if __name__ == '__main__':
    main()
