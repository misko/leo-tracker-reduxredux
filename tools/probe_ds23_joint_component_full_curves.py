"""Full archived pair curves following an RF-only joint-refinement pilot."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import probe_ds23_joint_component_refinement as pilot
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_joint_component_full_curves'
BULK = Path('/srv/bulk/leo/research/ds23-joint-component-full-curves-20261021')


def prepare():
    evidence = read(pilot.OUT/'evaluation.json'); old_protocol = read(pilot.OUT/'protocol.json')
    for name, digest in old_protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != digest: raise ValueError('pilot RF fitter changed')
    cases = sorted({r['case'] for r in evidence['rows'] if r['status'] == 'complete' and r['qualified_for_full_curve_test']})
    chosen = {r['case']: r['group'] for r in evidence['rows'] if r['case'] in cases}
    sources = {r['source'] for r in evidence['rows']}; jobs = []
    for source in sorted(sources):
        source = Path(source); native = read(source/'protocol.json'); saved = read(source/'evaluation.json')
        fits = {(r['case'], r['probe']): r for r in saved['rows'] if r['status'] == 'complete' and r['two_components_qualified']}
        for job in native['jobs']:
            if chosen.get(job['case']) == job['group'] and (job['case'], job['probe']) in fits:
                jobs.append(dict(job=job, fit=fits[job['case'], job['probe']], source=str(source)))
    return dict(cases=cases, jobs=jobs, workers=16, per_probe_seconds=90,
        case_selection='at least one of two phase-blind pilot probes passes both disjoint symbol predictions, parameter bounds and CFO consistency',
        same_native_component_pairs_and_no_position_or_satellite_selection=True,
        all_qualified_probes_on_selected_native_pair=True,
        prior_pilot_sha256=sha(pilot.OUT/'evaluation.json'), prior_protocol_sha256=sha(pilot.OUT/'protocol.json'),
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/probe_ds23_joint_component_refinement.py',
                                              ROOT/'tools/ds23_joint_component_refinement.py']})


def one(item):
    job = item['job']; name = job['group']+f"_probe{job['probe']:06d}.json"
    old, target = pilot.BULK/name, BULK/name
    if target.exists(): return read(target)
    if old.exists():
        result = read(old); result['reused_pilot_result_sha256'] = sha(old); write(target, result)
        return result
    original = pilot.BULK
    try:
        pilot.BULK = BULK
        return pilot.one(item)
    finally:
        pilot.BULK = original


def main():
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True); protocol = prepare(); path = OUT/'protocol.json'
    if path.exists() and read(path) != protocol: raise ValueError('full-curve joint RF protocol changed')
    if not path.exists(): write(path, protocol)
    rows = []
    with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
        for future in as_completed([pool.submit(one, item) for item in protocol['jobs']]):
            r = future.result(); rows.append(r)
            if len(rows) % 20 == 0 or len(rows) == len(protocol['jobs']):
                write(OUT/'progress.json', dict(terminal=len(rows), total=len(protocol['jobs']),
                    failures=[r for r in rows if r['status'] != 'complete']))
                print('JOINT_RF', len(rows), '/', len(protocol['jobs']), flush=True)
    write(OUT/'evaluation.json', dict(rows=rows, all_terminal=True, protocol_sha256=sha(path),
        complete=sum(r['status'] == 'complete' for r in rows),
        strict_RF_qualified=sum(r['status'] == 'complete' and r['qualified_for_full_curve_test'] for r in rows),
        no_position_error_evaluated=True))


if __name__ == '__main__': main()
