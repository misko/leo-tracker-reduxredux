"""Matched-support phase-release diagnostic with one observed NORAD per stock group."""

from collections import Counter


def point_map(context, node, entries):
    scan = context["scan"]
    tracks = {t["key"]: t for t in scan.tracks}
    curve = {}
    count = 0
    curved = (row for row in node["seed"]["rows"] if row["active_curvature"])
    for row, alias in zip(curved, node["aliases"], strict=True):
        track = tracks[row["component"]]
        ids = track["observation_ids"]
        for oid, value, keep in zip(
            ids, track["values"], context["keep"][count : count + len(ids)], strict=True
        ):
            if keep:
                if oid in curve:
                    raise ValueError("duplicate active observation in stock layout")
                curve[oid] = dict(
                    group=track["key"],
                    norad=int(row["candidate_norad"]),
                    alias=int(alias),
                    value=float(value),
                    index=count,
                )
            count += 1
    if count != len(context["keep"]):
        raise ValueError("active mask and track order disagree")
    predictive = {
        oid: dict(group=e["component"], norad=int(e["norad"]), alias=int(e["alias"]))
        for e in entries
        for oid in e["observation_ids"]
    }
    if len(predictive) != sum(e["points"] for e in entries) or curve.keys() & predictive.keys():
        raise ValueError("curved and predictive layouts overlap or have duplicate observations")
    return dict(curved=curve, predictive=predictive)


def matching(stock, union, catalogue, period):
    shared = stock.keys() & union.keys()
    by_group = {}
    for oid in sorted(shared):
        by_group.setdefault(stock[oid]["group"], []).append(oid)
    included, changes, counts = [], {}, Counter()
    for group, points in by_group.items():
        old = {stock[oid]["norad"] for oid in points}
        owners = {union[oid]["norad"] for oid in points}
        if len(old) != 1:
            raise ValueError("original group contains multiple stock NORADs")
        if len(owners) != 1:
            counts["ambiguous_points"] += len(points)
        elif not owners <= catalogue:
            counts["unavailable_points"] += len(points)
        else:
            included.extend(points)
            if old != owners:
                changes[group] = dict(
                    stock=next(iter(old)), union=next(iter(owners)), points=len(points)
                )
    counts.update(
        stock_active=len(stock),
        union_active=len(union),
        common=len(shared),
        matched=len(included),
        stock_only=len(stock.keys() - union.keys()),
        union_only=len(union.keys() - stock.keys()),
        common_changed_norad=sum(stock[k]["norad"] != union[k]["norad"] for k in shared),
        common_unwrap_changed=sum(stock[k]["value"] != union[k]["value"] for k in shared),
        common_total_cfo_alias_changed=sum(
            stock[k]["value"] + stock[k]["alias"] * period
            != union[k]["value"] + union[k]["alias"] * period
            for k in shared
        ),
        common_stock_group_count=len(by_group),
        coherent_swapped_groups=len(changes),
    )
    return included, changes, dict(counts)
