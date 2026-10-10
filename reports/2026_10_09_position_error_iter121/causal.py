"""Pure saved-position fusion; conditional stationarity, no truth/covariance."""

import numpy as np


def chart(latitude_longitude, origin):
    """Fixed first-fix equirectangular chart (km), longitude wrapped at origin."""
    values = np.asarray(latitude_longitude, dtype=float)
    origin = np.asarray(origin, dtype=float)
    d = values - origin
    d[..., 1] = (d[..., 1] + 180) % 360 - 180
    return np.stack(
        (
            6371.0088 * np.radians(d[..., 1]) * np.cos(np.radians(origin[0])),
            6371.0088 * np.radians(d[..., 0]),
        ),
        axis=-1,
    )


def unchart(xy, origin):
    origin = np.asarray(origin, dtype=float)
    xy = np.asarray(xy, dtype=float)
    return np.stack(
        (
            origin[0] + np.degrees(xy[..., 1] / 6371.0088),
            (origin[1] + np.degrees(xy[..., 0] / (6371.0088 * np.cos(np.radians(origin[0])))) + 180)
            % 360
            - 180,
        ),
        axis=-1,
    )


def fuse(rows):
    """Rows ordered by declared availability, resets supplied before inference.

    Each row: label, order_ns, reset_group, arms {fitted-c|zero-c: latlon|null}.
    Arm-specific first qualified fix initializes chart; no error-based rejection.
    Outages carry last state, explicitly marked held; standalone remains separate.
    """
    if len({x["label"] for x in rows}) != len(rows):
        raise ValueError("duplicate membership")
    if rows != sorted(rows, key=lambda x: (x["order_ns"], x["label"])):
        raise ValueError("chronological order required")
    states = {}
    output = []
    for row in rows:
        result = {
            "label": row["label"],
            "order_ns": row["order_ns"],
            "reset_group": row["reset_group"],
            "arms": {},
        }
        for arm in ("fitted-c", "zero-c"):
            state = states.setdefault(
                (row["reset_group"], arm), {"origin": None, "fixes": [], "last_ns": None}
            )
            fix = row["arms"][arm]
            if fix is not None:
                fix = np.asarray(fix, dtype=float)
                if (
                    fix.shape != (2,)
                    or not np.isfinite(fix).all()
                    or abs(fix[0]) >= 89
                    or abs(fix[1]) > 180
                ):
                    raise ValueError("finite nonpolar geographic fix required")
                if state["origin"] is None:
                    state["origin"] = fix.copy()
                state["fixes"].append(chart(fix, state["origin"]))
                state["last_ns"] = row["order_ns"]
            count = len(state["fixes"])
            result["arms"][arm] = {
                "standalone": None if fix is None else fix.tolist(),
                "mean": None
                if not count
                else unchart(np.mean(state["fixes"], axis=0), state["origin"]).tolist(),
                "median": None
                if not count
                else unchart(np.median(state["fixes"], axis=0), state["origin"]).tolist(),
                "fix_count": count,
                "held": fix is None and count > 0,
                "held_age_s": None if not count else (row["order_ns"] - state["last_ns"]) / 1e9,
            }
        output.append(result)
    return output
