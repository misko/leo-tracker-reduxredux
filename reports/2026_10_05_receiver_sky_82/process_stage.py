"""One bounded extension stage; only research outputs, capture stores read-only."""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent/'2026_10_04_ds13_18_scan_benchmark'
BASELINE = HERE.parent/'2026_10_04_t1_at_v1_replication'
COHORT = HERE/'cohort.json'
WORK = Path('/srv/bulk/leo/receiver-sky-82-20261005')
sys.path[:0] = [str(BASELINE), str(BENCH)]


def run(stage, label):
    cohort = json.loads(COHORT.read_text())
    if label not in cohort['new_labels']:
        raise ValueError('only frozen new scans may be processed here')
    scan = next(r for r in cohort['scans'] if r['label'] == label)
    directory = WORK/'inputs'/label
    directory.mkdir(parents=True, exist_ok=True)
    if stage == 'export':
        from export_observations import export
        from cohort import digest
        result = export(scan, directory/'observations.json', digest(COHORT.read_bytes()))
    elif stage == 'bank':
        from orbit_bank import build
        value = build(directory/'observations.json')
        result = {k: value[k] for k in ('status', 'retained_count', 'elapsed_s')}
    elif stage == 'refine':
        from cached_refinement import main
        main(directory/'observations.json')
        result = json.loads((directory/'refinement/progress.json').read_text())
        result.pop('signature', None)
    elif stage == 'bootstrap':
        from bootstrap_tracks import run as bootstrap
        if not (directory/'bootstrap.json').exists():
            bootstrap(directory)
        result = {'status': 'bootstrap_saved'}
    elif stage == 'seed':
        from seed_timing_variant import run as seed
        seed(directory)
        result = {'status': 'timing_initializer_saved'}
    elif stage == 'calibrate':
        from calibration import run as calibrate
        calibrate(directory/'seed-timing-v6')
        from discovery import FoldCalibration
        FoldCalibration(directory/'seed-timing-v6')  # Fail closed on convergence.
        result = {'status': 'all_five_calibration_folds_accepted'}
    elif stage == 'associate':
        from run import run as associate
        output = WORK/'associations'/label
        if not (output/'summary.json').exists():
            if output.exists():
                raise ValueError('partial association directory requires explicit continuation; do not overwrite')
            associate(directory/'seed-timing-v6', label, output)
        result = json.loads((output/'summary.json').read_text())
    elif stage == 'pair':
        import subset_positions
        from export_receiver_sky_probes import run as probes
        from collect_receiver_sky import run as collect
        from numeric_data import enable_research_model
        from cohort import digest
        subset_positions.INPUTS = WORK/'inputs'
        subset_positions.ROOT = WORK/'profile-inputs'
        subset_positions.ASSOCIATIONS = WORK/'associations'
        subset_positions.prepare(label)  # Frozen arrays only; no position fit.
        enable_research_model()
        probe_path = WORK/'probes'/f'{label}.json'
        probe_path.parent.mkdir(exist_ok=True)
        if not probe_path.exists():
            value = probes(label, COHORT)
            value['exporter_sha256'] = digest((BASELINE/'export_receiver_sky_probes.py').read_bytes())
            probe_path.write_text(json.dumps(value))
        target = WORK/'paired'/f'{label}.json'
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            value = collect(label, probe_path, input_root=WORK/'profile-inputs',
                            raw_root=WORK/'inputs', cohort_path=COHORT)
            value['collector_sha256'] = digest((BASELINE/'collect_receiver_sky.py').read_bytes())
            value['cohort_sha256'] = digest(COHORT.read_bytes())
            target.write_text(json.dumps(value, allow_nan=False))
        result = json.loads(target.read_text())['counts']
    else:
        raise ValueError('unknown stage')
    print('STAGE_RESULT', json.dumps(dict(scan=label, stage=stage, result=result)), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=('export','bank','refine','bootstrap','seed','calibrate','associate','pair'))
    p.add_argument('label')
    a = p.parse_args()
    run(a.stage, a.label)
