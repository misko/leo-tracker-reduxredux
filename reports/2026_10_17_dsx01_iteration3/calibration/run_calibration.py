"""Short causal donor/no-donor bootstrap experiments, separate from final fitting."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
MODELS = HERE.parents[1] / '2026_10_16_dsx01_models'
sys.path.insert(0, str(MODELS))
import common
from donors import discover
from causal_calibration import bootstrap


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--discover', action='store_true')
    parser.add_argument('--sources', nargs='+', default=['S03'])
    parser.add_argument('--modes', nargs='+', default=['early_to_late'])
    parser.add_argument('--arms', nargs='+', default=['fitted-c', 'zero-c'])
    parser.add_argument('--policies', nargs='+', default=['donor', 'no-donor'])
    parser.add_argument('--max-evaluations', type=int, default=400)
    parser.add_argument('--seconds', type=float, default=60.)
    args = parser.parse_args()
    manifest_path = HERE / 'donor_manifest.json'
    if args.discover:
        from leo.storage.shared_fast_scan import SharedFastScanStore
        sources = json.loads((common.DATASET/'sources.json').read_text())
        manifest = discover(SharedFastScanStore('/srv/bulk/leo', 'shared-scan-q-v2'), sources)
        common.save_json(manifest_path, manifest)
        print(json.dumps(dict(stage='donor-discovery',
            sources=[dict(source_id=row['target']['source_id'], available=row['available'],
                job_id=row.get('donor', {}).get('job_id')) for row in manifest['sources']])), flush=True)
    manifest = json.loads(manifest_path.read_text())
    output = HERE / 'results'
    output.mkdir(exist_ok=True)
    for source_id in args.sources:
        original = common.load_context(source_id)
        donor = next(row for row in manifest['sources'] if row['target']['source_id'] == source_id)
        for mode in args.modes:
            for arm in args.arms:
                context = common.temporal_context(original, mode, fixed_c=arm == 'zero-c')
                for policy in args.policies:
                    name = f'{source_id}-{mode}-{arm}-{policy}'
                    path = output/(name+'.json')
                    if path.exists():
                        print(json.dumps(dict(task=name, status='existing')), flush=True)
                        continue
                    trained, diag = bootstrap(context, donor, use_donor=policy == 'donor',
                        max_evaluations=args.max_evaluations, max_seconds=args.seconds)
                    record = dict(task=name, source_id=source_id, mode=mode, arm=arm,
                        policy=policy, kind='calibration bootstrap only; no final method fitting',
                        donor_available=donor['available'], diagnostics=diag,
                        training=common.measure(trained, trained.vector, trained.nuisance,
                            mask=trained.train_mask),
                        held=common.measure(trained, trained.vector, trained.nuisance,
                            mask=~trained.train_mask),
                        vector=trained.vector, nuisance=trained.nuisance,
                        seed_band_offsets_hz=[row['band_delta_seed_hz'] for row in diag['seed']['receivers']],
                        qualification='Candidate-conditioned train/held split; configured reference distance is evaluation only; missing donor remains in denominator and uses declared paired-training fallback.')
                    common.save_json(path, record)
                    np.savez_compressed(path.with_suffix('.npz'), vector=trained.vector,
                        nuisance=trained.nuisance, offsets_hz=np.asarray(diag['learned_offsets_hz']))
                    print(json.dumps(dict(task=name, training=record['training']['associated'],
                        held=record['held']['associated'], held_total=record['held']['observations'],
                        stationarity=diag['fit'].get('stationarity'), accepted=diag['accepted'],
                        evaluations=diag['evaluations'], elapsed_seconds=diag['elapsed_seconds'],
                        offsets_hz=diag['learned_offsets_hz'], slopes_hz_s=diag['receiver_slopes_hz_s'])), flush=True)


if __name__ == '__main__':
    main()
