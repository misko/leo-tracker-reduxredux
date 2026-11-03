"""Replay first/last paired probes per lane from hash-bound saved IQ."""

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import numpy as np

from ds23_conditional_pilot_components import conditional_component_prediction
from fast_local_pilot_refinement import FastPilotWorkspace
from probe_ds23_all_lane_components import OUT, BULK
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay(job):
    saved = read(BULK/'fits'/(job['case']+f"_probe{job['probe']:06d}.json"))
    with np.load(BULK/'panels'/(job['case']+'.npz'), allow_pickle=False) as archive:
        meta = json.loads(str(archive['metadata_json']))
        point = next(p for p in meta['points'] if p['probe'] == job['probe'])
        raw = archive[point['window_key']][:, point['receiver_offset']]
    y = raw[:, 0].astype(float)+1j*raw[:, 1].astype(float)
    fits = []
    for role in ('first', 'second'):
        workspace = FastPilotWorkspace(y, meta['sample_rate_hz'], job['edge'], job[role]['epoch'])
        fits.append(workspace.fast_joint_fit(job[role]['cfo_hz']))
    differences = [abs(fit['CFO_hz']-saved[role+'_fit']['CFO_hz']) for fit, role in zip(fits, ('first', 'second'), strict=True)]
    result = conditional_component_prediction(y, meta['sample_rate_hz'], job['edge'], job['first']['epoch'], fits[0], job['second']['epoch'], fits[1])
    interior = not any(f[k] for f in fits for k in ('frequency_search_boundary', 'epoch_search_boundary', 'code_rate_search_boundary'))
    if max(differences) > 1e-6 or (result['two_received_components_supported'] and interior) != saved['two_components_qualified']:
        raise ValueError('all-lane RF component qualification failed exact replay')
    scores = [abs(result['folds'][k][name]-saved['conditional']['folds'][k][name])
              for k in (0, 1) for name in ('first_exact_vs_control_loss', 'second_exact_vs_control_loss')]
    if max(scores) > 1e-6:
        raise ValueError('held-out component-specificity control failed replay')
    return dict(case=job['case'], group=job['group'], probe=job['probe'], maximum_CFO_difference_hz=max(differences),
                maximum_control_loss_difference=max(scores), two_components_qualified=saved['two_components_qualified'])


def main():
    protocol = read(BULK/'protocol.json')
    for name, expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name) != expected:
            raise ValueError('all-lane RF source changed')
    bindings = {r['case']: r['sha256'] for r in read(OUT/'read_only_exports.json')['rows']}
    for case in protocol['cases']:
        if sha(BULK/'panels'/(case+'.npz')) != bindings[case]:
            raise ValueError('saved IQ panel changed')
    jobs = []
    for selected in protocol['selected']:
        group = sorted([j for j in protocol['jobs'] if j['group'] == selected['group']], key=lambda j: j['time_s'])
        jobs.extend([group[0], group[-1]])
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = [f.result() for f in as_completed([pool.submit(replay, job) for job in jobs])]
    write(OUT/'independent_RF_audit.json', dict(rows=rows, independently_refitted_probes=len(rows),
          coverage='first and last selected probes per lane, not all508', protocol_sha256=sha(BULK/'protocol.json'),
          evaluation_sha256=sha(BULK/'evaluation.json'), panel_sha256=bindings,
          no_GPS_or_new_RF=True, no_position_gain_claim=True))
    print('ALL_LANE_RF_REPLAY', len(rows), 'probes', flush=True)


if __name__ == '__main__':
    main()
