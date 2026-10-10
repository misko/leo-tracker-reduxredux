"""Soft conditional mean/product diagnostics; no estimator of physical covariance."""

from collections import defaultdict

import numpy as np


def diagnostic(
    responsibilities, standardized_residuals, pair_details, window_ids, satellite_numbers
):
    """Group by frozen acquisition identity and candidate, preserving fractional mass.

    Pair weight for satellite k is R_ik R_jk. Opposite-block mean predictions
    never use the target block's residuals to estimate their means. All R and z
    still come from nuisance parameters fitted on the entire recording.
    """
    r, z = np.asarray(responsibilities, float), np.asarray(standardized_residuals, float)
    ids = list(window_ids)
    numbers = list(map(int, satellite_numbers))
    if (
        r.ndim != 2
        or z.shape != r.shape
        or r.shape != (len(ids), len(numbers))
        or len(set(ids)) != len(ids)
        or len(set(numbers)) != len(numbers)
        or not np.isfinite(r).all()
        or not np.isfinite(z).all()
        or np.any(r < 0)
        or np.any(r.sum(axis=1) > 1 + 1e-12)
    ):
        raise ValueError("invalid responsibilities, residuals or identities")
    lookup = {name: i for i, name in enumerate(ids)}
    grouped = defaultdict(list)
    used = set()
    for detail in pair_details:
        first, second = [lookup[detail[key]] for key in ("first_window_id", "second_window_id")]
        if first == second or first in used or second in used:
            raise ValueError("pair reuse")
        used.update((first, second))
        block = detail["alternating_block"]
        if block not in (0, 1):
            raise ValueError("invalid fixed block")
        grouped[tuple(detail["group"])].append((first, second, block))
    records = []
    for group, pairs in sorted(grouped.items()):
        for k, satellite in enumerate(numbers):
            blocks = []
            for block in (0, 1):
                rows = [(i, j) for i, j, b in pairs if b == block]
                i = np.asarray([p[0] for p in rows], int)
                j = np.asarray([p[1] for p in rows], int)
                w = r[i, k] * r[j, k]
                mass = float(w.sum())
                sx = float(np.sum(w * z[i, k]))
                sy = float(np.sum(w * z[j, k]))
                sxy = float(np.sum(w * z[i, k] * z[j, k]))
                blocks.append(
                    dict(
                        block=block,
                        pairs=len(rows),
                        mass=mass,
                        weighted_x_sum=sx,
                        weighted_y_sum=sy,
                        weighted_product_sum=sxy,
                        mean_x=sx / mass if mass else None,
                        mean_y=sy / mass if mass else None,
                        mean_product=sxy / mass if mass else None,
                    )
                )
            for block, target in enumerate(blocks):
                train = blocks[1 - block]
                if target["mass"] and train["mass"]:
                    x, y = train["mean_x"], train["mean_y"]
                    target["opposite_block_mean_product"] = x * y
                    target["opposite_block_centered_product_sum"] = (
                        target["weighted_product_sum"]
                        - x * target["weighted_y_sum"]
                        - y * target["weighted_x_sum"]
                        + x * y * target["mass"]
                    )
                    target["crossprediction_status"] = "available"
                else:
                    target["opposite_block_mean_product"] = None
                    target["opposite_block_centered_product_sum"] = None
                    target["crossprediction_status"] = "zero-training-or-target-mass"
            records.append(dict(group=list(group), satellite=satellite, blocks=blocks))
    all_blocks = [b for record in records for b in record["blocks"]]
    available = [b for b in all_blocks if b["crossprediction_status"] == "available"]
    return dict(
        pairs=len(pair_details),
        observations=len(ids),
        unpaired=len(ids) - len(used),
        group_satellite_records=records,
        shared_label_mass=sum(b["mass"] for b in all_blocks),
        weighted_product_sum=sum(b["weighted_product_sum"] for b in all_blocks),
        crossprediction_mass=sum(b["mass"] for b in available),
        crossprediction_raw_product_sum=sum(b["weighted_product_sum"] for b in available),
        crossprediction_centered_product_sum=sum(
            b["opposite_block_centered_product_sum"] for b in available
        ),
        excluded_crossprediction_mass=sum(
            b["mass"] for b in all_blocks if b["crossprediction_status"] != "available"
        ),
        interpretation="Descriptive decomposition, not unbiased covariance or significance",
    )
