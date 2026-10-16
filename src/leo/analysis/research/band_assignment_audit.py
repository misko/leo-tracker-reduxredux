"""Compare aligned posterior assignments without selection or optimization."""

import numpy as np


def compare_assignments(all_ids, all_probabilities, half_ids, half_probabilities):
    """Columns must share candidate order and include clutter as the last column."""
    a, b = np.asarray(all_probabilities, float), np.asarray(half_probabilities, float)
    for ids, values in ((all_ids, a), (half_ids, b)):
        if (values.ndim != 2 or len(ids) != len(values) or not len(ids)
                or len(set(ids)) != len(ids) or values.shape[1] < 2
                or not np.isfinite(values).all() or np.any(values < 0)
                or not np.allclose(values.sum(axis=1), 1, atol=1e-10, rtol=0)):
            raise ValueError("Unique windows and normalized finite posteriors required")
    if a.shape[1] != b.shape[1]:
        raise ValueError("Candidate columns differ")
    index = {identity: i for i, identity in enumerate(all_ids)}
    if any(identity not in index for identity in half_ids):
        raise ValueError("Half window missing from all-band evidence")
    a = a[[index[identity] for identity in half_ids]]
    tv = .5 * np.abs(a-b).sum(axis=1)
    winner_a, winner_b = a.argmax(axis=1), b.argmax(axis=1)
    changed = winner_a != winner_b
    confident = (a.max(axis=1) >= .9) & (b.max(axis=1) >= .9)
    signal = (winner_a != a.shape[1]-1) & (winner_b != a.shape[1]-1)
    return dict(
        windows=len(b), total_variation_mean=float(tv.mean()),
        total_variation_p90=float(np.quantile(tv, .9)),
        map_changed=int(changed.sum()),
        both_confident=int(confident.sum()),
        both_confident_changed=int((confident & changed).sum()),
        both_signal=int(signal.sum()),
        both_signal_satellite_changed=int((signal & changed).sum()),
        all_clutter_mass=float(a[:, -1].sum()),
        half_clutter_mass=float(b[:, -1].sum()),
        interpretation=("Conditional assignments at each own training-selected fit; "
                        "not identity truth"),
    )
