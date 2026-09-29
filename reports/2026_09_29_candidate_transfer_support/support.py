"""Causal same-roster candidate support, without asserted satellite identity."""


def roster_key(scan):
    return scan["snapshot"], scan["catalogue_size"]


def census(scans):
    ordered = sorted(scans, key=lambda s: (s["start_utc_ns"], s["session_id"]))
    if len({s["session_id"] for s in ordered}) != len(ordered):
        raise ValueError("Duplicate recording")
    rows = []
    for target in ordered:
        earlier = [
            s
            for s in ordered
            if s["start_utc_ns"] < target["start_utc_ns"] and roster_key(s) == roster_key(target)
        ]
        for track in target["tracks"]:
            for scope in ("any_earlier_scan", "earlier_other_panel"):
                donors = [
                    s
                    for s in earlier
                    if scope == "any_earlier_scan" or s["panel"] != target["panel"]
                ]
                for match in ("any_receiver_rf", "same_receiver_rf"):
                    all_support = {}
                    strong_support = {}
                    for scan in donors:
                        raw = set()
                        strong = set()
                        for t in scan["tracks"]:
                            if match == "same_receiver_rf" and (t["receiver_id"], t["rf_hz"]) != (
                                track["receiver_id"],
                                track["rf_hz"],
                            ):
                                continue
                            raw.update(t["ids"])
                            strong.update(
                                i
                                for i, w in zip(t["ids"], t["weights"], strict=True)
                                if w * t["signal_responsibility"] >= 0.5
                            )
                        for i in raw:
                            all_support[i] = all_support.get(i, 0) + 1
                        for i in strong:
                            strong_support[i] = strong_support.get(i, 0) + 1
                    ordered_ids = sorted(
                        zip(track["ids"], track["weights"], strict=True),
                        key=lambda x: (-x[1], x[0]),
                    )
                    rows.append(
                        dict(
                            session_id=target["session_id"],
                            panel=target["panel"],
                            dataset=target["panel"][:3],
                            track_id=track["track_id"],
                            scope=scope,
                            match=match,
                            compatible_donor_scans=len(donors),
                            raw_two_scan_mass=sum(
                                w for i, w in ordered_ids if all_support.get(i, 0) >= 2
                            ),
                            strong_two_scan_mass=sum(
                                w for i, w in ordered_ids if strong_support.get(i, 0) >= 2
                            ),
                            map_has_two_strong_scans=strong_support.get(ordered_ids[0][0], 0) >= 2,
                            target_signal_responsibility=track["signal_responsibility"],
                        )
                    )
    return rows
