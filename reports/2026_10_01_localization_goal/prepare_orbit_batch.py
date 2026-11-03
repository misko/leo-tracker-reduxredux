"""Bounded causal orbit exports; retain verified matrices in the local cache."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from admit_heldout_orbit import admit
from prepare_heldout_batch import RUNTIME, verify_reader
from regression_batch import digest, execute, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--first', type=int, required=True)
    parser.add_argument('--last', type=int, required=True)
    args = parser.parse_args()
    if not 3 <= args.first <= args.last <= 16 or args.last-args.first >= 8:
        raise ValueError('select one to eight pending units H003-H016')
    selection_path = HERE/'ds12-heldout-selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(selection_path.read_text())
    units = selection['units'][args.first-1:args.last]
    directory = HERE/'held-out'/f'orbit-preparation-{args.first:02d}-{args.last:02d}'
    directory.mkdir(exist_ok=False)
    before = verify_reader()
    sources = [Path(__file__), HERE/'admit_heldout_orbit.py', HERE/'export_heldout_orbit.py',
               HERE.parent/'2026_09_30_gaussian_sum_single_scan/evidence.py',
               HERE.parent/'2026_10_01_fixed_height_greedy/extend_orbits.py']
    bindings = {str(p.resolve()): digest(p) for p in sources}
    (directory/'sources.json').write_text(json.dumps(bindings, indent=2))

    def run(unit):
        name = unit['unit_id']
        prefix = Path('/tmp/leo-localization-goal-'+name.lower()+'-bank-v1')
        verify_sources(bindings)
        command = ['sudo', '-n', '-u', 'leo', 'env', 'OPENBLAS_NUM_THREADS=1',
                   'OMP_NUM_THREADS=1', 'MKL_NUM_THREADS=1', 'timeout', '--kill-after=2s', '85s',
                   RUNTIME, str(HERE/'export_heldout_orbit.py'), name,
                   '--output-prefix', str(prefix)]
        launch = execute(command, directory, name, timeout_s=90.)
        verify_sources(bindings)
        with (directory/(name+'.launch.json')).open('x') as stream:
            json.dump(launch, stream, indent=2)
        if launch['returncode'] != 0 or launch['timed_out']:
            result = dict(unit=name, status='export_failed')
        else:
            cache = Path.home()/'.cache/leo/research/localization_goal/ds12'/name
            result = admit(HERE/'held-out'/name, prefix, cache)
            result.update(status='admitted', seconds=launch['elapsed_seconds'])
        with (directory/(name+'.admission.json')).open('x') as stream:
            json.dump(result, stream, indent=2)
        print(json.dumps(result), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, units))
    after = verify_reader()
    with (directory/'batch.json').open('x') as stream:
        json.dump(dict(selection_sha256=digest(selection_path), source_sha256=bindings,
                       reader_before=before, reader_after=after, results=results), stream, indent=2)


if __name__ == '__main__':
    main()
