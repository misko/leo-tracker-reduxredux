"""Measured ARM summaries; proposal addition remains explicitly a stage sum."""
import hashlib
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent


def main():
    sources = {}
    def read(path):
        data = path.read_bytes()
        sources[str(path.relative_to(HERE.parent))] = hashlib.sha256(data).hexdigest()
        return json.loads(data)
    proposal = read(HERE.parent/'2026_09_29_arm_fine_reuse/arm-aggregate.json')['proposal_fp32_separate_ms']
    groups = {
        'baseline': [HERE/'arm4-baseline-v1'],
        'raw_fp32': [HERE/'arm4-raw-v2', HERE/'arm4-raw-v2-repeat'],
        'guarded_fp32': [HERE/'arm4-guarded-v2', HERE/'arm4-guarded-v2-repeat'],
        'batch4_fp64': [HERE.parent/'2026_09_29_arm_fine_batch/arm4-batch4-v1'],
        'batch16_fp64': [HERE.parent/'2026_09_29_arm_fine_batch/arm4-batch16-v1'],
    }
    result = {}
    for name, folders in groups.items():
        runs = [read(folder/'summary.json') for folder in folders]
        for folder, run in zip(folders, runs, strict=True):
            assert run['complete'] and run['hardware'] == 'PLUTO+ CPU0'
            assert hashlib.sha256((folder/'rows.jsonl').read_bytes()).hexdigest() == run['rows_sha256']
        timings = {k: sum(r['mean_timings_ms'][k] for r in runs)/len(runs) for k in runs[0]['mean_timings_ms']}
        result[name] = {'runs': [f.name for f in folders], 'mean_search_timings_ms': timings,
                        'search_plus_separately_measured_proposal_ms': timings['total_cpu']+proposal}
    base = result['baseline']['mean_search_timings_ms']['total_cpu']
    for value in result.values():
        total = value['mean_search_timings_ms']['total_cpu']
        value['search_speedup'] = base/total
        value['search_cpu_reduction_fraction'] = 1-total/base
    output = {'scope': 'Four unique saved 2.5 MS/s dwells, CPU0, no RF/concurrent capture; raw and guarded average two runs. Repeats do not enlarge the cohort.',
              'proposal_ms_separately_measured': proposal, 'methods': result, 'source_sha256': sources}
    diagnostic = read(HERE/'arm4-raw-diagnostic-v3/summary.json')
    assert diagnostic['scientific_outputs_identical']
    profile = {'scope': 'v3 attribution only; timers add overhead, candidate objects identical to ARM raw-v2',
               'summary_sha256': sources['2026_09_29_arm_fine_precision/arm4-raw-diagnostic-v3/summary.json'],
               'mean_ms_per_dwell': {k: v/diagnostic['dwells'] for k, v in diagnostic['fine_instrumentation_totals'].items() if k.endswith('_ms')}}
    (HERE/'fine-stage-profile.json').write_text(json.dumps(profile, indent=2)+'\n')
    (HERE/'arm-aggregate.json').write_text(json.dumps(output, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
