"""Bounded confirmation on a seeded random set of other existing fast scans.

The bulk workspace contains intermediate metadata and existing-IQ panels. Only
derived scientific summaries belong in the repository; no new RF collection.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import random

from run_algo01_ds23_sample import ROOT, DATASET, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_shared_probe_confirmation'
BULK = Path('/srv/bulk/leo/research/ds23-shared-probe-confirmation-20261020')


def selection():
    path = OUT/'selection.json'
    if path.exists():
        return read(path)
    from probe_algo03_frame_peak_recovery import SOURCE
    available = read(ROOT/'reports/2026_10_20_ds23_combined_recovery_full/protocol.json')['available_cases']
    eligible = sorted(m['dataset_label'] for m in read(DATASET/'manifest.json')['members']
                      if m['recording_format'] == 'short_window_iq_recording'
                      and m['dataset_label'] in available
                      and m['dataset_label'] not in ('DS23-0202', 'DS23-0274')
                      and (SOURCE/m['dataset_label']/'tracking.json').exists())
    selected = random.Random(20261022).sample(eligible, min(20, len(eligible)))
    OUT.mkdir(parents=True, exist_ok=True)
    record = dict(cases=selected, eligible_cases=eligible, seed=20261022,
                  dataset_manifest_sha256=sha(DATASET/'manifest.json'),
                  selection_uses_no_position_error_or_RF_correlation=True,
                  same_DS23_site_not_new_location_confirmation=True,
                  workers=12, no_new_RF_collection=True, maximum_raw_export_seconds_per_case=120)
    write(path, record)
    return record


def native_job(job):
    import probe_ds23_same_probe_curves as native
    native.OUT = BULK/'curves'
    return native.run(job)


def curves():
    import probe_ds23_same_probe_curves as native
    cases = selection()['cases']
    target = BULK/'curves'
    target.mkdir(parents=True, exist_ok=True)
    protocol_path = target/'protocol.json'
    if protocol_path.exists():
        protocol = read(protocol_path)
    else:
        jobs = [job for case in cases for job in native.lanes(case)]
        protocol = dict(cases=cases, jobs=jobs, source_sha256=sha(ROOT/'tools/probe_ds23_same_probe_curves.py'),
                        selection_sha256=sha(OUT/'selection.json'), workers=12, GPS_used=False,
                        no_occupied_probe_exclusion=True, original_1200_trial_config_unchanged=True)
        write(protocol_path, protocol)
    with ProcessPoolExecutor(max_workers=12) as pool:
        rows = [future.result() for future in as_completed([pool.submit(native_job, job) for job in protocol['jobs']])]
    write(target/'evaluation.json', dict(rows=rows, pending=[], protocol_sha256=sha(protocol_path)))
    summaries = []
    for case in cases:
        group = [r for r in rows if r['case'] == case]
        pairs = [(r, p) for r in group for p in r.get('pairs', []) if all(p['geometry_checks'].values())]
        best = max(pairs, key=lambda x: (len(x[1]['probes']), x[1]['first'], x[1]['second'])) if pairs else None
        summaries.append(dict(case=case, complete_lanes=sum(r['status'] == 'complete' for r in group),
                              geometry_pairs=len(pairs), common_noise_candidates=sum(r.get('common_noise_candidates', 0) for r in group),
                              selected_pair=best[1] if best else None, selected_lane=best[0]['lane'] if best else None))
    write(OUT/'native_summary.json', dict(rows=summaries, bulk_evaluation_sha256=sha(target/'evaluation.json'),
                                         real_position_gain_not_yet_tested=True))


def IQ_module():
    import probe_ds23_same_probe_IQ as iq
    iq.OUT = BULK/'IQ'
    iq.PANELS = BULK/'panels'
    iq.CURVES = BULK/'curves'
    iq.CASES = tuple(r['case'] for r in read(OUT/'native_summary.json')['rows'] if r['selected_pair'])
    return iq


def analyze_job(job):
    return IQ_module().analyze(job)


def analyze():
    from ds23_same_probe_covariance import residual_pair
    iq = IQ_module()
    protocol = read(iq.OUT/'protocol.json')
    jobs = [j for j in protocol['jobs'] if (iq.PANELS/(j['case']+'.npz')).exists()]
    with ProcessPoolExecutor(max_workers=12) as pool:
        rows = [f.result() for f in as_completed([pool.submit(analyze_job, j) for j in jobs])]
    summary = {}
    for selected in protocol['selected']:
        case = selected['case']
        complete = sorted([r for r in rows if r['case'] == case and r['status'] == 'complete'], key=lambda r: r['time_s'])
        qualified = [r for r in complete if r['two_components_qualified']]
        summary[case] = dict(complete=len(complete), qualified_count=len(qualified))
        for name, subset in [('all_refined', complete), ('RF_qualified', qualified)]:
            if len(subset) >= 16:
                summary[case][name] = residual_pair([r['time_s'] for r in subset], [r['refined_first_value'] for r in subset],
                                                   [r['refined_second_value'] for r in subset], selected['pair']['degree'])
    write(iq.OUT/'evaluation.json', dict(rows=rows, pending=[], summary=summary,
                                        protocol_sha256=sha(iq.OUT/'protocol.json'), real_DS23_accuracy_gain=False))
    write(OUT/'RF_summary.json', dict(summary=summary, bulk_evaluation_sha256=sha(iq.OUT/'evaluation.json')))


def catalogue_job(case):
    import probe_ds23_differential_catalogue as catalogue
    catalogue.RF = BULK/'IQ'
    catalogue.OUT = BULK/'catalogue'
    return catalogue.run(case)


def position_job(case):
    import probe_ds23_shared_probe_position as position
    position.RF = BULK/'IQ'
    position.CATALOGUE = BULK/'catalogue'
    position.OUT = BULK/'position'
    return position.run(case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['curves', 'prepare_IQ', 'export', 'analyze', 'catalogue', 'position'])
    parser.add_argument('--case')
    args = parser.parse_args()
    selection()
    if args.stage == 'curves':
        curves()
    elif args.stage == 'prepare_IQ':
        protocol = IQ_module().prepare()
        print('CONFIRMATION_IQ', len(protocol['jobs']), 'probes', len(protocol['selected']), 'scans', flush=True)
    elif args.stage == 'export':
        IQ_module().export(args.case)
    elif args.stage == 'analyze':
        analyze()
    else:
        target = BULK/args.stage
        target.mkdir(parents=True, exist_ok=True)
        summary = read(BULK/'IQ/evaluation.json')['summary']
        cases = [c for c, r in summary.items() if 'RF_qualified' in r]
        function = catalogue_job if args.stage == 'catalogue' else position_job
        if args.stage == 'position':
            import probe_ds23_shared_probe_position as position
            protocol = dict(cases=cases, selection_sha256=sha(OUT/'selection.json'),
                            RF_evaluation_sha256=sha(BULK/'IQ/evaluation.json'),
                            catalogue_sha256={c: sha(BULK/'catalogue'/(c+'.json')) for c in cases},
                            source_sha256={p.name: sha(p) for p in [Path(__file__),
                                ROOT/'tools/probe_ds23_shared_probe_position.py',
                                ROOT/'tools/ds23_probe_conditioned_prediction.py']},
                            original_development_protocol_sha256=sha(position.OUT/'protocol.json'),
                            methods=list(position.METHODS), workers=8, per_case_seconds=240,
                            matched_c0_fitted_c=True, original_observations_and_gates_preserved=True,
                            no_GPS_used=True, nomination_must_agree_at_regional_centre_and_RF_mode=True,
                            failure_policy='exact original signed-prior incumbent, including nomination ambiguity or no new active anchors')
            path = OUT/'position_protocol.json'
            if path.exists() and read(path) != protocol:
                raise ValueError('confirmation position protocol changed')
            if not path.exists():
                write(path, protocol)
        with ProcessPoolExecutor(max_workers=8) as pool:
            rows = [f.result() for f in as_completed([pool.submit(function, c) for c in cases])]
        write(target/'execution.json', dict(rows=rows, all_terminal=True, cases=cases))


if __name__ == '__main__':
    main()
