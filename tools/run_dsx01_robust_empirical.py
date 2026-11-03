"""Blind robust joint-nuisance fit with shared variance-component learning."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import run_dsx01_joint_marginal as runner
from associate_merged_track_catalogue import write
from dsx01_joint_marginal import JointMarginal
from dsx01_robust_joint import RobustJoint


class RobustEmpirical(RobustJoint):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant != "empirical":
            raise ValueError("empirical variance-component control required")
        JointMarginal.__init__(self, scan, seed, fitted_c, variant=variant, **kwargs)
        self.noise_groups = np.concatenate(
            [np.full(sl.stop - sl.start, k, dtype=int) for k, sl in enumerate(self.slices)]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    a = parser.parse_args()
    runner.OUTPUT = runner.OUTPUT / "robust_empirical"
    runner.JointMarginal = RobustEmpirical
    runner.run(a.case, variants=("empirical",))
    path = runner.OUTPUT / a.case / "protocol.json"
    protocol = json.loads(path.read_text())
    protocol.update(
        likelihood="variational Student Gaussian/Gamma bound, one precision per original curve",
        student_nu=4,
        variational_iterations=24,
        posterior_variance_in_precision_updates=True,
        no_observations_removed_or_relabelled=True,
        robust_source_sha256={
            str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), runner.ROOT / "tools/dsx01_robust_joint.py")
        },
    )
    write(path, protocol)
