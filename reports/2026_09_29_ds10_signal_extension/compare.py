"""Qualified joint-corpus region correlations, words, and exact-track orbit candidates."""

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from extend import OUT, PRIOR, sha, write  # noqa: E402

sys.path.insert(0, str(PRIOR))
from cluster_tracks import mean_phase, normalized_phase_features  # noqa: E402

REGIONS = [(0, 6), (6, 32), (32, 128), (128, 192)]


def time_bin(seconds):
    return 0 if seconds < 600 else 1 if seconds < 7200 else 2


def summarize(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return dict(n=0)
    return dict(n=len(values), mean=float(values.mean()),
                quantiles=np.quantile(values, [.05, .5, .95]).tolist())


def metadata(c, r, label):
    track = c["tracks"][r["index"]]
    assert track["track_id"] == r["track_id"]
    meta = r["receiver_metadata"]
    ev = meta["evaluation_frames"]
    q = min(meta["diagnostics"][f]["held_pilot_coherence"] for f in ev)
    visit_times = [t for v, t in zip(track["visits"], track["times_s"], strict=True)
                   if v == r["visit"]]
    return dict(
        id=f"{c['unit']}-T{r['index']:04d}", unit=c["unit"], dataset=c["dataset"],
        session=c["session"], track_id=r["track_id"], receiver=r["receiver"],
        rate=c["rate"], edge=r["edge"], channel=r["channel"], pilot=q,
        visit=r["visit"], selected_utc_ns=c["start_utc_ns"] + round(visit_times[0] * 1e9),
        norad_id=label.get("norad_id"), tier=label.get("tier", "unlabeled"),
        physical_group=label.get("physical_group"), satellite_name=label.get("satellite_name"),
        source_artifact=r["artifact"], source_artifact_sha256=r["artifact_sha256"],
        cfo_hz=r["candidate"]["fractional_tracking_cfo_hz"],
        rf_hz=r["actual_rf_hz"], span_s=r["span_s"],
        known_tail_states=sorted({w["known_phase"] for w in r["words"]
                                 if w["accepted"] and w["known_phase"] is not None}),
    )


def build():
    census = json.loads((OUT / "census.json").read_text())
    archived = json.loads((OUT / "associations.json").read_text())
    labels = {(r["session"], r["track_id"]): r for r in archived["rows"]}
    bridge_plan = json.loads((OUT / "bridge-plan.json").read_text())
    for unit in bridge_plan["targets"]:
        bridge = json.loads((OUT / "bridges" / (unit + ".json")).read_text())
        for mapping in bridge["mappings"]:
            label = labels.get((bridge["session"], mapping["production_track_id"]))
            if label:
                assert label["source_sha256"] == bridge["source_sha256"]
                labels[bridge["session"], mapping["census_track_id"]] = label
    for r in json.loads((PRIOR / "local/clustering.json").read_text())["tracks"]:
        if r["dataset"] == "DS7" and r["norad_id"] is not None:
            labels[r["session"], r["track_id"]] = dict(
                norad_id=r["norad_id"], satellite_name=r["satellite_name"],
                tier="legacy_conditional", capture_manifest=None, analysis_manifest=None,
            )
    for r in json.loads((PRIOR / "local/bound-ds8-labels/summary.json").read_text())["bound"]:
        labels[r["session"], r["track_id"]] = dict(
            norad_id=r["norad_id"], satellite_name=r["satellite_name"],
            tier="legacy_conditional", capture_manifest=None, analysis_manifest=None,
        )
    rows, features, counts, novelty, bindings = [], defaultdict(list), Counter(), [], {}
    words_by_dataset = defaultdict(Counter)
    for c in census["captures"]:
        receipt = OUT / "decoded" / c["unit"] / "results.json"
        windows = receipt.with_name("windows.json")
        bindings[str(receipt)] = sha(receipt)
        bindings[str(windows)] = sha(windows)
        result = json.loads(receipt.read_text())
        wr = json.loads(windows.read_text())
        assert wr["source_sha256"] == hashlib.sha256(receipt.read_bytes()).hexdigest()
        by_index = {r["index"]: r["windows"] for r in wr["rows"]}
        assert len(result["rows"]) == len(c["tracks"])
        for r in result["rows"]:
            counts[c["dataset"], r["status"]] += 1
            for w in by_index[r["index"]]:
                if w["accepted"]:
                    words_by_dataset[c["dataset"]][w["word"]] += 1
                    if w["known_phase"] is None:
                        novelty.append(dict(id=f"{c['unit']}-T{r['index']:04d}",
                                            dataset=c["dataset"], status=r["status"], **w))
            if r["status"] != "qualified":
                continue
            label = labels.get((c["session"], r["track_id"]), {})
            if label.get("capture_manifest"):
                assert label["capture_manifest"] == c["capture_manifest"]
                assert label["analysis_manifest"] == c["analysis_manifest"]
            info = metadata(c, r, label)
            path = Path(r["artifact"])
            assert hashlib.sha256(path.read_bytes()).hexdigest() == r["artifact_sha256"]
            with np.load(path) as data:
                bins = data["bins"]
                core = [486, 487, 496, 497] if r["edge"] == "upper" else [526, 527, 536, 537]
                assert np.isin(core, bins).all()
                assert not np.isin(core, r["receiver_metadata"]["pilot_bins"]).any()
                z = data["z"][r["receiver_metadata"]["evaluation_frames"]]
                z = z[:, :, np.searchsorted(bins, core)]
                for ri, (start, stop) in enumerate(REGIONS):
                    features[ri].append(mean_phase(z[:, start:stop]))
            info["accepted_window_words"] = [w["word"] for w in by_index[r["index"]]
                                              if w["accepted"]]
            rows.append(info)
    arrays = {f"region{i}": normalized_phase_features(features[i]) for i in range(4)}
    np.savez_compressed(OUT / "qualified-features.npz", **arrays)
    write(OUT / "qualified-tracks.json", rows)
    write(OUT / "word-comparison.json", dict(
        counts={str(k): v for k, v in counts.items()},
        words_by_dataset={k: dict(v) for k, v in words_by_dataset.items()}, novelty=novelty,
        source_sha256=bindings, method_sha256=sha(Path(__file__)),
    ))
    return rows, arrays


def unique_visits(rows):
    """Retain strongest exact observation, never choose by measured correlation."""
    best = {}
    for i, r in enumerate(rows):
        key = (r["session"], r["visit"], r["receiver"], r["channel"], r["edge"])
        if key not in best or r["pilot"] > rows[best[key]]["pilot"]:
            best[key] = i
    return sorted(best.values())


def compare_pairs(rows, arrays):
    keep = unique_visits(rows)
    correlations = np.stack([arrays[f"region{i}"] @ arrays[f"region{i}"].T for i in range(4)])
    np.savez_compressed(OUT / "region-correlations.npz", correlations=correlations)
    groups = defaultdict(list)
    for i in keep:
        r = rows[i]
        groups[r["edge"], r["channel"]].append(i)
    pairs = []
    for group in groups.values():
        for ai, i in enumerate(group):
            a = rows[i]
            for j in group[ai + 1:]:
                b = rows[j]
                delta = abs(a["selected_utc_ns"] - b["selected_utc_ns"]) / 1e9
                if a["session"] == b["session"] and a["visit"] == b["visit"]:
                    continue
                labeled = a["norad_id"] is not None and b["norad_id"] is not None
                sa, sb = set(a["known_tail_states"]), set(b["known_tail_states"])
                pairs.append(dict(
                    i=i, j=j, left=a["id"], right=b["id"], separation_s=delta,
                    receiver_pair=sorted([a["receiver"], b["receiver"]]),
                    rate_pair=sorted([a["rate"], b["rate"]]),
                    time_bin=time_bin(delta), cross_session=a["session"] != b["session"],
                    includes_ds10=a["dataset"] == "DS10" or b["dataset"] == "DS10",
                    same_id=(a["norad_id"] == b["norad_id"]) if labeled else None,
                    both_control_supported=all(r["tier"] == "control_supported_candidate"
                                               for r in (a, b)),
                    both_production=all(r["tier"] in (
                        "heldout_candidate", "control_supported_candidate") for r in (a, b)),
                    shared_tail_state=bool(sa & sb) if sa and sb else None,
                    correlations=correlations[:, i, j].tolist(),
                ))
    summaries, repeats = [], []
    for tier in ["all_candidates", "production_candidates", "control_supported"]:
        for scope in ["within_session", "cross_session", "separated_30min"]:
            chosen = [p for p in pairs if p["includes_ds10"] and p["same_id"] is not None
                      and (tier == "all_candidates" or
                           (p["both_production"] if tier == "production_candidates"
                            else p["both_control_supported"]))
                      and ((not p["cross_session"]) if scope == "within_session" else
                           (p["cross_session"] if scope == "cross_session"
                            else p["separation_s"] >= 1800))]
            same = [p for p in chosen if p["same_id"]]
            other = [p for p in chosen if not p["same_id"]]
            summaries.append(dict(
                tier=tier, scope=scope,
                same=[summarize([p["correlations"][r] for p in same]) for r in range(4)],
                different=[summarize([p["correlations"][r] for p in other]) for r in range(4)],
            ))
    for p in pairs:
        if p["same_id"] is not True or not p["includes_ds10"]:
            continue
        a, b = rows[p["i"]], rows[p["j"]]
        # Same instrument/edge/channel/rate/RX and separation bin; control shares an endpoint.
        controls = [q for q in pairs if q["same_id"] is False
                    and q["receiver_pair"] == p["receiver_pair"]
                    and q["rate_pair"] == p["rate_pair"]
                    and q["time_bin"] == p["time_bin"]
                    and q["cross_session"] == p["cross_session"]
                    and ({q["i"], q["j"]} & {p["i"], p["j"]})]
        repeats.append(dict(
            **p, norad_id=a["norad_id"], tiers=[a["tier"], b["tier"]],
            endpoint_control_n=len(controls),
            endpoint_control_summaries=[summarize([q["correlations"][r] for q in controls])
                                        for r in range(4)],
            early_control_percentile=float(np.mean(
                [q["correlations"][0] < p["correlations"][0] for q in controls]
            )) if controls else None,
        ))
    state_summaries = []
    for cross in [False, True]:
        relevant = [p for p in pairs if p["includes_ds10"] and p["cross_session"] == cross
                    and p["shared_tail_state"] is not None]
        state_summaries.append(dict(
            cross_session=cross,
            same=[summarize([p["correlations"][r] for p in relevant if p["shared_tail_state"]])
                  for r in range(4)],
            different=[summarize([p["correlations"][r] for p in relevant
                                 if not p["shared_tail_state"]]) for r in range(4)],
        ))
    by_satellite = defaultdict(list)
    for i in keep:
        if rows[i]["norad_id"] is not None:
            by_satellite[rows[i]["norad_id"]].append(rows[i])
    satellites = []
    for norad, rr in by_satellite.items():
        if not any(r["dataset"] == "DS10" for r in rr):
            continue
        satellites.append(dict(
            norad_id=norad, qualified_entries=len(rr),
            unique_visits=len({(r["session"], r["visit"]) for r in rr}),
            sessions=len({r["session"] for r in rr}),
            datasets=dict(Counter(r["dataset"] for r in rr)),
            tiers=dict(Counter(r["tier"] for r in rr)),
            earliest_ns=min(r["selected_utc_ns"] for r in rr),
            latest_ns=max(r["selected_utc_ns"] for r in rr), ids=[r["id"] for r in rr],
        ))
    write(OUT / "correlation-summary.json", dict(
        unique_qualified_entries=len(keep), total_qualified_entries=len(rows),
        regions=REGIONS, summaries=summaries, repeats=repeats,
        state_summaries=state_summaries,
        satellites=sorted(satellites, key=lambda r: (-r["sessions"], -r["unique_visits"])),
        pair_count=len(pairs), method_sha256=sha(Path(__file__)),
        limitation="Conditional IDs; no satellite identity decoded. Pairs are dependent. "
        "No phase/lag search. Four physical data carriers; two evaluation frames. "
        "Same state means intersection of accepted tail-state sets, not whole-frame equality.",
    ))
    write(OUT / "matched-pairs.json", pairs)
    return correlations


def plots(rows, arrays, correlations):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.cluster.hierarchy import leaves_list, linkage
    from scipy.spatial.distance import pdist

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), layout="constrained")
    for ax, edge in zip(axes, ["upper", "lower"], strict=True):
        ix = np.array([i for i, r in enumerate(rows) if r["edge"] == edge])
        tree = linkage(pdist(arrays["region0"][ix]), method="average")
        order = ix[leaves_list(tree)]
        np.save(OUT / f"{edge}-early-linkage.npy", tree)
        write(OUT / f"{edge}-early-order.json", [rows[i]["id"] for i in order])
        im = ax.imshow(correlations[0][np.ix_(order, order)], vmin=-1, vmax=1,
                       cmap="RdBu_r", interpolation="nearest")
        ax.set(title=f"{edge.title()} edge: {len(ix)} qualified tracks",
               xlabel="Ordered receiver tracks", ylabel="Ordered receiver tracks")
    fig.colorbar(im, ax=axes, label="Early-region normalized phase correlation", shrink=.75)
    fig.suptitle("DS7–DS10: symbols 2–7, four common carriers\n"
                 "Average linkage; one cell per pair; candidate identity not used")
    fig.savefig(OUT / "joint-early-correlations.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    rows, arrays = build()
    correlations = compare_pairs(rows, arrays)
    plots(rows, arrays, correlations)
    print("Compared", len(rows), "qualified receiver tracks", flush=True)
