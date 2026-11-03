"""Bounded nine-point cold calibration tests; held scores never select a fit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2]/'2026_10_16_dsx01_models'))
import common
from portfolio import fit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', nargs='+', default=['S03'])
    parser.add_argument('--modes', nargs='+', default=['early_to_late'])
    parser.add_argument('--arms', nargs='+', default=['fitted-c', 'zero-c'])
    parser.add_argument('--policies', nargs='+', default=['no-donor', 'donor'])
    parser.add_argument('--max-evaluations', type=int, default=1000)
    parser.add_argument('--seconds', type=float, default=120.)
    args = parser.parse_args()
    manifest_path = HERE.parent/'donor_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    output = HERE/'results'
    output.mkdir(exist_ok=True)
    for source_id in args.sources:
        original = common.load_context(source_id)
        receipt = next(row for row in manifest['sources'] if row['target']['source_id'] == source_id)
        for mode in args.modes:
            for arm in args.arms:
                context = common.temporal_context(original, mode, fixed_c=arm == 'zero-c')
                for policy in args.policies:
                    name = f'{source_id}-{mode}-{arm}-{policy}'
                    path = output/(name+'.json')
                    if path.exists():
                        print(json.dumps(dict(task=name, status='existing')), flush=True)
                        continue
                    trained, diag = fit(context, receipt, use_donor=policy == 'donor',
                        max_evaluations=args.max_evaluations, max_seconds=args.seconds)
                    record = dict(task=name, source_id=source_id, mode=mode, arm=arm,
                        policy=policy, kind='prior-grid free current band calibration; no final track method fit',
                        donor_available=receipt['available'], diagnostics=diag,
                        training=common.measure(trained, trained.vector, trained.nuisance,
                            mask=trained.train_mask),
                        held=common.measure(trained, trained.vector, trained.nuisance,
                            mask=~trained.train_mask), vector=trained.vector, nuisance=trained.nuisance,
                        donor_manifest_sha256='sha256:'+hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                        source_input_sha256=original.source['tracking_input_sha256'],
                        code_sha256={str(p.relative_to(HERE.parent)):'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in [HERE/'portfolio.py', HERE/'run_portfolio.py', HERE.parent/'causal_calibration.py']},
                        qualification='Candidate-conditioned temporal validation; no held CFO or evaluation position enters seed construction, selection or refinement. Configured reference distance is evaluated separately.')
                    common.save_json(path, record)
                    np.savez_compressed(path.with_suffix('.npz'), vector=trained.vector,
                        nuisance=trained.nuisance, offsets_hz=np.asarray(diag['learned_offsets_hz']))
                    print(json.dumps(dict(task=name, training=record['training']['associated'],
                        held=record['held']['associated'], held_total=record['held']['observations'],
                        stationarity=diag['endpoint'].get('stationarity'), accepted=diag['accepted'],
                        evaluations=diag['evaluations'], elapsed_seconds=diag['elapsed_seconds'],
                        offsets_hz=diag['learned_offsets_hz'], slopes_hz_s=diag['receiver_slopes_hz_s'],
                        selected_seed=diag['selected_seed_index'])), flush=True)


if __name__ == '__main__':
    main()
