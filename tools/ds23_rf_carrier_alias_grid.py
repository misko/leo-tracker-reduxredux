"""Training-only continuous RF search over adjacent pilot CFO branches."""

from itertools import product
import numpy as np

from ds23_joint_component_rf import JointComponentWorkspace
from inventory_ds23_paired_component_cycles import PERIOD


class AliasBranchWorkspace(JointComponentWorkspace):
    def joint_fit(self, seeds, *, iterations=24):
        trials = []
        for aliases in product([-1, 0, 1], repeat=2):
            shifted = [dict(seed, CFO_hz=seed['CFO_hz']+alias*PERIOD)
                for seed, alias in zip(seeds, aliases, strict=True)]
            result = super().joint_fit(shifted, iterations=iterations)
            trials.append(dict(pilot_aliases=aliases, fit=result))
        selected = max(trials, key=lambda r:r['fit']['score'])
        return dict(selected['fit'], selected_pilot_aliases=selected['pilot_aliases'],
            branch_scores=[dict(pilot_aliases=r['pilot_aliases'], training_score=r['fit']['score'],
                parameters=r['fit']['parameters'], boundary=r['fit']['boundary']) for r in trials],
            branch_selection_uses_training_IQ_only=True,
            local_iterations_per_branch=iterations, trained_branches=len(trials))
