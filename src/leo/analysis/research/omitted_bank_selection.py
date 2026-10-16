"""Normalized-weight tangent audit and deterministic common-bank selection.

Array ports only. No fit, data loading, satellite identity, significance test or
position accuracy claim. Numerical-zero eligibility is fixed at machine rank
scale; all original raw/projected scores remain unchanged in the audit.
"""

from dataclasses import dataclass

import numpy as np

from leo.analysis.regional_position_score import zero_sum_basis
from leo.analysis.research.omitted_bank_score import OmittedScoreProjection, project_omitted_scores

ARMS = ("fitted-c", "zero-c")


def included_weight_tangents(posterior):
    """K P B for full per-original-window satellite masses, never normalized P."""
    p = np.asarray(posterior, float)
    if (
        p.ndim != 2
        or not len(p)
        or p.shape[1] < 1
        or not np.isfinite(p).all()
        or np.any(p < 0)
        or np.any(p > 1)
        or np.any(p.sum(axis=1) > 1 + 8 * np.finfo(float).eps)
    ):
        raise ValueError("Finite per-window satellite posterior masses required")
    result = p.shape[1] * p @ zero_sum_basis(p.shape[1])
    result.setflags(write=False)
    return result


@dataclass(frozen=True)
class WeightProfileAudit:
    projection: OmittedScoreProjection
    numerical_zero: tuple[bool, ...]
    relative_zero_tolerance: float
    weight_columns: int


def project_with_weight_tangents(
    scores, geographic_scores, physical_nuisance_scores, posterior, *, active_nuisance_bounds=()
):
    weight = included_weight_tangents(posterior)
    nuisance = np.asarray(physical_nuisance_scores, float)
    if nuisance.ndim != 2 or len(nuisance) != len(weight):
        raise ValueError("Aligned physical and normalized-weight score rows required")
    result = project_omitted_scores(
        scores,
        geographic_scores,
        np.column_stack([nuisance, weight]),
        active_nuisance_bounds=active_nuisance_bounds,
    )
    columns = 2 + nuisance.shape[1] + weight.shape[1]
    tolerance = max(
        result.all_parameter_space.rank_tolerance, max(len(weight), columns) * np.finfo(float).eps
    )
    # This is a numerical-rank convention, not a general SVD error bound.
    # Exact-span roundoff must not qualify a duplicate by strictly positive
    # receiver/block sums. Do not clip or rewrite the reported residual arrays.
    zero = tuple(
        fraction is None or fraction <= tolerance for fraction in result.projected_norm_fraction
    )
    return WeightProfileAudit(result, zero, float(tolerance), weight.shape[1])


def select_common_pool(
    numbers,
    projected_by_arm,
    receiver,
    training_blocks,
    numerical_zero_by_arm,
    *,
    coverage_complete,
    maximum=4,
):
    """Strict common eligibility, worst-arm block-removed rank; no fallback."""
    numbers, rx, blocks = map(np.asarray, (numbers, receiver, training_blocks))
    if (
        not coverage_complete
        or set(projected_by_arm) != set(ARMS)
        or set(numerical_zero_by_arm) != set(ARMS)
        or numbers.ndim != 1
        or numbers.dtype.kind not in "iu"
        or np.any(numbers <= 0)
        or len(np.unique(numbers)) != len(numbers)
        or rx.ndim != 1
        or not len(rx)
        or blocks.shape != rx.shape
        or rx.dtype.kind not in "iu"
        or blocks.dtype.kind not in "iu"
        or not set(rx) <= {0, 1}
        or np.any(blocks < 0)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or not 1 <= maximum <= 4
    ):
        raise ValueError("Complete fixed two-arm catalogue/receiver/block inventory required")
    matrices, zero = {}, {}
    for arm in ARMS:
        matrices[arm] = np.asarray(projected_by_arm[arm], float)
        zero[arm] = np.asarray(numerical_zero_by_arm[arm])
        if (
            matrices[arm].shape != (len(rx), len(numbers))
            or not np.isfinite(matrices[arm]).all()
            or zero[arm].shape != numbers.shape
            or zero[arm].dtype != bool
        ):
            raise ValueError("Aligned complete projected scores and numerical-zero flags required")
    grouped = {}
    for arm in ARMS:
        matrix = matrices[arm]
        grouped[arm] = dict(
            projected_sum=matrix.sum(axis=0),
            groups=dict(
                receiver=[dict(group=r, projected_sum=matrix[rx == r].sum(axis=0)) for r in (0, 1)],
                training_block=[
                    dict(group=int(b), projected_sum=matrix[blocks == b].sum(axis=0))
                    for b in np.unique(blocks)
                ],
            ),
        )
    return select_common_grouped_pool(
        numbers, grouped, zero, coverage_complete=True, maximum=maximum
    )


