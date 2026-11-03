"""One common timing offset with scan-specific drifts and satellite epochs."""
from collections.abc import Sequence
import numpy as np
from leo.analysis.localization_windows import independent_scan_columns


def common_clock_layout(candidate_counts: Sequence[int]) -> tuple[tuple[np.ndarray,...],np.ndarray]:
    # Reuse catalogue-size validation, not its independent-clock indexing.
    independent_scan_columns(candidate_counts)
    dimension=3+sum(2+n for n in candidate_counts)
    precision=np.r_[0.,0.,1.,np.full(dimension-3,4.)]
    columns=[];start=3
    for count in candidate_counts:
        indices=np.r_[0,1,2,np.arange(start,start+2+count)]
        indices.setflags(write=False);columns.append(indices)
        start+=2+count
    precision.setflags(write=False)
    return tuple(columns),precision
