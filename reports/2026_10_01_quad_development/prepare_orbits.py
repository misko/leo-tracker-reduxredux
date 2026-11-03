"""Bounded causal orbit preparation for already exported pilot observations."""
import json
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

HERE = Path(__file__).resolve().parent
GOAL = HERE.parent/'2026_10_01_localization_goal'
sys.path.insert(0,str(GOAL))
from regression_batch import digest, execute
from admit_heldout_orbit import admit
from prepare_heldout_batch import verify_reader, RUNTIME


def main():
    selection = json.loads((HERE/'selection.json').read_text())
    assert digest(HERE/'selection.json') == (HERE/'selection.sha256').read_text().strip()
    captures = [c for c in selection['captures'] if c['block_id'].endswith('-B01')]
    before = verify_reader()
    directory = HERE/'orbit-preparation-v1'
    directory.mkdir(exist_ok=False)
    # F001 was exported and admitted as the bounded initial integration check.
    def run(capture):
        unit = capture['unit_id']
        target = HERE/'prepared'/unit
        if (target/'orbits-extended.json').exists():
            return dict(unit=unit,status='previously_admitted',metadata_sha256=digest(target/'orbits-extended.json'))
        if not (target/'observations.json').exists():
            return dict(unit=unit,status='missing_observations')
        prefix = Path('/tmp')/('leo-quad-orbit-v1-'+unit)
        command = ['sudo','-n','-u','leo','env','OPENBLAS_NUM_THREADS=1',
                   'OMP_NUM_THREADS=1','MKL_NUM_THREADS=1',RUNTIME,str(HERE/'export_orbit.py'),
                   unit,'--output-prefix',str(prefix)]
        launch = execute(command,directory,unit,timeout_s=90.)
        (directory/(unit+'.launch.json')).write_text(json.dumps(launch,indent=2))
        if launch['returncode'] or launch['timed_out']:
            result = dict(unit=unit,status='export_failed',launch=launch)
        else:
            result = admit(target,prefix,Path.home()/'.cache/leo/research/quad_development_v1'/unit)
            result['status'] = 'admitted'
        print(json.dumps(result),flush=True)
        return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run,captures))
    after = verify_reader()
    result = dict(rows=results,reader_before=before,reader_after=after,
                  source_sha256={str(p):digest(p) for p in [Path(__file__),HERE/'export_orbit.py',GOAL/'admit_heldout_orbit.py']})
    path = directory/'summary.json'
    path.write_text(json.dumps(result,indent=2))
    path.with_suffix('.sha256').write_text(digest(path)+'\n')


if __name__ == '__main__':
    main()
