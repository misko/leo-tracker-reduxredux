"""Reconstruct matching and selection, audit held scores, and report the full census."""
# ruff: noqa: E501 -- Markdown tables and prose.

import math
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from study import HERE, ROOT, read, save, verify


def density(r, s):
    r = np.asarray(r)
    return (
        math.lgamma(2.5)
        - math.lgamma(2)
        - 0.5 * math.log(4 * math.pi * s * s)
        - 2.5 * np.log1p(r * r / (4 * s * s))
    )


def main():
    bindings = read(HERE / "seal.json")["sha256"]
    verify(bindings)
    assert int((HERE / "exit-code.txt").read_text()) == 0
    result = read(HERE / "result.json")["scans"]
    plan = read(HERE / "plan.json")["units"]
    assert len(result) == len(plan) == 72
    for scan, unit in zip(result, plan, strict=True):
        assert all(scan[k] == v for k, v in unit.items())
        doc = read(ROOT / unit["observations"])
        tracks = {t["track_id"]: t for t in doc["tracks"]}
        assert scan["tracks"] == len(tracks)
        expected = {
            (a["track_id"], b["track_id"])
            for a in tracks.values()
            if a["receiver_id"] == 0
            for b in tracks.values()
            if b["receiver_id"] == 1 and a["channel"] == b["channel"] and a["rf_hz"] == b["rf_hz"]
        }
        assert len(expected) == len(scan["pairs"]) and expected == {
            (p["rx0"], p["rx1"]) for p in scan["pairs"]
        }
        for pair in scan["pairs"]:
            a, b = tracks[pair["rx0"]], tracks[pair["rx1"]]
            bv = {}
            for j, v in enumerate(b["visits"]):
                bv.setdefault(v, []).append(j)
            edges = [
                (i, j)
                for i, v in enumerate(a["visits"])
                for j in bv.get(v, [])
                if abs(a["times_s"][i] - b["times_s"][j]) <= 0.001
            ]
            left, right = Counter(i for i, j in edges), Counter(j for i, j in edges)
            unique = [(i, j) for i, j in edges if left[i] == right[j] == 1]
            assert unique == list(zip(pair["rx0_indices"], pair["rx1_indices"], strict=True))
            assert pair["ambiguous_edges"] == len(edges) - len(unique)
            assert pair["rx0_unmatched"] == len(a["times_s"]) - len(unique)
            assert pair["rx1_unmatched"] == len(b["times_s"]) - len(unique)
            i, j = pair["rx0_indices"], pair["rx1_indices"]
            t = np.asarray(a["times_s"])[i]
            y0 = np.asarray(a["measured_hz"])[i]
            y1 = np.asarray(b["measured_hz"])[j]
            ma, mb = np.asarray(a["training_mask"])[i], np.asarray(b["training_mask"])[j]
            train, held = ma & mb, ~ma & ~mb
            assert pair["training"] == train.tolist() and pair["held"] == held.tolist()
            assert (
                pair["times_s"] == t.tolist()
                and pair["rx0_hz"] == y0.tolist()
                and pair["rx1_hz"] == y1.tolist()
            )
            assert pair["difference_hz"] == (y0 - y1).tolist()
            assert pair["training_count"] == int(train.sum())
            span = float(np.ptp(t[train])) if train.any() else 0
            assert pair["training_span_s"] == span
            eligible = train.sum() >= 5 and span >= 5
            assert pair["eligible"] == bool(eligible)
            if eligible:
                offset = float(np.median((y0 - y1)[train]))
                r = (y0 - y1)[train] - offset
                assert offset == pair["offset_hz"]
                assert float(np.median(abs(r))) == pair["training_median_abs_hz"]
                assert float(np.quantile(abs(r), 0.9)) == pair["training_p90_abs_hz"]
                assert (
                    abs(
                        float(density(r, math.sqrt(20000)).mean())
                        - pair["training_mean_log_density"]
                    )
                    < 1e-12
                )
                assert pair["passes_shape"] == bool(
                    np.median(abs(r)) <= 100 and np.quantile(abs(r), 0.9) <= 300
                )
        chosen = []
        for p in scan["pairs"]:
            selected = p["eligible"] and p["passes_shape"]
            if p["eligible"]:
                for side in ("rx0", "rx1"):
                    peers = [
                        q
                        for q in scan["pairs"]
                        if q is not p and q["eligible"] and q[side] == p[side]
                    ]
                    margin = (
                        p["training_mean_log_density"]
                        - max(q["training_mean_log_density"] for q in peers)
                        if peers
                        else None
                    )
                    assert margin == p["margins_nats_per_observation"][side]
                    selected &= margin is None or margin >= 0.1
            assert bool(selected) == p["selected"]
            if selected:
                chosen.append(p)
        assert len({p["rx0"] for p in chosen}) == len({p["rx1"] for p in chosen}) == len(chosen)
        for p in chosen:
            e = p["evaluation"]
            held = np.array(p["held"], bool)
            train = np.array(p["training"], bool)
            t = np.array(p["times_s"])
            y0 = np.array(p["rx0_hz"])
            y1 = np.array(p["rx1_hz"])
            assert e["held_count"] == int(held.sum())
            span = float(np.ptp(t[held])) if held.any() else 0
            assert e["held_span_s"] == span and e["held_available"] == bool(
                held.sum() >= 3 and span >= 5
            )
            if not e["held_available"]:
                continue
            r = (y0 - y1)[held] - p["offset_hz"]
            actual = float(density(r, math.sqrt(20000)).sum())
            assert abs(actual - e["held_log_density"]) < 1e-9
            assert float(np.median(abs(r))) == e["held_median_abs_hz"]
            assert float(np.quantile(abs(r), 0.9)) == e["held_p90_abs_hz"]
            assert e["held_shape_pass"] == bool(
                np.median(abs(r)) <= 100 and np.quantile(abs(r), 0.9) <= 300
            )
            assert (
                abs(e["narrow_minus_broad_nats"] - (actual - float(density(r, 2000).sum()))) < 1e-9
            )
            reverse_offset = np.median(y0[train] - y1[train][::-1])
            reverse = y0[held] - y1[held][::-1] - reverse_offset
            assert (
                abs(
                    e["actual_minus_reversed_nats"]
                    - (actual - float(density(reverse, math.sqrt(20000)).sum()))
                )
                < 1e-9
            )
            donors = [
                q
                for q in chosen
                if q is not p and q["channel"] == p["channel"] and q["rf_hz"] == p["rf_hz"]
            ]
            assert e["donor_count"] == len(donors)
            if len(donors) >= 2:
                offset = float(np.median([q["offset_hz"] for q in donors]))
                r = (y0 - y1)[held] - offset
                assert e["donor_offset_hz"] == offset
                assert e["donor_held_median_abs_hz"] == float(np.median(abs(r)))
                assert e["donor_held_p90_abs_hz"] == float(np.quantile(abs(r), 0.9))
                assert e["donor_held_shape_pass"] == bool(
                    np.median(abs(r)) <= 100 and np.quantile(abs(r), 0.9) <= 300
                )
                assert (
                    abs(
                        e["donor_minus_own_nats"]
                        - (float(density(r, math.sqrt(20000)).sum()) - actual)
                    )
                    < 1e-9
                )
    aggregates = []
    for ds in ("DS7", "DS8", "DS9"):
        scans = [s for s in result if s["dataset"] == ds]
        assert len(scans) == 24
        pairs = [p for s in scans for p in s["pairs"]]
        chosen = [p for p in pairs if p["selected"]]
        held = [p["evaluation"] for p in chosen if p["evaluation"]["held_available"]]
        donor = [e for e in held if "donor_offset_hz" in e]
        aggregates.append(
            {
                "dataset": ds,
                "scans": len(scans),
                "tracks": sum(s["tracks"] for s in scans),
                "candidate_pairs": len(pairs),
                "matched_pairs": sum(bool(p["rx0_indices"]) for p in pairs),
                "eligible_pairs": sum(p["eligible"] for p in pairs),
                "training_shape_pairs": sum(p["passes_shape"] for p in pairs),
                "selected_pairs": len(chosen),
                "scans_with_selected_pairs": sum(
                    any(p["selected"] for p in s["pairs"]) for s in scans
                ),
                "held_available": len(held),
                "held_pass": sum(e["held_shape_pass"] for e in held),
                "narrow_better": sum(e["narrow_minus_broad_nats"] > 0 for e in held),
                "reverse_better": sum(e["actual_minus_reversed_nats"] > 0 for e in held),
                "donor_available": len(donor),
                "donor_pass": sum(e["donor_held_shape_pass"] for e in donor),
                "median_pair_held_abs_hz": float(np.median([e["held_median_abs_hz"] for e in held]))
                if held
                else None,
                "median_donor_held_abs_hz": float(
                    np.median([e["donor_held_median_abs_hz"] for e in donor])
                )
                if donor
                else None,
            }
        )
    save(HERE / "summary.json", {"audit_passed": True, "datasets": aggregates})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for i, key in enumerate(("eligible_pairs", "selected_pairs", "held_available", "held_pass")):
        axes[0].bar(
            np.arange(3) + (i - 1.5) * 0.2, [r[key] for r in aggregates], width=0.2, label=key
        )
    axes[0].set_xticks(range(3), ["DS7", "DS8", "DS9"])
    axes[0].set_ylabel("Track pairs")
    axes[0].legend(fontsize=8)
    for i, key in enumerate(("median_pair_held_abs_hz", "median_donor_held_abs_hz")):
        axes[1].bar(
            np.arange(3) + (i - 0.5) * 0.3,
            [r[key] for r in aggregates],
            width=0.3,
            label="Own pair offset" if i == 0 else "Other-pair offset",
        )
    axes[1].axhline(100, color="gray", linestyle="--", label="Median threshold")
    axes[1].set_xticks(range(3), ["DS7", "DS8", "DS9"])
    axes[1].set_ylabel("Median of pair held absolute-error medians (Hz)")
    axes[1].legend(fontsize=8)
    fig.suptitle("Cross-RX frequency agreement; identity and location are not evaluated")
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"coherence.{suffix}", dpi=160)
    plt.close(fig)
    print(aggregates, flush=True)


if __name__ == "__main__":
    main()
