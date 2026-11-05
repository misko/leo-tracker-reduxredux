"""Primary receiver-shared predictive guard with explicit causal evidence."""

import numpy as np

from leo.analysis.localization_v3.reassociation_catalogue import bank_for
from leo.analysis.localization_v3.reassociation_context import build
from leo.analysis.localization_v3.reassociation_predictive import GUARD_SEED, partitions, predict
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency

ARMS = ("c0", "fitted_c")


def receiver_shared_check(
    d,
    scan_receipt,
    screen,
    old,
    new,
    ledger,
    *,
    models=("receiver_offset",),
    phase_sds=(5.0,),
    regional_offsets=((0.0, 0.0),),
    include_arrays=False,
):
    """Generic bounded finalist check using supplied causal context and screen.

    No case roster, storage writes, GPS, history mutation, or archive reads.
    Defaults execute only the primary receiver-shared guard. The diagnostic
    wrapper requests the extra nuisance/prior/regional cells explicitly.
    The caller owns baseline reconstruction and the full causal ledger.
    """
    cutoff = scan_receipt["cutoff_utc_ns"]
    for n in screen["nominees"]:
        element = ledger[str(n)]
        if not (
            0 <= cutoff - element["element_epoch_utc_ns"] <= int(72 * 3600000000000.0)
            and element["collected_utc_ns"] <= cutoff
        ):
            raise ValueError("finalist element must be verifiably scan-causal and within72h")
    nums, bank, failures = bank_for(
        {str(n): ledger[str(n)] for n in screen["nominees"]}, scan_receipt["origin_utc_ns"]
    )
    base = d["problems"]["fitted_c"][0]
    tracks = [
        (i, base.keep[sl])
        for row, i, sl in zip(base.rows, base.members, base.slices, strict=True)
        if row["candidate_norad"] == old and base.keep[sl].any()
    ]
    times = np.concatenate([d["scan"].tracks[i]["times"][use] for i, use in tracks])
    q = np.concatenate(
        [np.full(use.sum(), d["scan"].tracks[i]["rf_hz"] / 11500000000.0) for i, use in tracks]
    )
    groups = np.concatenate([np.full(use.sum(), k) for k, (i, use) in enumerate(tracks)])
    receivers = np.concatenate(
        [np.full(use.sum(), d["scan"].tracks[i]["receiver"]) for i, use in tracks]
    )
    native_ids = [
        o
        for i, use in tracks
        for o, keep in zip(d["scan"].tracks[i]["observation_ids"], use, strict=True)
        if keep
    ]
    assert len(native_ids) == len(set(native_ids)) == len(times)
    parts = partitions(times, groups)
    phase = np.linspace(-30, 30, 151)
    rows = []
    regional = []
    arrays = dict(
        times_s=times,
        rf_scale=q,
        track_group=groups,
        receiver=receivers,
        observation_ids=np.asarray(native_ids),
    )
    for arm in ARMS:
        saved = screen["cavity"][arm]
        p, _ = build(d, arm, np.asarray(saved["reference"]), omit=old)
        point = np.asarray(saved["x"])
        state = p.state(point)
        values = np.concatenate(
            [
                (
                    tr["values"]
                    - p.scan.hardware(tr, state["beta"])
                    - tr["rf_hz"]
                    / 11500000000.0
                    * p.scan.rx_basis[i]
                    @ state["smooth"][tr["receiver"] - 1]
                )[use]
                for i, use in tracks
                for tr in [p.scan.tracks[i]]
            ]
        )
        arrays[arm + "_cavity_values_hz"] = values
        for offset in regional_offsets:
            at = np.clip(point + offset, -12.5, 12.5)
            for j, num in enumerate(nums):
                bb = dict(
                    time_s=bank["time_s"],
                    position_km=np.broadcast_to(
                        bank["position_km"][j], (len(phase), *bank["position_km"][j].shape)
                    ),
                    velocity_km_s=np.broadcast_to(
                        bank["velocity_km_s"][j], (len(phase), *bank["velocity_km_s"][j].shape)
                    ),
                )
                ff, el = paired_phase_frequency(
                    bb,
                    np.tile(times, len(phase)),
                    np.repeat(np.arange(len(phase)), len(times)),
                    phase,
                    *d["scan"].search_region.latlon(at),
                )
                if np.min(el) < 0:
                    regional.append(
                        dict(arm=arm, offset_km=offset, norad=int(num), status="below_horizon")
                    )
                    continue
                raw = values[None, :] - ff.reshape(len(phase), -1) * q
                if offset == (0.0, 0.0):
                    arrays[f"{arm}_{num}_raw_hz"] = raw
                    for model in models:
                        for sd in phase_sds:
                            for split in parts:
                                fitted = predict(
                                    raw,
                                    times,
                                    q,
                                    groups,
                                    receivers,
                                    split["train"],
                                    split["test"],
                                    phase,
                                    model,
                                    sd,
                                )
                                rows.append(
                                    dict(
                                        arm=arm,
                                        norad=int(num),
                                        model=model,
                                        phase_sd_s=sd,
                                        fold=split["fold"],
                                        held_points=int(split["test"].sum()),
                                        **fitted,
                                    )
                                )
                for model in models:
                    all_points = np.ones(len(times), bool)
                    regional.append(
                        dict(
                            arm=arm,
                            offset_km=offset,
                            position_km=at,
                            norad=int(num),
                            model=model,
                            status="complete",
                            **predict(
                                raw,
                                times,
                                q,
                                groups,
                                receivers,
                                all_points,
                                all_points,
                                phase,
                                model,
                                5.0,
                            ),
                        )
                    )
    output = dict(
        old=old,
        new=new,
        seed=GUARD_SEED,
        parts=parts,
        rows=rows,
        regional=regional,
        provenance={str(n): ledger[str(n)] for n in screen["nominees"]},
        propagation_failures=failures,
        scope=(
            "Unique randomized whole-time-group finalist checks; full-data nomination and cavity "
            "fitting inherited. No GPS selection, later TLE, full catalogue exact search, or new "
            "acceptance. Regional cells freeze cavity radio calibration."
        ),
    )
    if include_arrays:
        output["arrays"] = dict(phase_grid_s=phase, **arrays)
    return output