def select_common_grouped_pool(
    numbers, grouped_by_arm, numerical_zero_by_arm, *, coverage_complete, maximum=4
):
    """Same selector on sealed group arrays, enabling receipt validation without replay."""
    numbers = np.asarray(numbers)
    if (
        not coverage_complete
        or numbers.ndim != 1
        or numbers.dtype.kind not in "iu"
        or np.any(numbers <= 0)
        or len(np.unique(numbers)) != len(numbers)
        or set(grouped_by_arm) != set(ARMS)
        or set(numerical_zero_by_arm) != set(ARMS)
        or not isinstance(maximum, int)
        or isinstance(maximum, bool)
        or not 1 <= maximum <= 4
    ):
        raise ValueError("Complete fixed common group inventory required")
    parsed = {}
    for arm in ARMS:
        row = grouped_by_arm[arm]
        total = np.asarray(row["projected_sum"], float)
        rx = row["groups"]["receiver"]
        blocks = row["groups"]["training_block"]
        if (
            sorted(g["group"] for g in rx) != [0, 1]
            or not blocks
            or len({g["group"] for g in blocks}) != len(blocks)
        ):
            raise ValueError("Both receiver groups and unique original blocks required")
        values = [total, *(np.asarray(g["projected_sum"], float) for g in rx + blocks)]
        zero = np.asarray(numerical_zero_by_arm[arm])
        if (
            any(x.shape != numbers.shape or not np.isfinite(x).all() for x in values)
            or zero.shape != numbers.shape
            or zero.dtype != bool
        ):
            raise ValueError("Aligned finite complete group scores required")
        for groups in (rx, blocks):
            summed = np.sum([g["projected_sum"] for g in groups], axis=0)
            if not np.allclose(summed, total, rtol=1e-11, atol=1e-9):
                raise ValueError("Receiver/block sums differ from complete projected total")
        parsed[arm] = total, sorted(rx, key=lambda g: g["group"]), blocks, zero
    rows = []
    for i, number in enumerate(numbers):
        arms, eligible = {}, True
        for arm in ARMS:
            total_score, receivers, blocks, zero = parsed[arm]
            totals = [float(g["projected_sum"][i]) for g in receivers]
            block_sums = [(int(g["group"]), float(g["projected_sum"][i])) for g in blocks]
            largest = max(block_sums, key=lambda row: (row[1], -row[0]))
            total = float(total_score[i])
            removed = total - largest[1]
            ok = not zero[i] and min(totals) > 0 and removed > 0
            arms[arm] = dict(
                eligible=bool(ok),
                numerical_zero=bool(zero[i]),
                receiver_projected_sums=totals,
                projected_sum=total,
                largest_block=largest[0],
                largest_block_sum=largest[1],
                block_removed_score=removed,
            )
            eligible &= bool(ok)
        rows.append(
            dict(
                number=int(number),
                eligible=eligible,
                arms=arms,
                min_block_removed_score=min(arms[a]["block_removed_score"] for a in ARMS),
            )
        )
    ranking = sorted(
        (r for r in rows if r["eligible"]),
        key=lambda r: (-r["min_block_removed_score"], r["number"]),
    )
    selected = sorted(r["number"] for r in ranking[:maximum])
    return dict(
        state="selected" if selected else "unavailable",
        added_numbers=selected,
        eligible_count=len(ranking),
        selected_ranking=[r["number"] for r in ranking[:maximum]],
        candidate_rank_rows=ranking,
        candidate_audit=rows,
        coverage_complete=True,
    )
