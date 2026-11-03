"""Exercise actual native paired epochs across boundary and partial-support cases."""

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from probe_native_screen import screen_grid
from profile_algo07_glrt import PROFILE, use_source
from stage_native_glrt_runtime import digest, verify_files


def load(root, name):
    path = next((root/'src/leo/analysis/starlink').glob('_native_acquisition*.so'))
    spec = importlib.util.spec_from_file_location(name+'._native_acquisition', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.folded_anchor_score_grid_backend() != 'avx2_fma':
        raise RuntimeError('Explicit AVX-VNNI hardware required for native boundary checks')
    return module


def run(candidate, output):
    receipt_path = candidate/'epoch-pair.json'
    receipt_pin = digest(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    original = Path(receipt['source'])
    source_path = original/'screen-probe.json'
    if digest(source_path) != receipt['source_receipt_sha256']:
        raise ValueError('Original screen changed')
    base = json.loads(source_path.read_text())
    verify_files(original, base['files_sha256'])
    verify_files(candidate, receipt['files_sha256'])
    use_source(Path(base['base']))
    from leo.analysis.starlink import acquisition

    old, new = load(original, '_original'), load(candidate, '_paired')
    g = SimpleNamespace(OFDM_SYMBOL_DURATION_S=.0001, FRAME_RATE_HZ=1000,
                        _power_prefix=acquisition._power_prefix)
    rng = np.random.default_rng(20261103)
    rows = []
    for taps in (1, 2, 44, 4096):
        for epochs in (1, 2, 3, 64, 65):
            size = max(3*taps+epochs-1, 10*taps+epochs+taps//2)
            template = rng.normal(size=3*taps)+1j*rng.normal(size=3*taps)
            for maximum in (127, 32767):
                noise = (rng.integers(-maximum, maximum+1, size)
                         + 1j*rng.integers(-maximum, maximum+1, size))
                patterns = [('noise', noise), ('constant', np.full(size, maximum*(1+1j))),
                            ('zero-tail', np.r_[noise[:size//2], np.zeros(size-size//2)])]
                for pattern, values in patterns:
                    for count in (1, 21, 25):
                        args = (values, template, taps*10_000.,
                                tuple(np.linspace(-taps*1000, taps*1000, count)),
                                (0, 1, 2), epochs)
                        expected = np.asarray(screen_grid(old, g, *args))
                        actual = np.asarray(screen_grid(new, g, *args))
                        np.testing.assert_array_equal(expected.view(np.uint64),
                                                      actual.view(np.uint64))
                        rows.append(dict(taps=taps, epochs=epochs, maximum=maximum,
                                         pattern=pattern, frequencies=count,
                                         exact_values=actual.size, bit_exact=True))
    verify_files(original, base['files_sha256'])
    verify_files(candidate, receipt['files_sha256'])
    if (digest(receipt_path) != receipt_pin
            or digest(source_path) != receipt['source_receipt_sha256']):
        raise ValueError('Native receipts changed')
    result = dict(summary=dict(cases=len(rows), all_bit_exact=True,
                               exact_values=sum(r['exact_values'] for r in rows),
                               production_modified=False), rows=rows, build_pin=receipt_pin,
                  source_pins={n: digest(Path(__file__).with_name(n)) for n in
                               ('check_integer_epoch_pair.py', 'probe_native_screen.py')})
    PROFILE.write_new(output, result)
    return result['summary']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.resolve().is_relative_to('/srv/bulk/leo/research'):
        raise ValueError('New private diagnostic output required')
    print(json.dumps(run(args.candidate.resolve(strict=True), args.output)))
