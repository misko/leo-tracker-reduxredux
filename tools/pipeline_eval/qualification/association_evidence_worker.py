"""Read-only traces of the frozen native joint solver, including its actual owner rows."""

import json
import sys
from unittest.mock import patch

from tools.pipeline_eval.variants import joint_orbits as joint
from tools.pipeline_eval.variants import native_lean as native
from tools.pipeline_eval.variants import robust_orbit_fit as exact


def state(value):
    if value is None:
        return None
    return dict(
        xy=value.xy.tolist(),
        bias=value.bias.tolist(),
        drift=value.drift.tolist(),
        phase=value.phase.tolist(),
        c_hz_per_ghz=value.c_hz_per_ghz,
    )


def worker(request):
    real_fit = exact.infer
    real_solve, real_train, real_associate = joint.solve, joint._train, joint.associate
    valid_states = exact.grid._valid_states
    trace = dict(training=[], banks=[], all_associations=[])
    track_indexes = {}

    def bank(*args, **kwargs):
        data = valid_states(*args, **kwargs)
        trace["banks"].append([int(sat.satnum) for sat in data[0]])
        return data

    def owners(rows):
        return [
            dict(
                track=track_indexes[id(row.arc.track)],
                orbit=int(row.orbit),
                alias=int(row.alias),
                loss=float(row.loss),
                margin=float(row.margin),
            )
            for row in rows
        ]

    def associate(*args, **kwargs):
        rows, moves = real_associate(*args, **kwargs)
        trace["all_associations"].append(owners(rows))
        return rows, moves

    def train(*args, **kwargs):
        fitted, rows, moves = real_train(*args, **kwargs)
        trace["training"].append(dict(state=state(fitted), owners=owners(rows), pair_moves=moves))
        return fitted, rows, moves

    def solve(arcs, tile, region, half):
        lookup = {
            (
                float(x["rf_hz"]),
                2 * (x["receiver"] - 1) + int(x["channel"] > 4),
                tuple(x["times"]),
            ): i
            for i, x in enumerate(trace["observation"]["tracks"])
        }

        def index(track):
            return lookup[(track.rf, track.lane, tuple(track.t))]

        track_indexes.update({id(a.track): index(a.track) for a in arcs})
        trace["arcs"] = [
            dict(
                index=index(a.track),
                curved=a.track.curved,
                lane=a.track.lane,
                held=int(a.track.t.mean() // 12) % 5 == 2,
                shortlist=[int(v) for v in a.orbit],
            )
            for a in arcs
        ]
        fits, metrics, reason = real_solve(arcs, tile, region, half)
        trace["fit_states"] = {arm: state(fit.state) for arm, fit in fits.items()}
        return fits, metrics, reason

    def infer(observation, offer, catalogue):
        trace["observation"] = observation
        return joint.infer(observation, offer, catalogue)

    with (
        patch.object(exact, "infer", infer),
        patch.object(joint, "solve", solve),
        patch.object(joint, "_train", train),
        patch.object(joint, "associate", associate),
        patch.object(exact.grid, "_valid_states", bank),
    ):
        out = native.worker(request)
    assert exact.infer is real_fit
    out["trace"] = trace
    return out


if __name__ == "__main__":
    json.dump(worker(json.load(sys.stdin)), sys.stdout, allow_nan=False, separators=(",", ":"))
