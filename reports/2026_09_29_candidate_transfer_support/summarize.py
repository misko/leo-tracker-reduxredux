"""Independent set-index reconstruction of cross-record candidate support."""
# ruff: noqa: E501 -- Markdown prose and tables.

from collections import defaultdict

import matplotlib
import numpy as np
from study import HERE, read, save, verify

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main():
    assert read(HERE / "exit.json")["exit_code"] == 0
    bindings = read(HERE / "seal.json")["sha256"]
    verify(bindings)
    result = read(HERE / "result.json")
    scans = result["scans"]
    rows = result["rows"]
    index = defaultdict(set)
    strong = defaultdict(set)
    byscan = {s["session_id"]: s for s in scans}
    tracks = {}
    for scan in scans:
        for t in scan["tracks"]:
            tracks[scan["session_id"], t["track_id"]] = t
            for i, w in zip(t["ids"], t["weights"], strict=True):
                for receiver in (None, (t["receiver_id"], t["rf_hz"])):
                    key = (scan["snapshot"], scan["catalogue_size"], i, receiver)
                    index[key].add(scan["session_id"])
                    if w * t["signal_responsibility"] >= 0.5:
                        strong[key].add(scan["session_id"])
    assert len(scans) == len(byscan) == 72 and len(tracks) == 4328 and len(rows) == 4328 * 4
    assert len({(r["session_id"], r["track_id"], r["scope"], r["match"]) for r in rows}) == len(
        rows
    )
    for r in rows:
        s = byscan[r["session_id"]]
        t = tracks[r["session_id"], r["track_id"]]
        allowed = {
            a["session_id"]
            for a in scans
            if a["start_utc_ns"] < s["start_utc_ns"]
            and (a["snapshot"], a["catalogue_size"]) == (s["snapshot"], s["catalogue_size"])
            and (r["scope"] == "any_earlier_scan" or a["panel"] != s["panel"])
        }
        assert len(allowed) == r["compatible_donor_scans"]
        receiver = None if r["match"] == "any_receiver_rf" else (t["receiver_id"], t["rf_hz"])
        goodraw = set()
        goodstrong = set()
        for i in t["ids"]:
            key = (s["snapshot"], s["catalogue_size"], i, receiver)
            if len(index[key] & allowed) >= 2:
                goodraw.add(i)
            if len(strong[key] & allowed) >= 2:
                goodstrong.add(i)
        for field, supported in (
            ("raw_two_scan_mass", goodraw),
            ("strong_two_scan_mass", goodstrong),
        ):
            mass = sum(w for i, w in zip(t["ids"], t["weights"], strict=True) if i in supported)
            assert abs(mass - r[field]) < 1e-12
        maximum = max(t["weights"])
        chosen = min(i for i, w in zip(t["ids"], t["weights"], strict=True) if w == maximum)
        assert r["map_has_two_strong_scans"] == (chosen in goodstrong)
        assert r["target_signal_responsibility"] == t["signal_responsibility"]
    aggregates = []
    for dataset in ("DS7", "DS8", "DS9"):
        for scope in ("any_earlier_scan", "earlier_other_panel"):
            for match in ("any_receiver_rf", "same_receiver_rf"):
                rr = [
                    r
                    for r in rows
                    if r["dataset"] == dataset and r["scope"] == scope and r["match"] == match
                ]
                aggregates.append(
                    dict(
                        dataset=dataset,
                        scope=scope,
                        match=match,
                        tracks=len(rr),
                        scans=len({r["session_id"] for r in rr}),
                        scans_with_two_donors=len(
                            {r["session_id"] for r in rr if r["compatible_donor_scans"] >= 2}
                        ),
                        mean_raw_mass=float(np.mean([r["raw_two_scan_mass"] for r in rr])),
                        mean_strong_mass=float(np.mean([r["strong_two_scan_mass"] for r in rr])),
                        map_supported=sum(r["map_has_two_strong_scans"] for r in rr),
                        strong_mass_over_half=sum(r["strong_two_scan_mass"] > 0.5 for r in rr),
                    )
                )
    rosters = defaultdict(list)
    for s in scans:
        rosters[s["snapshot"], s["catalogue_size"]].append(s)
    roster_rows = [
        dict(
            snapshot=k[0], catalogue_size=k[1], scans=len(v), panels=sorted({s["panel"] for s in v})
        )
        for k, v in rosters.items()
    ]
    save(HERE / "summary.json", dict(audit_passed=True, aggregates=aggregates, rosters=roster_rows))
    lines = [
        "# Same-roster candidate support across earlier recordings",
        "",
        "This census measures available donor support; it fits no correction and produces no new accuracy estimate. All 4,328 tracks and 72 distinct scans remain in denominators. Different snapshots are not joined by row number.",
        "",
        "| Dataset | Scope | Receiver/RF restriction | Tracks | Scans with ≥2 compatible donors /24 | Mean raw supported mass | Mean strong supported mass | MAP supported tracks |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for a in aggregates:
        lines.append(
            f"| {a['dataset']} | {a['scope']} | {a['match']} | {a['tracks']} | {a['scans_with_two_donors']}/24 | {100 * a['mean_raw_mass']:.2f}% | {100 * a['mean_strong_mass']:.2f}% | {a['map_supported']} |"
        )
    lines += [
        "",
        "Raw support means membership in at least two earlier donor scans. Strong support additionally requires signal responsibility × conditional candidate weight ≥0.5 in each of at least two donor scans. Mass is averaged across target tracks with zero support included; it is conditional candidate mass, not correctness probability. Compatible donor counts precede receiver/RF filtering and do not imply track support.",
        "",
        "![Conditional target mass with strong donor support](support.png)",
        "",
        "| Snapshot digest suffix | Catalogue size | Scans | Panels |",
        "|---|---:|---:|---|",
    ]
    for r in roster_rows:
        lines.append(
            f"| {r['snapshot'][-12:]} | {r['catalogue_size']} | {r['scans']} | {', '.join(r['panels'])} |"
        )
    lines += [
        "",
        "The bank exporter preserves baseline row ordering when replacing orbital elements. Same-snapshot row equality is catalogue identity under that export contract, not verified detection identity. Provider-source changes are retained in the scan rows and do not change the baseline roster key. No cross-snapshot physical identity mapping or new archive query was attempted.",
        "",
        "Within-panel distributions share training-fitted geometry. Support there cannot serve as independent correction validation. Other-panel donors remove this shared-fit dependence but do not make this previously explored site blind. All candidate weights use the original eight-scan q020 fits.",
        "",
        "Six prelaunch synthetic tests passed. The independent auditor builds inverted candidate-to-record sets and reconstructs every support mass, MAP support flag and denominator. Execution/input hashes pass. This audit verifies exported support, not physical identities or the radio likelihood.",
        "",
        "[Protocol](PROTOCOL.md), [summary](summary.json), [full records and support](result.json), [tests](tests.log), [evidence hashes](evidence-sha256.json).",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
    x = np.arange(3)
    for j, (scope, match) in enumerate(
        (
            ("any_earlier_scan", "any_receiver_rf"),
            ("any_earlier_scan", "same_receiver_rf"),
            ("earlier_other_panel", "any_receiver_rf"),
            ("earlier_other_panel", "same_receiver_rf"),
        )
    ):
        vals = [
            100
            * next(
                a["mean_strong_mass"]
                for a in aggregates
                if (a["dataset"], a["scope"], a["match"]) == (ds, scope, match)
            )
            for ds in ("DS7", "DS8", "DS9")
        ]
        label = (
            ("Any earlier scan" if scope == "any_earlier_scan" else "Earlier other panel")
            + "; "
            + ("any RX/RF" if match == "any_receiver_rf" else "same RX/RF")
        )
        ax.bar(x + (j - 1.5) * 0.19, vals, width=0.19, label=label)
    ax.set_xticks(x, ["DS7", "DS8", "DS9"])
    ax.set_ylabel("Mean conditional candidate mass (%)")
    ax.set_title("Support from ≥2 earlier scans with donor signal × candidate weight ≥0.5")
    ax.legend(fontsize=8)
    ax.set_ylim(0, 100)
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("support." + suffix), dpi=160)
    plt.close(fig)
    print(aggregates, flush=True)


if __name__ == "__main__":
    main()
