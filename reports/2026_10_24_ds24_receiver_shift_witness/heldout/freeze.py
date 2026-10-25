"""Generate the pre-fit protocol, module hashes and observation-ID partition."""
import json
import sys
from pathlib import Path
import numpy as np
import scipy
from heldout import HERE, CASES, MODELS, ARMS, SEED, SCALES, fold_assignment, training_data, build, causal_reference
from matched_controls import load_baseline, digest, measurement_binding, write, canonical
import hashlib


def freeze():
    inputs = {}
    for case in CASES:
        d = load_baseline(case)
        p = build(d, 'c0', np.zeros(len(d['means'])), 'baseline')
        groups = fold_assignment(d)
        folds = []
        for index, held in enumerate(groups):
            curved_train, curved_held = [], []
            for row, i, sl in zip(p.rows, p.members, p.slices, strict=True):
                ids = np.asarray(p.scan.tracks[i]['observation_ids'])[d['keep'][sl]].tolist()
                (curved_held if row['candidate_index'] in held else curved_train).extend(ids)
            predictive_train, predictive_held = [], []
            for e in d['entries']:
                (predictive_held if e['candidate_index'] in held else predictive_train).extend(e['observation_ids'])
            train_ids = curved_train+predictive_train;held_ids = curved_held+predictive_held
            assert not (set(train_ids)&set(held_ids))
            assert len(set(train_ids+held_ids)) == len(train_ids+held_ids)
            folds.append(dict(fold=index, held_families=held,
                curved_training_ids=curved_train, curved_held_ids=curved_held,
                predictive_training_ids=predictive_train, predictive_held_ids=predictive_held,
                training_ids_sha256=hashlib.sha256(canonical(train_ids)).hexdigest(),
                held_ids_sha256=hashlib.sha256(canonical(held_ids)).hexdigest()))
        inputs[case] = dict(baseline_path=d['baseline_path'], baseline_sha256=d['baseline_sha256'],
            measurement_binding_sha256=measurement_binding(d), receipt=d['scan'].receipt,
            native_curved_noise_sha256=hashlib.sha256(canonical(p.point_noise)).hexdigest(),
            inherited_full_RF_fixed_noise=d['scan'].fixed_window_noise, folds=folds)
    write(HERE/'input_manifest.json', inputs)
    previous = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
    files = {HERE/'heldout.py', HERE/'test_heldout.py', HERE/'freeze.py', previous/'receiver/selection.json',
             previous/'receiver/protocol.json', previous/'receiver/adapter.py'}
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path:
            path = Path(path).resolve()
            if path.suffix == '.py' and (str(path).startswith('/home/mouse9911/gits/leo-tracker-reduxredux/tools/')
                    or str(path).startswith('/home/mouse9911/gits/leo-tracker-reduxredux/src/')
                    or str(path).startswith(str(previous))):
                files.add(path)
    dependencies = [dict(path=str(p), sha256=digest(p)) for p in sorted(files)]
    protocol = dict(schema_version=1, cases=CASES, models=MODELS, arms=ARMS,
        seed=SEED, case_seed='seed+numeric case suffix', folds=3,
        expected_position_fits=24, expected_crossover_vectors=48,
        randomization='Disjoint random whole-family three-fold partition across both RX/all channels and all factors',
        phase_rounds=5, position_steps=48, start_east_north_km=[0.,0.], box_km=[25.,25.],
        workers=2, blas_threads=1, case_fold_seconds_cap=240,
        score='Full joint unprojected held CFO Gaussian moment predictive density; quadratic and logdet retained',
        primary_sigma_multiplier=float(np.sqrt(2.)), sigma_sensitivity_multipliers=SCALES,
        noise_scale='Immutable original per-ID sigma, conditional inherited full-RF preprocessing; no target Gamma fit',
        target_prior='Causal phase mean only for geometry; unit-variance moment match to original nu=3 Student phase; unchanged Gaussian orbit and300Hz fragment priors',
        posterior='Full training curved-only nuisance covariance conditional on variational Gamma precisions and original powers; predictive training factors influence position only',
        crossover='Each train-only endpoint scored under each predictor after symmetric five fixed-position train-only phase refresh rounds',
        excluded_uncertainty='Train-only position is a plug-in point; its search/posterior uncertainty is not integrated',
        caveats=['Inherited full-RF graph, labels, aliases, masks, powers, physical-mode support and per-ID noise remain conditioning inputs',
                 'Target Student/Gamma tails approximated by covariance moments; score is not exact original model density',
                 'Linear orbit and phase geometry at causal target prior mean does not integrate nonlinear phase geometry',
                 'Two scans chosen from opposite posthoc geographic effects; no geographic reference in new fits/scoring/selection',
                 'Held-family marginal densities are nonadditive descriptive diagnostics'],
        GPS_used=False, new_RF=False, promotion_or_tuned_gate=False,
        source_sha256=digest(HERE/'heldout.py'), input_manifest_sha256=digest(HERE/'input_manifest.json'),
        dependencies=dependencies, environment=dict(python=sys.version, numpy=np.__version__, scipy=scipy.__version__))
    write(HERE/'protocol.json', protocol)
    print('sealed', len(dependencies), 'dependencies;24fits/48crossover vectors', flush=True)


if __name__ == '__main__':
    freeze()
