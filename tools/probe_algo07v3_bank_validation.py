"""External immutable-bank experiment; alternate complete exact screen trials."""

import argparse
import hashlib
import inspect
import json
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

import algo07v3_prebank_phase_oracle as orbit_phase_geometry
import algo07v3_prebank_screen_oracle as residual_screen
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import screen_geometry
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.track_catalogue_geometry import interpolate_states
from leo.operations.localization_v3_job import runtime_versions
from leo.storage.localization_v3 import LocalizationV3Store

KEYS = ('time_s', 'position_km', 'velocity_km_s')


@dataclass(frozen=True, init=False, eq=False)
class FrozenOrbitBank:
    """An independently owned, validated snapshot with immutable byte buffers."""

    _entries: tuple

    def __init__(self, bank):
        entries = []
        for key in KEYS:
            source = np.asarray(bank[key], float)
            entries.append((source.tobytes(), source.shape))
        object.__setattr__(self, '_entries', tuple(entries))
        interpolate_states(self, np.array([], float))

    def __getitem__(self, key):
        if key not in KEYS:
            raise KeyError(key)
        data, shape = self._entries[KEYS.index(key)]
        return np.frombuffer(data, dtype=float).reshape(shape)


def replace_once(source, before, after):
    if source.count(before) != 1:
        raise ValueError('Review exact source boundary: ' + before)
    return source.replace(before, after)


def candidate():
    originals, changed = {}, {}
    original = inspect.getsource(orbit_phase_geometry.phase_shifted_states)
    originals['phase_states'] = original
    modified = replace_once(original,
        '    interpolate_states(bank, np.array([], float))',
        '    if not isinstance(bank, FrozenOrbitBank):\n'
        '        interpolate_states(bank, np.array([], float))')
    changed['phase_states'] = modified
    scope = dict(vars(orbit_phase_geometry), FrozenOrbitBank=FrozenOrbitBank)
    exec(compile(modified, '<validated-phase>', 'exec'), scope)
    original = inspect.getsource(screen_geometry.phase_frequency_grids)
    originals['frequency_grids'] = changed['frequency_grids'] = original
    projection_scope = dict(vars(screen_geometry),
                            phase_shifted_states=scope['phase_shifted_states'])
    exec(compile(original, '<validated-grid>', 'exec'), projection_scope)
    original = inspect.getsource(residual_screen._nomination_grids)
    originals['nomination_grids'] = changed['nomination_grids'] = original
    nomination_scope = dict(vars(residual_screen),
                            phase_frequency_grids=projection_scope['phase_frequency_grids'])
    exec(compile(original, '<validated-nomination>', 'exec'), nomination_scope)
    original = inspect.getsource(residual_screen.screen_candidates)
    originals['screen'] = original
    modified = replace_once(original, '    outputs = []',
        '    if packet["targets"]:\n        bank = FrozenOrbitBank(bank)\n    outputs = []')
    changed['screen'] = modified
    screen_scope = dict(vars(residual_screen), FrozenOrbitBank=FrozenOrbitBank,
                        _nomination_grids=nomination_scope['_nomination_grids'])
    exec(compile(modified, '<validated-screen>', 'exec'), screen_scope)
    return screen_scope['screen_candidates'], scope['phase_shifted_states'], originals, changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or len(os.sched_getaffinity(0)) != 1:
        parser.error('Pin one CPU and one BLAS thread')
    root = args.output.resolve()
    if root.is_relative_to('/mnt/qnap01'):
        raise ValueError('QNAP is read-only')
    root.mkdir(exist_ok=False)
    paths = [*Path('src').rglob('*.py'), args.request, Path(__file__),
             Path('tools/check_algo07v3_scan_likelihood.py'), Path(residual_screen.__file__),
             Path(orbit_phase_geometry.__file__)]
    bindings = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    request = json.loads(args.request.read_bytes())
    assert runtime_versions() == request['runtime']
    saved = LocalizationV3Store(request['output_root']).load(request['identity']['run_id'])
    evidence = saved['evidence']
    packet = evidence['audit']['additional_recovery']['preflight']
    catalogue, expected = evidence['catalogue'], evidence['audit']['residual_screen']['screen']
    before = fingerprint((packet, catalogue))
    operation, _, originals, changed = candidate()
    for label, sources in (('original', originals), ('candidate', changed)):
        for name, source in sources.items():
            (root / f'{label}-{name}.py').write_text(source)
    (root / 'plan.json').write_text(json.dumps(dict(bindings=bindings, repeats=3,
        cpus=list(os.sched_getaffinity(0)), blas_threads=1, runtime_modified=False), indent=2)+'\n')
    rows = []
    for pair in range(3):
        order = ('baseline', 'candidate') if pair % 2 == 0 else ('candidate', 'baseline')
        for side in order:
            callbacks = []
            function = residual_screen.screen_candidates if side == 'baseline' else operation
            began, cpu = time.perf_counter(), time.process_time()
            result = function(packet, catalogue, SearchRegion(tuple(request['search_center'])),
                              on_target=callbacks.append)
            elapsed, used = time.perf_counter() - began, time.process_time() - cpu
            exact = (fingerprint(result) == fingerprint(expected)
                     and fingerprint(callbacks) == fingerprint(expected['targets']))
            unchanged = before == fingerprint((packet, catalogue))
            row = dict(pair=pair, side=side, seconds=elapsed, cpu_seconds=used,
                       exact=exact, unchanged_inputs=unchanged)
            rows.append(row)
            (root / f'{pair}-{side}.json').write_text(json.dumps(row, indent=2)+'\n')
            print(json.dumps(row), flush=True)
            assert exact and unchanged, 'Complete screen mismatch; retain failed receipt'
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in bindings.items())
    means = {side: {k: statistics.mean(r[k] for r in rows if r['side'] == side)
                    for k in ('seconds', 'cpu_seconds')} for side in ('baseline', 'candidate')}
    result = dict(rows=rows, means=means, exact=True, bindings=bindings,
                  scientific_receipt=saved['sha256'], full_pipeline_speedup=None,
                  runtime_modified=False)
    (root / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(means=means)), flush=True)


if __name__ == '__main__':
    main()
