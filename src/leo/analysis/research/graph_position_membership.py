"""Disjoint original-point roles for graph-position diagnostic views."""


def point_roles(observations, tracks, curved, predictive, accepted):
    original = {o["observation_id"] for o in observations}
    graph = {oid for t in tracks for oid in t["observation_ids"]}
    curved, predictive, accepted = map(set, (curved, predictive, accepted))
    if len(original) != len(observations) or curved & predictive:
        raise ValueError("Duplicate original or overlapping likelihood owners")
    if not curved | predictive <= accepted <= original or not graph <= original:
        raise ValueError("Membership contains nonphysical or omitted likelihood points")
    return {oid: ("curved_likelihood" if oid in curved else
                  "predictive_likelihood" if oid in predictive else
                  "postfit_only" if oid in accepted else
                  "unassociated_graph" if oid in graph else "unassociated_outside_graph")
            for oid in original}


def native_polynomial(track, observations_by_id):
    """Render each graph piece in the measured alias, with gaps preserved."""
    import numpy as np
    t = np.asarray(track["times"])
    native = np.array([observations_by_id[o]["measured_cfo_hz"] for o in track["observation_ids"]])
    lifts = np.asarray(track["values"]) - native
    result = []
    for piece in track["pieces"]:
        use = (t >= piece["start_s"]) & (t <= piece["end_s"])
        y = np.polynomial.legendre.legval((t-piece["reference_time_s"])/piece["time_scale_s"], piece["coefficients_hz"]) - lifts
        y[~use] = np.nan
        y[np.r_[False, np.abs(np.diff(y)) > 100000]] = np.nan
        result.append(y)
    return result
