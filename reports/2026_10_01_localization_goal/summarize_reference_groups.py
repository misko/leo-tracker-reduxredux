"""Offline reference diagnostic; no estimator selection or new fits."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent
audit_path = HERE/'fixed-reference-nuisance-v1-audit.json'
assert digest(audit_path) == audit_path.with_suffix('.sha256').read_text().strip()
audit = json.loads(audit_path.read_text())
assert audit['valid'] == audit['planned'] == 6
assert audit['auditor_sha256'] == digest(HERE/'audit_fixed_reference_nuisance.py')
freeze = HERE/'fixed-reference-nuisance-v1/sources.json'
assert digest(freeze) == audit['freeze_sha256']
verify_sources(json.loads(freeze.read_text())['source_sha256'])
sources = {str(audit_path): digest(audit_path), str(__file__): digest(__file__)}
rows = []
fig, axes = plt.subplots(1, 3, figsize=(15, 6), layout='constrained')
for ax, comparison in zip(axes, audit['comparisons'], strict=True):
    unit = comparison['unit']
    path = HERE/'group-influence-v1'/f'{unit}.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    influence = json.loads(path.read_text())
    launch = json.loads(path.with_suffix('.launch.json').read_text())
    assert launch['returncode'] == 0 and launch['within_budget']
    assert launch['receipt_sha256'] == digest(path)
    sources[str(path)] = digest(path)
    control_path = HERE/'fixed-reference-nuisance-v1'/f'{unit}-control.json'
    assert digest(control_path) == control_path.with_suffix('.sha256').read_text().strip()
    control = json.loads(control_path.read_text())
    assert influence['parent_sha256'] == control['parent_sha256']
    groups = {g['identity']: g for g in comparison['groups'] if g['identity'] != 'clutter'}
    ordered = sorted(influence['groups'], key=lambda g: -g['position_step_m'])
    assert set(groups) == {g['norad_id'] for g in ordered}
    joined = []
    for rank, group in enumerate(ordered, 1):
        ref = groups[group['norad_id']]
        assert ref['tracks'] == group['track_indices']
        joined.append(dict(identity=group['norad_id'], influence_rank=rank,
                           predicted_deletion_shift_m=group['position_step_m'], **{
                               k: ref[k] for k in ['observation_gap', 'epoch_prior_gap', 'total_gap']}))
    top_reference = {g['identity'] for g in comparison['largest_positive_groups']}
    top_influence = {g['identity'] for g in joined[:3]}
    rows.append(dict(unit=unit, objective_gap=comparison['objective_gap'],
        observation_gap=sum(g['observation_gap'] for g in comparison['groups']),
        epoch_prior_gap=sum(g['epoch_prior_gap'] for g in comparison['groups']),
        shared_prior_gap=comparison['shared_prior_gap'],
        top3_overlap=len(top_reference & top_influence),
        top3_influence=joined[:3],
        reference_top3_influence_ranks=[g['influence_rank'] for g in joined if g['identity'] in top_reference],
        groups=joined))
    ordered_ref = sorted(groups.values(), key=lambda g: g['total_gap'])
    y = np.arange(len(ordered_ref))
    ax.barh(y-.18, [g['observation_gap'] for g in ordered_ref], .35, label='Observation score')
    ax.barh(y+.18, [g['epoch_prior_gap'] for g in ordered_ref], .35, label='Satellite timing prior')
    ax.set_yticks(y, [g['identity']+(' *' if g['identity'] in top_influence else '') for g in ordered_ref])
    ax.axvline(0, color='black', lw=.8)
    ax.set_title(f'{unit}: total gap {comparison["objective_gap"]:.2f}')
    ax.set_xlabel('Reference minus fitted location: objective contribution')
axes[0].set_ylabel('Inferred NORAD identity; * top-three deletion influence')
axes[0].legend(fontsize=8)
fig.suptitle('Fixed-location nuisance refits: observation versus timing-prior disagreement\n'
             'Positive values favor the fitted location; reference-informed diagnostic, not accuracy improvement')
plot = HERE/'fixed-reference-groups-v1.png'
assert not plot.exists()
fig.savefig(plot, dpi=160)
result = dict(rows=rows, source_sha256=sources,
    qualification='Three exposed development scans only. Influence ranks were computed without reference '
    'positions; their comparison with reference gaps is retrospective. Neither statistic labels a group '
    'as faulty. One locally stationary nuisance fit per position and unchanged hard identities. '
    'No estimator, new localization accuracy, calibrated uncertainty, or independent validation.')
output = HERE/'fixed-reference-groups-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps([{k: v for k, v in row.items() if k != 'groups'} for row in rows], indent=2))
