"""Frozen fresh random20 confirmation for the multi-lane conditional methods."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import random

import probe_ds23_shared_probe_cohort as native
import probe_ds23_all_lane_components as components
import probe_ds23_all_lane_catalogue as catalogue
import probe_ds23_multilane_position as predictive
import probe_ds23_joint_multilane_position as joint
from run_algo01_ds23_sample import ROOT, DATASET, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_multilane_confirmation'
BULK = Path('/srv/bulk/leo/research/ds23-multilane-confirmation-20261020')


def configure():
    native.OUT, native.BULK = OUT, BULK
    components.OUT, components.BULK = OUT, BULK
    catalogue.OUT, catalogue.BULK = BULK/'catalogue', BULK
    predictive.OUT, predictive.BULK = BULK/'position', BULK
    joint.PREVIOUS, joint.OUT = BULK/'position', BULK/'joint_position'


def freeze():
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True)
    path = OUT/'selection.json'
    earlier = read(ROOT/'reports/2026_10_20_ds23_shared_probe_confirmation/selection.json')
    second = read(ROOT/'reports/2026_10_20_ds23_joint_probe_confirmation/selection.json')
    excluded = set(earlier['cases']) | set(second['cases']) | {'DS23-0202', 'DS23-0274'}
    if not path.exists():
        eligible = sorted(set(earlier['eligible_cases'])-excluded)
        write(path, dict(cases=random.Random(20261024).sample(eligible, 20), eligible_cases=eligible,
                         excluded_previous_cases=sorted(excluded), seed=20261024,
                         no_position_errors_or_RF_results_used_for_selection=True, same_DS23_site_not_new_location=True))
    protocol = dict(selection_sha256=sha(path), methods=list(predictive.METHODS)+list(joint.METHODS),
        frozen_before_new_scan_RF_results=True, no_GPS_used=True, no_new_RF_collection=True,
        conditional_per_lane_covariance=True, old_observations_gates_and_priors_preserved=True,
        linear_data_never_calibrate=True, matched_c0_fitted_c=True, cold_start=[0, 0], regional_width_km=25,
        phase_rounds=5, position_iterations=48, per_scan_method_group_seconds=300,
        raw_export_seconds_per_scan=120, maximum_raw_windows_per_scan=8192,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/probe_ds23_all_lane_components.py',
            ROOT/'tools/probe_ds23_all_lane_catalogue.py', ROOT/'tools/probe_ds23_multilane_position.py',
            ROOT/'tools/probe_ds23_joint_multilane_position.py', ROOT/'tools/ds23_multilane_prediction.py',
            ROOT/'tools/ds23_joint_multilane_calibration.py']})
    target = OUT/'workflow_protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('multi-lane confirmation workflow changed')
    if not target.exists():
        write(target, protocol)


def prepare_IQ():
    # Same maximum-coverage geometry-only selection per lane as the3-scan
    # pilot, using this independently frozen20-scan membership.
    cases = read(OUT/'selection.json')['cases']; jobs, selected, bindings = [], [], {}
    evaluations, previous = read(BULK/'curves/evaluation.json'), read(BULK/'curves/protocol.json')
    for case in cases:
        document = read(components.iq.SOURCE/case/'tracking.json'); source = document.get('source', document)
        bindings[case] = dict(tracking_sha256=sha(components.iq.SOURCE/case/'tracking.json'))
        for lane in [r for r in evaluations['rows'] if r['case'] == case and r['status'] == 'complete']:
            pairs = [p for p in lane['pairs'] if all(p['geometry_checks'].values())]
            if not pairs:
                continue
            pair = max(pairs, key=lambda p: (len(p['probes']), p['first'], p['second']))
            paths = {p['key']: p for p in lane['paths']}
            original = next(j for j in previous['jobs'] if j['case'] == case and j['lane'] == lane['lane'])
            group = case+f"_RX{lane['lane'][0]}_CH{lane['lane'][1]}"
            for k, pi in enumerate(pair['probes']):
                probe = source['probes'][pi]
                if source['probe_ms'] != 20 or probe['probe_start_ms'] != 0:
                    raise ValueError('complete original20ms probe required')
                peaks, values = [], []
                for role in ('first', 'second'):
                    path = paths[pair[role]]; index = path['probes'].index(pi)
                    peaks.append(original['candidates'][path['peak_indices'][index]]); values.append(path['values'][index])
                jobs.append(dict(case=case, group=group, probe=pi, paired_index=k, time_s=pair['time_s'][k], lane=lane['lane'],
                    visit_index=probe['visit_index'], sample_counter=probe['valid_start_counter'], native_receiver_id=probe['receiver_id'],
                    edge=probe['edge'], first=peaks[0], second=peaks[1], first_lifted_value=values[0], second_lifted_value=values[1]))
            selected.append(dict(case=case, group=group, lane=lane['lane'], pair=pair, sample_rate_hz=original['sample_rate_hz']))
    for case in cases:
        components.visit_groups([j for j in jobs if j['case'] == case])
    protocol = dict(cases=cases, jobs=jobs, selected=selected, bindings=bindings,
        dataset_manifest_sha256=sha(DATASET/'manifest.json'), maximum_windows_per_case=8192, maximum_export_seconds=120,
        maximum_analysis_seconds_per_probe=20, workers=12, no_new_RF_collection=True,
        workflow_protocol_sha256=sha(OUT/'workflow_protocol.json'),
        source_sha256={p.name: sha(p) for p in [ROOT/'tools/probe_ds23_all_lane_components.py',
            ROOT/'tools/probe_ds23_same_probe_IQ.py', ROOT/'tools/ds23_conditional_pilot_components.py', Path(__file__)]})
    path = BULK/'protocol.json'
    if path.exists() and read(path) != protocol:
        raise ValueError('fresh multi-lane IQ selection changed')
    if not path.exists():
        write(path, protocol)
    print('FRESH_MULTI_LANE_IQ', len(jobs), 'probes', len(selected), 'lanes', flush=True)


def position_job(case, joint_mode):
    configure()
    if joint_mode:
        old_path = BULK/'position'/(case+'.json')
        if read(old_path)['status'] != 'complete':
            record = dict(case=case, status='no_offer', reason='no eligible supported conditional evidence; exact original incumbent fallback')
            write(BULK/'joint_position'/(case+'.json'), record)
            return record
        return joint.run(case)
    d = predictive.prepare_inputs(case)
    if not d['extra']:
        record = dict(case=case, status='no_offer', reason='no eligible supported conditional evidence; exact original incumbent fallback',
                      diagnostics=d['diagnostics'], signed_incumbent_path=str(d['signed_path'].relative_to(ROOT)),
                      signed_incumbent_sha256=sha(d['signed_path']))
        write(BULK/'position'/(case+'.json'), record)
        return record
    return predictive.run(case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['curves', 'prepare_IQ', 'export', 'analyze', 'catalogue', 'position', 'joint'])
    parser.add_argument('--case'); args = parser.parse_args()
    configure(); freeze()
    if args.stage == 'curves':
        native.curves()
    elif args.stage == 'prepare_IQ':
        prepare_IQ()
    elif args.stage == 'export':
        components.export(args.case)
    elif args.stage == 'analyze':
        components.analyze()
    elif args.stage == 'catalogue':
        catalogue.main()
    else:
        target = BULK/('joint_position' if args.stage == 'joint' else 'position'); target.mkdir(exist_ok=True)
        cases = read(OUT/'selection.json')['cases']
        with ProcessPoolExecutor(max_workers=10) as pool:
            rows = [f.result() for f in as_completed([pool.submit(position_job, c, args.stage == 'joint') for c in cases])]
        write(target/'execution.json', dict(rows=rows, all_terminal=True, all20_in_denominator=True,
                                           workflow_protocol_sha256=sha(OUT/'workflow_protocol.json')))


if __name__ == '__main__':
    main()
