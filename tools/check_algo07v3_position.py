"""External bounded exact oracle for joint position likelihood and descent.

Each side independently nominates a zero-calibration hypothesis from the full
causal bank. This is one declared hypothesis test, not full production discovery,
recovery or publication. Reference worker imports occur only in reference mode.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from check_algo07v3_scan_likelihood import fingerprint


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    if args.side == 'candidate':
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from leo.analysis.localization_v3.discovery import fresh_discovery
        from leo.analysis.localization_v3.families import AnchoredFamilies, nomination_rows
        from leo.analysis.localization_v3.position import NormalPosition as Position
        from leo.analysis.localization_v3.position import fit
        from leo.analysis.localization_v3.region import SearchRegion
        from leo.analysis.localization_v3.scan import ScanLikelihood
    else:
        if args.reference_runtime is None:
            raise ValueError('Explicit reference runtime required')
        sys.path[:0] = [str(args.reference_runtime/'src'), str(args.reference_runtime/'tools')]
        from evaluate_ds23_phase_refreshed import FreshScan
        from investigate_dsx01_localization_failures import DiagnosticNormal as Position
        from investigate_dsx01_localization_failures import fit
        from iterate_dsx01_position_nominations import AnchoredFamilies, nomination_rows
        from prototype_dsx01_continuous_position import CENTER, native_point
        from run_dsx01_clean_region import fresh_discovery

        if tuple(args.search_center) != tuple(CENTER):
            raise ValueError('Reference has a frozen search center; it cannot be overridden')

    import numpy as np

    from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

    def read(name):
        return json.loads((args.source/name).read_text())

    started = time.monotonic()
    if args.side == 'candidate':
        summary = read('summary.json')
        for name, sha in summary['source_files'].items():
            if digest(args.source/name) != sha:
                raise ValueError('Candidate preparation binding differs')
        metadata = read('metadata.json')
        with np.load(args.source/'bank.npz') as arrays:
            bank = dict(arrays)
        region = SearchRegion(tuple(args.search_center))
        scan = ScanLikelihood(read('tracks.json')['tracks'], bank, read('nominal_elements.json'),
            origin_utc_ns=metadata['origin_utc_ns'], regional_center=metadata['regional_center'],
            noise=read('radio_noise.json'), noise_sha256=digest(args.source/'radio_noise.json'),
            search_region=region, previous_tle=(args.source/'previous.tle').read_text(),
            previous_tle_sha256=digest(args.source/'previous.tle'))
        point = region.native_point(scan, [0., 0.])
    else:
        scan = FreshScan(args.source, noise_mode='radio')
        point = native_point(scan, [0., 0.])
    if args.discovery:
        result = dict(candidates=fingerprint(fresh_discovery(
            scan, scan.radio_sigma_hz, budget=args.seed_budget)))
    else:
        base = phase_linear_frequency(scan.geometry, *args.search_center)
        state = dict(beta=np.zeros(8), phases=np.zeros(len(scan.norads)), extra={},
                     smooth=np.zeros((2, scan.rx_basis[0].shape[1])))
        _, rows, nominees, _ = scan.association(state, base, point, 'receiver_smooth')
        seed = dict(state=state, rows=nomination_rows(scan, rows, nominees))
        anchored = AnchoredFamilies(scan, seed, 'receiver_smooth', False, [0., 0.])
        node = dict(seed=seed, aliases=anchored.alias)
        result = dict(node=fingerprint(node), arms={})
        for arm in ('c0', 'fitted_c'):
            problem = Position(scan, node, scan.radio_sigma_hz, arm == 'fitted_c')
            names = ('rows', 'members', 'labels', 'flat_labels', 'flat_times', 'alias', 'reference',
                     'phase_sigma', 'values', 'q', 'hardware', 'smooth', 'constants', 'supported',
                     'supported_local', 'mode_bank', 'mode_metadata', 'initial', 'lower', 'upper',
                     'noise_groups', 'point_noise', 'keep', 'noise_volume')
            record = dict(design={name:fingerprint(getattr(problem, name)) for name in names},
                          evaluations=[], fits=[])
            for xy in ([0., 0.], [3., -4.], [-7., 8.]):
                x = np.asarray(xy)
                record['evaluations'].append(dict(point=xy,
                    calculated=fingerprint(problem.calculate(x)),
                    residual=fingerprint(problem.residual(x)), state=fingerprint(problem.state(x)),
                    conditional_frequency=fingerprint(problem.conditional_frequency(x))))
            print(arm, 'design and three evaluations complete', flush=True)
            phase, anchor = np.zeros(len(problem.labels)), np.zeros(2)
            for epoch in range(args.rounds):
                problem = Position(scan, node, scan.radio_sigma_hz, arm == 'fitted_c',
                                   reference=phase)
                fitted = fit(problem, anchor, iterations=args.iterations)
                anchor = np.array(fitted['parameters'])
                posterior = problem.state(anchor)['phases'][problem.labels]
                record['fits'].append(fingerprint(dict(epoch=epoch, fit=fitted,
                    phase_reference=phase.copy(), posterior_phase_s=posterior,
                    max_reference_change_s=float(np.max(abs(posterior-phase))))))
                phase = np.clip(posterior, -15, 15)
                print(arm, 'phase round', epoch, 'complete', flush=True)
            result['arms'][arm] = record
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, allow_nan=False)
        stream.write('\n')
    modules = {name:str(module.__file__) for name, module in sys.modules.items()
               if getattr(module, '__file__', None) and (name.startswith('leo.')
               or (args.side == 'reference'
                   and str(module.__file__).startswith(str(args.reference_runtime))))}
    receipt = dict(side=args.side, source=str(args.source), seconds=time.monotonic()-started,
        output_sha256=digest(args.output), rounds=args.rounds, iterations=args.iterations,
        discovery=args.discovery, seed_budget=args.seed_budget,
        search_center=args.search_center, full_localization_parity=False,
        modules={name:dict(path=path, sha256=digest(Path(path))) for name,path in modules.items()},
        inputs={name:digest(args.source/name) for name in ('tracks.json', 'bank.npz',
               'nominal_elements.json', 'radio_noise.json', 'previous.tle')})
    with args.output.with_suffix('.receipt.json').open('x') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({k:receipt[k] for k in ('side','seconds','output_sha256')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--side', choices=('reference', 'candidate'), required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-runtime', type=Path)
    parser.add_argument('--search-center', type=float, nargs=2, required=True)
    parser.add_argument('--rounds', type=int, default=2)
    parser.add_argument('--iterations', type=int, default=8)
    parser.add_argument('--discovery', action='store_true')
    parser.add_argument('--seed-budget', type=int, default=4)
    run(parser.parse_args())
