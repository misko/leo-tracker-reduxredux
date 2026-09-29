"""Collect completed trials with separate proposal/search scopes and denominators."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
NAMES=('arm_frame_budget','arm_integrated_scorer','arm_padded_proposal',
       'arm_neon_proposal','arm_proposal_planner','arm_decimated_proposal',
       'arm_coarse_budget','arm_conditioned_moments','arm_float_scorer',
       'arm_float_glrt_fft','arm_final_reuse','arm_resampled_proposal',
       'arm_proposal_features','arm_subsecond')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    results={}
    for name in NAMES:
        folder=HERE.parent/('2026_09_29_'+name)
        for path in sorted(folder.glob('*/summary.json')):
            s=json.loads(path.read_text())
            if not s.get('complete'):continue
            cohort=path.parent
            entry={'summary_sha256':sha(path),'scope':s.get('scope'),
                   'binary_sha256':s.get('binary_sha256')}
            if 'candidate_entries' in s:
                entry.update(role='search',hardware=s['hardware'],dwells=s['dwells'],
                             windows=s['windows'],candidate_entries=s['candidate_entries'],
                             cpu_ms_per_dwell=s['mean_timings_ms']['total_cpu'])
                assert sha(cohort/'rows.jsonl')==s['rows_sha256']
                native=[r for line in (cohort/'rows.jsonl').read_text().splitlines()
                        for r in json.loads(line)['rows']]
                entry['logical_glrt_calls']=sum(r['candidate_count']+r['conditioned_fallback_count'] for r in native)
                entry['actual_glrt_calls']=sum(r.get('actual_executed_glrt_calls',r['candidate_count']+r['conditioned_fallback_count']) for r in native)
                entry['glrt_cache_hits']=sum(r.get('glrt_cache_hits',0) for r in native)
                entry['conditioned_cache_hits']=sum(r.get('conditioned_cache_hits',0) for r in native)
                audit=cohort/'standard-audit.json'
                if audit.is_file():
                    a=json.loads(audit.read_text());assert a['native_sha256']==s['rows_sha256']
                    entry.update(standard_hits=a['totals']['reference_positive_hits'],
                                 recovered_hits=a['totals']['recovered_positive_hits'],
                                 unmatched_hits=a['totals']['unmatched_positive_hits'],
                                 by_rate=a['by_rate'],audit_sha256=sha(audit))
            elif 'mean_timings_ms' in s:
                entry.update(role='proposal only',hardware='PLUTO+ CPU0',
                             cpu_ms_per_dwell=s['mean_timings_ms']['total'],
                             windows=s['unique_windows'],rank_mismatches=s['rank_mismatches'])
            else:
                entry.update(role='host proposal coverage only',windows=s.get('windows'),
                             top4_mismatches=s.get('top4_mismatches'))
            results[str(cohort.relative_to(HERE.parent))]=entry
    (HERE/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(len(results),'completed trials collected; missing audits are not recovery claims')

if __name__=='__main__':main()
