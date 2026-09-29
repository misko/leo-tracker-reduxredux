"""Posthoc one-donor sensitivity after the frozen two-donor census was zero."""

from collections import Counter, defaultdict

from study import HERE, read, save, verify


def main():
    verify(read(HERE / "seal.json")["sha256"])
    scans = read(HERE / "result.json")["scans"]
    records = defaultdict(set)
    strong = defaultdict(set)
    byscan = {s["session_id"]: s for s in scans}
    for s in scans:
        for t in s["tracks"]:
            for i, w in zip(t["ids"], t["weights"], strict=True):
                key = (s["snapshot"], s["catalogue_size"], i)
                records[key].add(s["session_id"])
                if w * t["signal_responsibility"] >= 0.5:
                    strong[key].add(s["session_id"])
    histogram = Counter(len(v) for v in records.values())
    pairs = defaultdict(set)
    for key, members in records.items():
        ordered = sorted(members, key=lambda sid: (byscan[sid]["start_utc_ns"], sid))
        for i, target in enumerate(ordered):
            for donor in ordered[:i]:
                pairs[donor, target].add(key[2])
    pair_rows = [
        dict(
            donor=a,
            target=b,
            shared_rows=len(v),
            gap_seconds=(byscan[b]["start_utc_ns"] - byscan[a]["start_utc_ns"]) / 1e9,
            donor_panel=byscan[a]["panel"],
            target_panel=byscan[b]["panel"],
        )
        for (a, b), v in pairs.items()
    ]
    rows = []
    for s in scans:
        for t in s["tracks"]:
            for scope in ("any_earlier_scan", "earlier_other_panel"):
                allowed = {
                    a["session_id"]
                    for a in scans
                    if a["start_utc_ns"] < s["start_utc_ns"]
                    and (scope == "any_earlier_scan" or a["panel"] != s["panel"])
                }
                rawmass = 0.0
                strongmass = 0.0
                supported = set()
                for i, w in zip(t["ids"], t["weights"], strict=True):
                    key = (s["snapshot"], s["catalogue_size"], i)
                    if records[key] & allowed:
                        rawmass += w
                    if strong[key] & allowed:
                        strongmass += w
                        supported.add(i)
                map_id = min(
                    i for i, w in zip(t["ids"], t["weights"], strict=True) if w == max(t["weights"])
                )
                rows.append(
                    dict(
                        dataset=s["panel"][:3],
                        session_id=s["session_id"],
                        track_id=t["track_id"],
                        scope=scope,
                        raw_mass=rawmass,
                        strong_mass=strongmass,
                        map_supported=map_id in supported,
                    )
                )
    aggregates = []
    for ds in ("DS7", "DS8", "DS9"):
        for scope in ("any_earlier_scan", "earlier_other_panel"):
            rr = [r for r in rows if r["dataset"] == ds and r["scope"] == scope]
            aggregates.append(
                dict(
                    dataset=ds,
                    scope=scope,
                    tracks=len(rr),
                    raw_mass=sum(r["raw_mass"] for r in rr) / len(rr),
                    strong_mass=sum(r["strong_mass"] for r in rr) / len(rr),
                    map_supported=sum(r["map_supported"] for r in rr),
                )
            )
    save(
        HERE / "one-donor-diagnostic.json",
        dict(
            posthoc=True,
            rule="one donor; any RX/RF; not a promotion gate",
            catalogue_row_scan_multiplicity=dict(sorted(histogram.items())),
            pairs=pair_rows,
            aggregates=aggregates,
            rows=rows,
        ),
    )
    print(dict(histogram), pair_rows, aggregates, flush=True)


if __name__ == "__main__":
    main()
