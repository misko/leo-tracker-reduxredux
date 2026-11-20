"""Check predictability of still-unowned Doppler curvature before late recovery."""

import numpy as np

ARMS = ("c0", "fitted_c")
HELD_RATIO_LIMIT = 0.60


def evaluate(targets):
    """Use the frozen three-fragment limit and matched calibration arms."""
    if len(targets) > 3:
        raise ValueError("late routing requires at most three incumbent residual targets")
    decisions = []
    for target in targets:
        time = np.asarray(target["times_s"], dtype=float)
        corrected = target["corrected_hz"]
        if len(time) < 20 or set(corrected) != set(ARMS):
            raise ValueError("incomplete incumbent residual fragment")
        if not np.isfinite(time).all() or np.min(np.diff(time)) <= 0 or time[-1] - time[0] < 15:
            raise ValueError("invalid incumbent residual time axis")
        x = (time - time[0]) / (time[-1] - time[0]) - 0.5
        left, right = x < -0.25, x > 0.25
        train = ~(left | right)
        arms = {}
        if min(left.sum(), train.sum(), right.sum()) >= 4:
            design = np.column_stack((np.ones(len(x)), x, x * x))
            for arm in ARMS:
                y = np.asarray(corrected[arm], dtype=float)
                if y.shape != time.shape or not np.isfinite(y).all():
                    raise ValueError("invalid incumbent residual frequency")
                linear = np.linalg.lstsq(design[train, :2], y[train], rcond=None)[0]
                quadratic = np.linalg.lstsq(design[train], y[train], rcond=None)[0]
                line_rms = float(np.sqrt(np.mean((y[~train] - design[~train, :2] @ linear) ** 2)))
                quad_rms = float(np.sqrt(np.mean((y[~train] - design[~train] @ quadratic) ** 2)))
                arms[arm] = dict(
                    linear_rms_hz=line_rms,
                    quadratic_rms_hz=quad_rms,
                    held_ratio=quad_rms / line_rms if line_rms > 0 else None,
                    quadratic_hz=float(quadratic[2]),
                )
        qualified = bool(
            arms
            and all(
                a["linear_rms_hz"] > 0 and a["held_ratio"] <= HELD_RATIO_LIMIT
                for a in arms.values()
            )
            and arms["c0"]["quadratic_hz"] * arms["fitted_c"]["quadratic_hz"] > 0
        )
        decisions.append(
            dict(
                qualified=qualified,
                arms=arms,
                points=len(time),
                span_s=float(time[-1] - time[0]),
                training_points=int(train.sum()),
                held_left=int(left.sum()),
                held_right=int(right.sum()),
            )
        )
    return dict(run=any(d["qualified"] for d in decisions), targets=decisions)
