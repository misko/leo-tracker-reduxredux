"""Reference-free rough position and satellite hypotheses from whole-track shapes."""

import time

import numpy as np

ALIAS_HZ = 1 / 4.4e-6
SCALE_HZ = 200.0
CAP_HZ = 2000.0


def loss(errors):
    return 2 * SCALE_HZ**2 * (np.sqrt(1 + (np.asarray(errors) / SCALE_HZ) ** 2) - 1)


def robust_locations(values):
    locations = np.median(values, axis=0)
    for _iteration in range(20):
        errors = values - locations
        weights = 1 / np.sqrt(1 + (errors / SCALE_HZ) ** 2)
        updated = np.sum(weights * values, axis=0) / np.sum(weights, axis=0)
        change = np.max(np.abs(updated - locations))
        locations = updated
        if change < 0.01:
            break
    return locations


class TrackObjective:
    def __init__(self, data):
        self.data = data
        self.blocks = []
        owned_groups = set()
        for index, track in enumerate(data.tracks):
            rows = []
            for row in np.asarray(track["rows"], dtype=int):
                group = int(data.group[row])
                if group not in owned_groups:
                    rows.append(int(row))
                    owned_groups.add(group)
            if len(rows) < 2:
                continue
            rows = np.asarray(rows)
            rows = rows[np.lexsort((rows, data.times[rows]))]
            candidates = np.asarray(track["candidate_indices"], dtype=int)
            if (
                not len(candidates)
                or np.any(candidates < 0)
                or np.any(candidates >= len(data.numbers))
            ):
                raise ValueError("Track has invalid satellite candidate indices")
            measured = data.measured[rows]
            unwrapped = np.unwrap(measured * (2 * np.pi / ALIAS_HZ)) * ALIAS_HZ / (2 * np.pi)
            self.blocks.append(
                {
                    "track_index": index,
                    "rows": rows,
                    "candidates": candidates,
                    "unwrapped": unwrapped,
                }
            )
        if not self.blocks:
            raise ValueError("No tracks retain two group-exclusive observations")
        self.paired_rows = np.concatenate(
            [np.repeat(block["rows"], len(block["candidates"])) for block in self.blocks]
        )
        self.paired_satellites = np.concatenate(
            [np.tile(block["candidates"], len(block["rows"])) for block in self.blocks]
        )
        self.calls = 0

    def evaluate(self, point):
        self.calls += 1
        parameters = np.zeros(6 + len(self.data.numbers))
        parameters[:2] = point
        predicted, visible = self.data.predict(
            parameters, rows=self.paired_rows, satellites=self.paired_satellites
        )
        predicted = np.asarray(predicted)
        visible = np.asarray(visible, dtype=bool)
        if predicted.shape != self.paired_rows.shape or visible.shape != predicted.shape:
            raise ValueError("Prediction port returned incompatible paired shapes")
        assignments = []
        cursor = 0
        for block in self.blocks:
            rows, candidates = block["rows"], block["candidates"]
            count = len(rows) * len(candidates)
            predictions = predicted[cursor : cursor + count].reshape(len(rows), len(candidates))
            visibility = visible[cursor : cursor + count].reshape(len(rows), len(candidates))
            cursor += count
            usable = np.all(np.isfinite(predictions), axis=0) & np.any(visibility, axis=0)
            values = block["unwrapped"][:, None] - np.where(
                np.isfinite(predictions), predictions, 0
            )
            offsets = robust_locations(values)
            costs = np.mean(loss(values - offsets), axis=0)
            costs[~usable] = np.inf
            order = np.argsort(costs, kind="stable")
            best = int(order[0])
            runner_up = float(costs[order[1]]) if len(order) > 1 else float("inf")
            center = float((self.data.times[rows[0]] + self.data.times[rows[-1]]) / 2)
            assignments.append(
                {
                    "track_index": block["track_index"],
                    "satellite_index": int(candidates[best]),
                    "catalog_number": int(self.data.numbers[candidates[best]]),
                    "source_groups": len(rows),
                    "rows": rows,
                    "receiver": int(self.data.receiver[rows[0]]),
                    "center_s": center,
                    "span_s": float(np.ptp(self.data.times[rows])),
                    "constant_offset_hz": float(offsets[best]),
                    "cost": float(costs[best]),
                    "runner_up_cost": runner_up,
                    "accepted": bool(np.isfinite(costs[best]) and costs[best] < loss(CAP_HZ)),
                }
            )
        score = float(np.mean([min(row["cost"], loss(CAP_HZ)) for row in assignments]))
        return score, assignments


def fit_rough(data, *, region_km=200.0, step_km=50.0, budget_s=45.0, max_nfev=200):
    from scipy.optimize import minimize

    objective = TrackObjective(data)
    started = time.monotonic()
    deadline = started + budget_s
    evaluated = []

    def score(point):
        if time.monotonic() > deadline:
            raise TimeoutError("Rough-track fit wall-clock budget exhausted")
        value, _ = objective.evaluate(point)
        evaluated.append((value, np.asarray(point).copy()))
        return value

    local_runs = []
    try:
        axis = np.arange(-region_km, region_km + 0.01, step_km)
        for east in axis:
            for north in axis:
                score([east, north])
        seeds = sorted(evaluated, key=lambda row: row[0])[:3]
        for _, seed in seeds:
            fitted = minimize(
                score,
                seed,
                method="Nelder-Mead",
                bounds=[(-region_km, region_km)] * 2,
                options={"maxfev": max_nfev, "xatol": 0.02, "fatol": 0.05},
            )
            local_runs.append(
                {
                    "point": fitted.x.tolist(),
                    "objective": float(fitted.fun),
                    "success": bool(fitted.success),
                    "message": str(fitted.message),
                }
            )
    except TimeoutError:
        pass
    if not evaluated:
        raise TimeoutError("No rough-track position evaluated within budget")
    successful = [row for row in local_runs if row["success"]]
    if successful:
        best = min(successful, key=lambda row: row["objective"])
        point = np.asarray(best["point"])
    else:
        _, point = min(evaluated, key=lambda row: row[0])
    value, assignments = objective.evaluate(point)
    return {
        "position_km": point,
        "objective": value,
        "assignments": assignments,
        "success": bool(successful),
        "local_runs": local_runs,
        "elapsed_s": time.monotonic() - started,
        "evaluations": objective.calls,
        "scope": "Whole-track shape fit with profiled independent constants; no RX-line "
        "constraint or timing shifts; associations are provisional hypotheses",
    }
