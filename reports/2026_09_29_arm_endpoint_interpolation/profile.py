"""Aggregate instrumented CPU time without double-counting nested timers."""
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

    exact = read(HERE.parent / '2026_09_28_arm_refinement_cache/arm-cohort-v2/summary.json')['timing_ms_per_dwell']
    boundary = read(HERE.parent / '2026_09_28_arm_boundary_fallback/arm-cohort-v1/summary.json')['timing_ms_per_dwell']
    fast_receipt = read(HERE.parent / '2026_09_29_arm_fine_reuse/arm-aggregate.json')
    fast = fast_receipt['mean_timings_ms']
    profiles = {}
    for name, row, proposal in [('exact_refinement_reuse', exact, 0), ('boundary_fallback', boundary, 0), ('restricted_lazy_fp32_stage_sum', fast, fast_receipt['proposal_fp32_separate_ms'])]:
        stages = {key: row[key] for key in ('coarse', 'fine_fft', 'conditioned', 'verification', 'glrt')}
        stages['other'] = row['total_cpu'] - sum(stages.values())
        stages['proposal'] = proposal
        profiles[name] = {'mean_cpu_ms_per_dwell': row['total_cpu'] + proposal,
                          'exclusive_stages_ms': stages,
                          'acquisition_parent_timer_not_added_ms': row['acquisition']}
    for name in ('pairs', 'union', 'union-fallback'):
        folder = HERE / f'arm4-{name}-v1'
        manifest = read(folder / 'manifest.json')
        assert manifest['complete']
        path = folder / 'rows.jsonl'
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        assert digest == manifest['rows_sha256']
        sources[str(path.relative_to(HERE.parent))] = digest
        rows = [json.loads(line) for line in data.splitlines()]
        stages = {key: sum(r['timings_ms'].get(key, 0) for d in rows for r in d['rows']) / len(rows)
                  for key in ('sample_preparation', 'endpoint_discovery', 'association', 'interpolation', 'local_glrt', 'fallback')}
        total = sum(r['timings_ms']['total_cpu'] for d in rows for r in d['rows']) / len(rows)
        assert abs(sum(stages.values()) - total) < 1e-6
        profiles['endpoint_' + name] = {'mean_cpu_ms_per_dwell': total, 'exclusive_stages_ms': stages}
    result = {'scope': '2.5 MS/s saved-IQ CPU0; four unique dual-RX dwells. No concurrent capture. Restricted method is a separately measured stage sum.',
              'profiles': profiles, 'source_sha256': sources}
    (HERE / 'runtime-profile.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
