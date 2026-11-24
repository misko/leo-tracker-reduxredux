"""Opt-in exact reuse inside the pinned accepted lean proposal."""

from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from unittest.mock import patch

import numpy as np


FINISH_SHA = "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708"
SALVAGE_SHA = "7ccb39db8f2f4a278b2c7b1977866e3d731601de7d759adb5541e88692917f09"
SECOND_GATE = """    base, powers, means = build_at(scan, node, keep, point, reference, model)
    gates = conservative_recovery.retained_metrics(base, point)
    checked, rejected = drop_failing(keep, base.rows, base.slices, gates)
"""
REUSE_GATE = """    if not initial.all():
        base, powers, means = build_at(scan, node, keep, point, reference, model)
        gates = conservative_recovery.retained_metrics(base, point)
    else:
        audit["unchanged_seed_gates_reused"] += 1
    checked, rejected = drop_failing(keep, base.rows, base.slices, gates)
"""


def checked_source(module, pin):
    path = Path(module.__file__)
    if sha256(path.read_bytes()).hexdigest() != pin:
        raise ValueError(f"Expected the pinned proposal source at {path}")
    return path


class IntervalWhitening:
    """Retain at most the prefix and suffix of the current support length."""

    def __init__(self, audit):
        self.audit = audit
        self.length = None
        self.matrices = {}

    def inverse(self, noise, start, stop):
        length = stop - start
        if length != self.length:
            self.length = length
            self.matrices.clear()
        key = start, stop
        if key in self.matrices:
            self.audit["whitening_reuses"] += 1
        else:
            self.matrices[key] = np.diag(1 / noise[start:stop])
            self.audit["whitening_builds"] += 1
        return self.matrices[key]


@contextmanager
def binding(audit):
    """Install before the normal isolated-salvage binding captures its proposal."""
    import blind_joint_finish as finish
    import certified_salvage as salvage

    finish_path = checked_source(finish, FINISH_SHA)
    salvage_path = checked_source(salvage, SALVAGE_SHA)
    proposal = getsource(finish.propose)
    reader = getsource(salvage.read_alternative)
    white = "np.diag(1 / noise[a:b])"
    if proposal.count(SECOND_GATE) != 1 or reader.count(white) != 1:
        raise ValueError("Expected one original second gate and one fine whitening operand")
    reuse = compile(proposal.replace(SECOND_GATE, REUSE_GATE), str(finish_path), "exec")
    # Keep the proposal globals live. The original route installs its confidence,
    # isolated-gate and paired-finish ports after this outer binding.
    def propose(*args, **kwargs):
        namespace = dict(vars(finish), audit=audit)
        exec(reuse, namespace)
        return namespace["propose"](*args, **kwargs)

    ordinary_fine = salvage.fine_alternatives
    transformed = compile(reader.replace(white, "inverse(noise, a, b)"), str(salvage_path), "exec")

    def fine(*args, **kwargs):
        whitening = IntervalWhitening(audit)
        namespace = dict(vars(salvage), inverse=whitening.inverse)
        exec(transformed, namespace)
        with patch.object(salvage, "read_alternative", namespace["read_alternative"]):
            return ordinary_fine(*args, **kwargs)

    with (patch.object(finish, "propose", propose),
          patch.object(salvage, "fine_alternatives", fine)):
        yield
