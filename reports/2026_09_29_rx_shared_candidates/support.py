"""Same-snapshot candidate agreement; not verified physical identity."""

import numpy as np


def compare(left, right):
    if left["snapshot"] != right["snapshot"] or left["catalogue_size"] != right["catalogue_size"]:
        raise ValueError("Candidate namespaces differ")
    arrays = []
    for item in (left, right):
        ids, weights = np.asarray(item["ids"]), np.asarray(item["weights"], float)
        if (
            ids.ndim != 1
            or not np.issubdtype(ids.dtype, np.integer)
            or len(ids) == 0
            or len(set(ids.tolist())) != len(ids)
            or np.any(ids < 0)
            or np.any(ids >= item["catalogue_size"])
            or weights.shape != ids.shape
            or not np.isfinite(weights).all()
            or np.any(weights < 0)
            or abs(weights.sum() - 1) > 1e-9
        ):
            raise ValueError("Invalid candidate IDs or normalized weights")
        arrays.append((ids, weights))
    (a, p), (b, q) = arrays
    common, i, j = np.intersect1d(a, b, return_indices=True)
    product = p[i] * q[j]
    # MAP ties use smallest catalogue row, independent of storage ordering.
    map_a = int(np.min(a[p == p.max()]))
    map_b = int(np.min(b[q == q.max()]))
    return {
        "left_candidates": len(a),
        "right_candidates": len(b),
        "common_ids": common.tolist(),
        "intersection": len(common),
        "left_common_mass": float(p[i].sum()),
        "right_common_mass": float(q[j].sum()),
        "agreement_mass": float(product.sum()),
        "map_equal": map_a == map_b,
        "left_map": map_a,
        "right_map": map_b,
        "positive_product_rows": int((product > 0).sum()),
    }
