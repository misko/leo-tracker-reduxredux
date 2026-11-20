"""Transfer a signed CFO correction from literal same-probe detector matches."""

from collections import Counter, defaultdict
from statistics import mean, median

import numpy as np

from ..variants.selective_capture import same_support, wrapped
from .factor_cross import CFO, GATE, winner
from .full_v5_check import ALIAS_HZ, FRAME_HZ

EPOCH_TOLERANCE = 2.0
CFO_TOLERANCE = 1_000.0
MODELS = ("offset", "affine", "edge_rf")
MIN_RF_CASES = 2
MIN_RF_ROWS = 80
MIN_CV_GAIN_HZ = 1.0


def _phase(point):
    return point["integer_epoch_sample"] + point["fractional_epoch_offset_samples"]


def selected(candidates):
    index = winner(candidates)
    return candidates[index] if index is not None else None


def pairs(ident, fast, original):
    """Pair gate winners only, with alternative and rejected support tracked separately."""
    same_support(fast, original)
    period = round(fast["source"]["sample_rate_hz"] / FRAME_HZ)
    samples, counts = [], Counter()
    for a, b in zip(fast["source"]["probes"], original["source"]["probes"], strict=True):
        if {k: v for k, v in a.items() if k != "candidates"} != {
            k: v for k, v in b.items() if k != "candidates"
        }:
            raise ValueError("literal matching requires the same physical RF probe and clock")
        counts.update(
            probes=1,
            fast_candidates=len(a["candidates"]),
            original_candidates=len(b["candidates"]),
            fast_gate_passes=sum(c[GATE] for c in a["candidates"]),
            original_gate_passes=sum(c[GATE] for c in b["candidates"]),
        )
        x, y = (selected(p["candidates"]) for p in (a, b))
        counts["fast_positive"] += x is not None
        counts["original_positive"] += y is not None
        if y is None:
            counts["fast_only" if x is not None else "neither"] += 1
            continue
        if x is None:
            counts["original_only"] += 1
        else:
            difference = y[CFO] - x[CFO]
            epoch = wrapped(_phase(y) - _phase(x), period)
            if abs(epoch) <= EPOCH_TOLERANCE and abs(difference) <= CFO_TOLERANCE:
                counts["literal_winners"] += 1
                samples.append(
                    dict(
                        id=ident,
                        visit=a["visit_index"],
                        rx=a["receiver_id"],
                        edge=a["edge"],
                        rf=int(a["actual_rf_hz"]),
                        fast_cfo_hz=x[CFO],
                        difference_hz=difference,
                        epoch_difference_samples=epoch,
                        fast_rank=x["candidate_rank"],
                        original_rank=y["candidate_rank"],
                    )
                )
                continue
            if (
                abs(epoch) <= EPOCH_TOLERANCE
                and abs(wrapped(difference, ALIAS_HZ)) <= CFO_TOLERANCE
            ):
                counts["aliased_winners"] += 1
            else:
                counts["different_winners"] += 1
        phase = [
            c
            for c in a["candidates"]
            if abs(wrapped(_phase(c) - _phase(y), period)) <= EPOCH_TOLERANCE
        ]
        literal = [c for c in phase if abs(c[CFO] - y[CFO]) <= CFO_TOLERANCE]
        if any(c[GATE] for c in literal):
            counts["literal_positive_alternate"] += 1
        elif literal:
            counts["literal_rejected"] += 1
        elif any(abs(wrapped(c[CFO] - y[CFO], ALIAS_HZ)) <= CFO_TOLERANCE for c in phase):
            counts["aliased_alternate"] += 1
        else:
            counts["no_literal_candidate"] += 1
    return samples, dict(counts)


def band(edge, rf):
    return f"{edge}:{int(rf)}"


def fit(rows, name):
    if name not in MODELS or not rows:
        raise ValueError("calibration needs development rows and a defined model")
    y = np.asarray([r["difference_hz"] for r in rows], dtype=float)
    center = float(np.median(y))
    model = dict(name=name, offset_hz=center)
    if name == "affine":
        x = np.asarray([r["fast_cfo_hz"] for r in rows], dtype=float) / 1e6
        design = np.column_stack((np.ones(len(x)), x))
        coeff = np.asarray([center, 0])
        for _ in range(8):
            residual = y - design @ coeff
            scale = max(0.1, 1.4826 * float(np.median(np.abs(residual - np.median(residual)))))
            weight = np.sqrt(np.minimum(1, 2.5 * scale / np.maximum(np.abs(residual), 1e-9)))
            coeff, *_ = np.linalg.lstsq(design * weight[:, None], y * weight, rcond=None)
        model.update(offset_hz=float(coeff[0]), slope_hz_per_mhz=float(coeff[1]))
    if name == "edge_rf":
        groups = defaultdict(list)
        edges = defaultdict(list)
        for r in rows:
            groups[band(r["edge"], r["rf"])].append(r)
            edges[r["edge"]].append(r["difference_hz"])
        model.update(
            per_rf={
                k: median(r["difference_hz"] for r in group)
                for k, group in groups.items()
                if len(group) >= MIN_RF_ROWS and len({r["id"] for r in group}) >= MIN_RF_CASES
            },
            per_edge={k: median(v) for k, v in edges.items()},
        )
    return model


def correction(model, cfo, edge, rf):
    if model["name"] == "affine":
        return model["offset_hz"] + model["slope_hz_per_mhz"] * (cfo / 1e6)
    if model["name"] == "edge_rf":
        return model["per_rf"].get(band(edge, rf), model["per_edge"].get(edge, model["offset_hz"]))
    return model["offset_hz"]


def residual(rows, model, sign=1):
    return [
        r["difference_hz"] - sign * correction(model, r["fast_cfo_hz"], r["edge"], r["rf"])
        for r in rows
    ]


def choose(groups):
    """Only an independently useful richer form can replace the basic robust offset."""
    all_rows = [r for rows in groups.values() for r in rows]
    folds = {}
    for name in MODELS:
        folds[name] = {}
        for ident, held in groups.items():
            model = fit([r for r in all_rows if r["id"] != ident], name)
            folds[name][ident] = median(map(abs, residual(held, model)))
    loss = {name: mean(r.values()) for name, r in folds.items()}
    rich = min(MODELS[1:], key=loss.get)
    winner_name = rich if loss["offset"] - loss[rich] >= MIN_CV_GAIN_HZ else "offset"
    return winner_name, {name: fit(all_rows, name) for name in MODELS}, folds, loss


def apply(document, model, sign=1):
    """Shift admitted CFOs using fast factors alone and preserve all gate and epoch fields."""
    if sign not in (-1, 1):
        raise ValueError("correction sign must be positive or reversed")
    output, changed = [], 0
    mode = model["name"]
    for p in document["source"]["probes"]:
        edge, rf = p["edge"], p["actual_rf_hz"]
        offset = (
            model["per_rf"].get(band(edge, rf), model["per_edge"].get(edge, model["offset_hz"]))
            if mode == "edge_rf"
            else model["offset_hz"]
        )
        slope = model.get("slope_hz_per_mhz", 0.0) / 1e6
        candidates = []
        for c in p["candidates"]:
            if c[GATE]:
                cfo = c[CFO] + sign * (offset + slope * c[CFO])
                candidates.append(dict(c, **{CFO: cfo}))
                changed += cfo != c[CFO]
            else:
                candidates.append(c)
        output.append(dict(p, candidates=candidates))
    return dict(document, source=dict(document["source"], probes=output)), changed
