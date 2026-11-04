"""External exact scoring oracle; old implementations never enter v3 inference.

Run each side in its own Python environment and compare the resulting JSON bytes.
All array elements are bound by dtype/shape/content hashes to keep evidence small.
This exercises scoring at declared states, not position optimization.
"""
import argparse
import dataclasses
import hashlib
import json
import sys
import time
from pathlib import Path


def fingerprint(value):
    import numpy as np

    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise ValueError('Object arrays are not scientific fingerprints')
        return dict(type='array', dtype=value.dtype.str, shape=list(value.shape),
                    sha256=hashlib.sha256(value.tobytes(order='C')).hexdigest())
    if isinstance(value, np.generic):
        return fingerprint(np.asarray(value))
    if dataclasses.is_dataclass(value):
        return {f.name:fingerprint(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k):fingerprint(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [fingerprint(v) for v in value]
    if isinstance(value, float):
        return dict(type='float', hex=value.hex())
    if value is None or isinstance(value, (int, str, bool)):
        return value
    raise TypeError(type(value).__name__)


def run(args):
    if args.side == 'candidate':
        from check_algo07v3_track_preparation import deny_legacy

        sys.addaudithook(deny_legacy)
        from leo.analysis.localization_v3.scan import ScanLikelihood
    else:
        if args.reference_runtime is None:
            raise ValueError('Reference runtime must be explicitly pinned')
        sys.path[:0] = [str(args.reference_runtime/'src'), str(args.reference_runtime/'tools')]
        from evaluate_ds23_phase_refreshed import FreshScan

    import numpy as np

    from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

    def read(name):
        return json.loads((args.source/name).read_text())

    began = time.monotonic()
    if args.side == 'candidate':
        summary = read('summary.json')
        for name, sha in summary['source_files'].items():
            if hashlib.sha256((args.source/name).read_bytes()).hexdigest() != sha:
                raise ValueError('Candidate preparation binding differs')
        metadata = read('metadata.json')
        with np.load(args.source/'bank.npz') as arrays:
            bank = dict(arrays)
        scan = ScanLikelihood(read('tracks.json')['tracks'], bank, read('nominal_elements.json'),
                              origin_utc_ns=metadata['origin_utc_ns'],
                              regional_center=metadata['regional_center'],
                              noise=read('radio_noise.json'))
    else:
        scan = FreshScan(args.source, noise_mode='radio')
    fields = ('curved', 'times', 'index', 'groups', 'geometry', 'norads', 'sigma',
              'initial', 'center', 'scale', 'white', 'ou', 'rx_basis', 'elements', 'radio_sigma_hz')
    result = dict(context={name:fingerprint(getattr(scan, name)) for name in fields}, cases={})
    base = phase_linear_frequency(scan.geometry, *scan.center)
    for label, coefficients, shifted, method in (
            ('c0', 8, False, 'shared_phase'), ('fitted_c', 9, False, 'receiver_smooth'),
            ('phase_shift', 9, True, 'receiver_smooth')):
        beta = np.arange(coefficients, dtype=float)*1.25
        phases = np.zeros(len(scan.norads))
        if shifted:
            phases[:3] = [.2, -.4, .6]
        smooth = np.zeros((2, scan.rx_basis[0].shape[1]))
        if coefficients == 9:
            smooth[:, 2] = [5., -7.]
        state = dict(beta=beta, phases=phases, extra={}, smooth=smooth)
        result['cases'][label] = fingerprint(scan.association(
            state, base, [0., 0.], method, all_tracks=True))
        print(label, 'scored', flush=True)
    result['element_basis'] = fingerprint(scan.element_basis(0))
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, allow_nan=False)
        stream.write('\n')
    modules = {name:str(module.__file__) for name, module in sys.modules.items()
               if getattr(module, '__file__', None) and (
                   name.startswith('leo.') or (args.side == 'reference'
                   and str(module.__file__).startswith(str(args.reference_runtime))))}
    receipt = dict(side=args.side, source=str(args.source),
        output_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
        modules={name:dict(path=path, sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
                 for name, path in modules.items()},
        inputs={name:hashlib.sha256((args.source/name).read_bytes()).hexdigest()
                for name in ('tracks.json', 'bank.npz', 'nominal_elements.json',
                             'radio_noise.json')},
        full_localization_parity=False)
    with args.output.with_suffix('.receipt.json').open('x') as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(side=args.side, seconds=time.monotonic()-began,
                          sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--side', choices=('reference', 'candidate'), required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-runtime', type=Path)
    run(parser.parse_args())
