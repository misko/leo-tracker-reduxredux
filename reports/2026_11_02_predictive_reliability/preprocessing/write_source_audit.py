"""Bind the inspected dependency sources; this script never loads scan data."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCES = (
    'tools/evaluate_ds23_phase_refreshed.py',
    'tools/ds23_radio_noise.py',
    'tools/dsx01_window_noise.py',
    'tools/evaluate_ds23_family_weighting.py',
    'tools/algo02_scan.py',
    'tools/iterate_dsx01_position_nominations.py',
    'tools/prototype_dsx01_continuous_position.py',
    'tools/dsx01_joint_marginal.py',
    'tools/investigate_algo01_ds23_0217.py',
    'tools/investigate_ds23_adaptive_failures.py',
    'tools/probe_ds23_causal_phase_mean.py',
    'tools/probe_ds23_history_calibrated_phase.py',
    'tools/probe_ds23_receiver_smooth_prior.py',
    'tools/build_dsx01_orbit_modes.py',
    'tools/dsx01_hierarchical_bound.py',
    'tools/ds23_frequency_events.py',
    'tools/algo07_science/engine.py',
    'src/leo/analysis/research/retained_track_likelihood.py',
    'reports/2026_11_02_family_reliability/family/prototype.py',
    'reports/2026_11_02_family_reliability/solver/solver.py',
    'reports/2026_11_02_family_reliability/predictive/predictive.py',
    'reports/2026_11_02_predictive_reliability/preprocessing/adapter.py',
    'reports/2026_11_02_predictive_reliability/preprocessing/test_adapter.py',
    'reports/2026_11_02_predictive_reliability/preprocessing/README.md',
    'reports/2026_11_02_predictive_reliability/preprocessing/write_source_audit.py',
)


def main():
    bindings = []
    for name in SOURCES:
        data = (REPO / name).read_bytes()
        bindings.append(dict(path=name, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data)))
    result = dict(
        repository_revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO,
                                                     text=True).strip(),
        inspected_sources=bindings,
        primary_preprocessing='fixed150_unit',
        primary_choice='existing engineering default, not chosen from held RF or GPS outcomes',
        initial_position_km=[0, 0], initial_phase_reference='zero vector',
        phase_prior_means='unchanged causal TLE-history forecast',
        train_only_updates=['coefficient posterior', 'fragment Gamma noise posterior',
                            'optional declared Student phase-prior latent precision'],
        not_retrained=['graph/peak discovery', 'curvature', 'joins', 'native mask eligibility',
                       'fixed identities', 'alias branches', 'family nomination', 'nominal mode support'],
        adapter_tests=dict(passed=5, test_file='preprocessing/test_adapter.py',
                           scientific_fits=False),
        inference_GPS=False, blind_cross_validation=False)
    (HERE / 'source_audit.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
