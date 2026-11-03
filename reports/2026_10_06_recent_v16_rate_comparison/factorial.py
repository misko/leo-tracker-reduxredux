"""Frozen eight-way recent-scan experiment, plus matched final RF ablation.

Refinement changes frequencies AND which candidate wins a window; calibration
and greedy+replacement rerun per measurement branch. Models/cones only change
the final score, not association membership. No newly collected RF or folds.
"""
import argparse
import json
from pathlib import Path
import sys

import process_stage as stage

SOURCE=stage.WORK
OUT=SOURCE/'factorial-v1'
REPORT=stage.HERE/'factorial-v1'
REFINEMENTS=('original','refined')
MODELS={'T1AT':'C0','V16':'V16'}
CONES=('off','on')
CONFIGURE=stage.configure


def cases():
    return [(r,m,c) for r in REFINEMENTS for m in MODELS for c in CONES]


def protocol():
    return dict(version=1,cohort_sha256=stage.sha(stage.COHORT),scans=16,
        position_cases_per_scan=16,refinements=REFINEMENTS,models=MODELS,cones=CONES,
        rf_arms=stage.ARMS,radius_km=4.,maximum_budgets_s=stage.POSITION_BUDGET,
        fit_scope='Independent scans, full data, no folds; roof-conditioned upstream calibration; exploratory localization.',
        baseline='T1AT association engine shared by both; T1AT position score = original Gaussian C0; full-data calibration for both, not a five-fold historical replay.',
        refinement='Original frequencies/margins and top-one versus orbit-blind refined frequencies/margins and top-one. Recalibrate and rerun greedy+replacement separately.',
        cone='Frozen earlier 20-scan cone; shared shape, receiver-specific roll. Position-only mass-preserving detection-prior tilt; strength 0.5, floor 0.1, neutral unsupported sky; unchanged hard horizon.',
        selection='Fitted-c associations and fixed receiver baseline frozen per refinement branch for all models/cones/final RF arms.',
        endpoint='Best-found horizontal distance to known roof; also report convergence, boundary, assignment coverage, final signal support, frequency RMS. No raw NLL comparisons across specifications.',
        dependencies={str(p):stage.sha(p) for p in [Path(__file__),stage.HERE/'original_candidates.py',
            stage.HERE/'factorial_objective.py',stage.HERE/'process_stage.py',stage.BASE/'position_score_sweep.py',
            stage.ROOT/'reports/2026_10_05_receiver_cones/summary.json',
            stage.ROOT/'reports/2026_10_05_receiver_cones/sky-maps.npz',
            stage.ROOT/'reports/2026_10_05_cone_prior_localization/cone_geometry.py',
            stage.ROOT/'reports/2026_10_05_cone_prior_localization/cone_objective.py']})


def freeze():
    record=protocol();path=REPORT/'protocol.json'
    # JSON normalizes tuples before equality comparison.
    record=json.loads(json.dumps(record))
    if path.exists():
        if json.loads(path.read_text())!=record: raise ValueError('Factorial protocol changed; use a new experiment version')
    else: stage.save(path,record)
    return record


def configure(refinement):
    if refinement not in REFINEMENTS: raise ValueError('Unknown refinement branch')
    root=SOURCE if refinement=='refined' else OUT/'original'
    stage.WORK=root
    cal=CONFIGURE()
    if refinement=='original':
        import original_candidates
        cal.load=original_candidates.load
    stage.configure=lambda:cal
    return root,cal


def prepare_original(label):
    root,cal=configure('original')
    folder=root/'inputs'/label;folder.mkdir(parents=True,exist_ok=True)
    for name in ('observations.json','orbit-bank'):
        source=SOURCE/'inputs'/label/name;dest=folder/name
        if not source.exists(): raise FileNotFoundError(f'Original GLRT export/bank pending: {source}')
        if dest.exists():
            if dest.resolve()!=source.resolve(): raise ValueError('Original branch input link mismatch')
        else: dest.symlink_to(source.resolve(),target_is_directory=source.is_dir())
    import original_candidates as original
    import bootstrap_tracks
    bootstrap_tracks.load=original.load;bootstrap_tracks.reconstruct=original.reconstruct
    if not (folder/'bootstrap.json').exists(): bootstrap_tracks.run(folder)
    original.seed(folder)
    cal.calibrate(label)
    cal.associate(label)


def position(label,refinement,model,cone):
    receipt=freeze()
    root,cal=configure(refinement)
    if not (root/'fits'/label/'associations/fitted-c.json').exists():
        raise FileNotFoundError(f'{label} {refinement}: association not complete')
    factory=None
    if cone=='on':
        from factorial_objective import Objective
        factory=Objective
    elif cone!='off': raise ValueError('Unknown cone toggle')
    stage.position(label,model=model,spec_key=MODELS[model],objective_factory=factory,
        destination=OUT/'positions'/label/refinement/model/cone,
        experiment=dict(protocol_sha256=stage.sha(REPORT/'protocol.json'),
                        refinement=refinement,cone=cone,model=model))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('freeze','original','position'))
    p.add_argument('--label')
    p.add_argument('--refinement',choices=REFINEMENTS)
    p.add_argument('--model',choices=MODELS)
    p.add_argument('--cone',choices=CONES)
    a=p.parse_args()
    labels={r['label'] for r in json.loads(stage.COHORT.read_text())['scans']}
    if a.action!='freeze' and a.label not in labels: raise ValueError('Unknown scan')
    if a.action=='freeze': freeze()
    elif a.action=='original': freeze();prepare_original(a.label)
    else: position(a.label,a.refinement,a.model,a.cone)
