"""Apply unique qualified frame CFOs without dropping original observations."""

import numpy as np

PERIOD_HZ = 1 / 4.4e-6


def replay_qualified_frequencies(tracks, records, *, require_complete=True):
    """Keep Graph membership, native alias branch, times and unsupported values.

    More than one supported physical alias is treated as ambiguous. No satellite
    label, orbit, reference position or fitted residual can select a measurement.
    """
    originals = {}
    for track in tracks:
        for index, oid in enumerate(track["observation_ids"]):
            if oid in originals:
                raise ValueError("duplicate original observation identity")
            originals[oid] = track, index
    incoming = {}
    for row in records:
        oid = row["observation_id"]
        if oid in incoming or oid not in originals:
            raise ValueError("duplicate or unknown refined observation identity")
        incoming[oid] = row
    if require_complete and incoming.keys() != originals.keys():
        raise ValueError("complete original point population required")
    output = [dict(t, values=np.asarray(t["values"], float).copy()) for t in tracks]
    target = {t["key"]: t for t in output}
    if len(target) != len(output):
        raise ValueError("duplicate original track identity")
    statuses = []
    for oid, (track, index) in originals.items():
        row = incoming.get(oid)
        status, delta = "not_evaluated_original_retained", 0.0
        if row is not None:
            if (
                row["component"] != track["key"]
                or row["receiver"] != track["receiver"]
                or row["channel"] != track["channel"]
                or abs(row["time_s"] - track["times"][index]) > 1e-8
                or not np.isfinite(row["graph_cfo_hz"])
                or abs(row["graph_cfo_hz"] - track["values"][index]) > 1e-5
            ):
                raise ValueError("refined measurement does not bind original observation")
            supported = [b for b in row["branches"] if b["measurement_supported"]]
            if len(supported) != row["supported_branches"]:
                raise ValueError("inconsistent qualified alias count")
            status = "unsupported_original_retained"
            if len(supported) > 1:
                status = "ambiguous_alias_original_retained"
            elif len(supported) == 1:
                branch = supported[0]
                native = branch["absolute_cfo_hz"] - branch["alias"] * PERIOD_HZ
                if not np.isfinite(native):
                    raise ValueError("nonfinite qualified frequency")
                if not row["best_supported"] or branch["alias"] != row["best_alias"]:
                    raise ValueError("inconsistent selected qualified alias")
                delta = native - row["original_glrt_cfo_hz"]
                target[track["key"]]["values"][index] += delta
                status = "unique_qualified_frame_cfo"
        statuses.append(
            dict(
                observation_id=oid,
                component=track["key"],
                status=status,
                correction_hz=float(delta),
            )
        )
    counts = {
        status: sum(r["status"] == status for r in statuses)
        for status in sorted({r["status"] for r in statuses})
    }
    return output, dict(
        original_points=len(originals),
        evaluated_points=len(incoming),
        points_dropped=0,
        status_counts=counts,
        points=statuses,
    )
