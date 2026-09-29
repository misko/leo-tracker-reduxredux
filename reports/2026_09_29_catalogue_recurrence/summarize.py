"""Independent raw-line roster audit and recurrence reconstruction."""
# ruff: noqa: E501 -- Markdown prose and tables.

import gzip
import hashlib
from collections import Counter, defaultdict

import matplotlib
import numpy as np
from study import HERE, read, save, verify

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def raw_roster(payload):
    lines = [line.rstrip() for line in payload.splitlines() if line.strip()]
    numbers = []
    excluded = 0
    offset = 0
    while offset < len(lines):
        name = ""
        if not lines[offset].startswith("1 "):
            name = lines[offset].removeprefix("0 ").strip()
            offset += 1
        a, b = lines[offset : offset + 2]
        assert a.startswith("1 ") and b.startswith("2 ") and a[2:7] == b[2:7]
        # All bound snapshots use numeric catalogue fields. Fail on other encodings.
        number = int(a[2:7])
        if name.upper().startswith("STARLINK") and name.upper().endswith(" DEB"):
            excluded += 1
        else:
            numbers.append(number)
        offset += 2
    return numbers, excluded


def main():
    assert read(HERE / "exit.json")["exit_code"] == 0
    verify(read(HERE / "seal.json")["sha256"])
    rosters = read(HERE / "rosters.json")
    for key, roster in rosters.items():
        raw = gzip.decompress((HERE / roster["raw_snapshot"]).read_bytes())
        assert "sha256:" + hashlib.sha256(raw).hexdigest() == key
        numbers, excluded = raw_roster(raw.decode())
        assert numbers == roster["numbers"] and len(numbers) == roster["size"]
        assert excluded == roster["excluded"] and len(set(numbers)) == len(numbers)
    result = read(HERE / "result.json")
    scans = result["scans"]
    byid = {s["session_id"]: s for s in scans}
    assert len(byid) == len(scans) == 258
    occurrences = defaultdict(set)
    tracks = {}
    for s in scans:
        for t in s["tracks"]:
            assert t["numbers"] == [rosters[s["snapshot"]]["numbers"][i] for i in t["ids"]]
            tracks[s["session_id"], t["track_id"]] = t
            for n in t["numbers"]:
                occurrences[n].add(s["session_id"])
    assert {str(n): len(v) for n, v in occurrences.items()} == result[
        "physical_candidate_scan_multiplicity"
    ]
    assert len(result["raw_rows"]) == 2 * len(tracks)
    assert len(
        {(r["session_id"], r["track_id"], r["outside_block"]) for r in result["raw_rows"]}
    ) == len(result["raw_rows"])
    allowed = {}
    for s in scans:
        for outside in (False, True):
            allowed[s["session_id"], outside] = {
                a["session_id"]
                for a in scans
                if a["start_utc_ns"] < s["start_utc_ns"]
                and (not outside or a["block"] != s["block"])
            }
    for r in result["raw_rows"]:
        t = tracks[r["session_id"], r["track_id"]]
        donors = allowed[r["session_id"], r["outside_block"]]
        assert r["candidates"] == len(t["numbers"])
        assert r["supported_candidates"] == sum(
            len(occurrences[n] & donors) >= 2 for n in t["numbers"]
        )
    ps = result["panel_scans"]
    panel_index = {s["session_id"]: s for s in ps}
    strong = defaultdict(set)
    pt = {}
    for s in ps:
        for t in s["tracks"]:
            pt[s["session_id"], t["track_id"]] = t
            assert t["numbers"] == tracks[s["session_id"], t["track_id"]]["numbers"]
            assert abs(sum(t["weights"]) - 1) < 1e-8 and min(t["weights"]) >= 0
            for n, w in zip(t["numbers"], t["weights"], strict=True):
                if w * t["signal_responsibility"] >= 0.5:
                    strong[n].add(s["session_id"])
    assert len(ps) == 72 and len(pt) == 4328 and len(result["panel_rows"]) == 8656
    for r in result["panel_rows"]:
        s = panel_index[r["session_id"]]
        t = pt[r["session_id"], r["track_id"]]
        donors = {
            a["session_id"]
            for a in ps
            if a["start_utc_ns"] < s["start_utc_ns"]
            and (not r["outside_panel"] or a["panel"] != s["panel"])
        }
        mass = sum(
            w
            for n, w in zip(t["numbers"], t["weights"], strict=True)
            if len(strong[n] & donors) >= 2
        )
        assert abs(mass - r["strong_mass"]) < 1e-12
    raw_aggregates = []
    panel_aggregates = []
    for ds in ("DS7", "DS8", "DS9"):
        for outside in (False, True):
            rr = [
                r
                for r in result["raw_rows"]
                if r["dataset"] == ds and r["outside_block"] == outside
            ]
            raw_aggregates.append(
                dict(
                    dataset=ds,
                    outside_block=outside,
                    tracks=len(rr),
                    tracks_with_support=sum(r["supported_candidates"] > 0 for r in rr),
                    scans_with_support=len(
                        {r["session_id"] for r in rr if r["supported_candidates"] > 0}
                    ),
                    candidates=sum(r["candidates"] for r in rr),
                    supported_candidates=sum(r["supported_candidates"] for r in rr),
                )
            )
            pr = [
                r
                for r in result["panel_rows"]
                if r["dataset"] == ds and r["outside_panel"] == outside
            ]
            panel_aggregates.append(
                dict(
                    dataset=ds,
                    outside_panel=outside,
                    tracks=len(pr),
                    mean_strong_mass=float(np.mean([r["strong_mass"] for r in pr])),
                    tracks_mass_above_half=sum(r["strong_mass"] > 0.5 for r in pr),
                )
            )
    histogram = Counter(len(v) for v in occurrences.values())
    summary = dict(
        audit_passed=True,
        snapshots=len(rosters),
        scans=len(scans),
        tracks=len(tracks),
        physical_candidates=len(occurrences),
        candidate_scan_multiplicity=dict(sorted(histogram.items())),
        raw_aggregates=raw_aggregates,
        panel_aggregates=panel_aggregates,
    )
    save(HERE / "summary.json", summary)
    lines = [
        "# Cross-snapshot catalogue recurrence: full frozen corpus",
        "",
        "Raw catalogue support is not posterior agreement or verified satellite identity. Full-corpus and 72-scan results use different populations and must not be conflated.",
        "",
        "| Dataset | Outside target chronological block | Tracks | Tracks with ≥2 earlier donor scans for a candidate | Scans with supported tracks | Supported candidate slots / all |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in raw_aggregates:
        lines.append(
            f"| {r['dataset']} | {r['outside_block']} | {r['tracks']} | {r['tracks_with_support']} | {r['scans_with_support']} | {r['supported_candidates']}/{r['candidates']} |"
        )
    lines += [
        "",
        "Full-corpus blocks are nonoverlapping chronological groups of eight within each dataset; final groups may be shorter. Donors are strictly earlier recordings, never repeated tracks in a single recording.",
        "",
        "| Original 72-scan subset | Outside original target panel | Tracks | Mean strong-supported conditional mass | Tracks with mass >0.5 |",
        "|---|---|---:|---:|---:|",
    ]
    for r in panel_aggregates:
        lines.append(
            f"| {r['dataset']} | {r['outside_panel']} | {r['tracks']} | {100 * r['mean_strong_mass']:.4f}% | {r['tracks_mass_above_half']} |"
        )
    lines += [
        "",
        "Strong support requires signal responsibility × conditional candidate weight ≥0.5 in at least two earlier panel scans. The original q020 training weights are unchanged. All target tracks remain in the means, including zeros. Full-corpus raw support cannot be substituted for these weighted results.",
        "",
        "![Catalogue recurrence and weighted panel support](recurrence.png)",
        "",
        f"Verified {len(rosters)} exact snapshot rosters, {len(scans)} recordings and {len(tracks)} bank-eligible tracks. Independent raw TLE-line extraction matches the public parser roster and debris exclusions for every snapshot. Candidate mappings and every support count/mass were reconstructed and execution/input hashes verified. The auditor does not verify physical signal identity or independently reproduce the radio likelihood.",
        "",
        "[Protocol](PROTOCOL.md), [summary](summary.json), [explicit rosters](rosters.json), [runtime provenance](runtime.json), [all records](result.json), [evidence](evidence-sha256.json).",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout="constrained")
    labels = ["One scan", "Two scans", "Three or more"]
    counts = [
        histogram.get(1, 0),
        histogram.get(2, 0),
        sum(v for k, v in histogram.items() if k >= 3),
    ]
    axes[0].bar(labels, counts)
    axes[0].set_ylabel("Distinct physical catalogue candidates")
    axes[0].set_title("Raw bank recurrence across 258 scans")
    for i, v in enumerate(counts):
        axes[0].text(i, v, str(v), ha="center", va="bottom")
    x = np.arange(3)
    for i, outside in enumerate((False, True)):
        values = [
            100 * r["mean_strong_mass"] for r in panel_aggregates if r["outside_panel"] == outside
        ]
        axes[1].bar(
            x + (i - 0.5) * 0.35,
            values,
            0.35,
            label="Outside panel" if outside else "Any earlier scan",
        )
    axes[1].set_xticks(x, ["DS7", "DS8", "DS9"])
    axes[1].set_ylabel("Mean conditional mass (%)")
    axes[1].set_title("Strong two-donor support: original 72 scans")
    axes[1].legend()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("recurrence." + suffix), dpi=160)
    plt.close(fig)
    print(summary, flush=True)


if __name__ == "__main__":
    main()
