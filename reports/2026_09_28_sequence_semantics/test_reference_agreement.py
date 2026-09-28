import numpy as np
from reference_agreement import compare


def test_reference_comparison_excludes_nonbinary_and_missing_symbols():
    raw = np.array([1, -1, 1, -1, 1], complex)
    reference = np.array([1, 1, 1j, np.nan, 3], complex)
    assert compare(raw, reference) == dict(decisions=2, matches=1)
