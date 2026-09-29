"""Audit donor fits and reconstruct target support from independent groups."""
# ruff: noqa: E501 -- Markdown prose and tables.

import math
from collections import defaultdict
from pathlib import Path

import matplotlib
import numpy as np
from study import HERE, RECURRENCE, read, save, verify

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def main():
    plan = read(HERE / "plan.json")
    bindings = read(HERE / "input-seal.json")["sha256"]
    rec = read(RECURRENCE / "result.json")
    full = {s["session_id"]: s for s in rec["scans"]}
    targets = read(HERE.parent / "2026_09_29_candidate_transfer_support/result.json")["scans"]
    excluded = {s["session_id"] for s in targets}
    seen = set()
    strong = defaultdict(set)
    group_rows = []
    ends = {}
    for u in plan["units"]:
        folder = HERE / "runs" / u["unit_id"]
        assert read(folder / "exit.json")["exit_code"] == 0
        for n, h in read(folder / "seal.json")["sha256"].items():
            assert n not in bindings or bindings[n] == h
            bindings[n] = h
        r = read(folder / "result.json")
        sids = u["group"]["session_ids"]
        assert r["session_ids"] == sids and not seen & set(sids) and not excluded & set(sids)
        seen.update(sids)
        end = 0
        for item in u["group"]["inputs"]:
            obs = read(
                Path(next(a["path"] for a in item["artifacts"] if a["kind"] == "observations"))
            )
            end = max(
                end,
                obs["start_utc_ns"]
                + math.ceil(max(max(t["times_s"]) for t in obs["tracks"]) * 1e9),
            )
        assert end == u["available_utc_ns"] == r["available_utc_ns"]
        ends[u["unit_id"]] = end
        assert len(r["starts"]) == 3
        eligible = []
        for initial_xy, fit in zip(
            ([0.0, 0.0], [3.0, -3.0], [-3.0, 3.0]), r["starts"], strict=True
        ):
            assert fit["initial"] == initial_xy + [0.0] * len(sids)
            if "error" in fit:
                assert not fit["qualified"] and fit["traceback"]
                continue
            limits = [12, 12] + [5] * len(sids)
            boundary = any(
                limit - abs(v) < 0.001 for limit, v in zip(limits, fit["x"], strict=True)
            )
            assert boundary == fit["boundary"]
            assert len(fit["checks"]) == 2 * len(fit["x"])
            agreement = []
            for axis in range(len(fit["x"])):
                pair = fit["checks"][axis * 2 : axis * 2 + 2]
                assert [c["step"] for c in pair] == (
                    [0.0005, 0.00025] if axis < 2 else [0.0000625, 0.00003125]
                )
                for c in pair:
                    assert c["axis"] == axis
                    assert (
                        abs(c["difference"] - abs(c["numerical"] - fit["gradient"][axis])) < 1e-12
                    )
                    z = fit["x"][axis]
                    step = c["step"]
                    assert c["crosses_node"] == (
                        axis >= 2 and math.floor((z - step) * 4) != math.floor((z + step) * 4)
                    )
                agreement.append(abs(pair[0]["numerical"] - pair[1]["numerical"]))
            assert agreement == fit["step_agreement"]
            qualified = (
                fit["success"]
                and not boundary
                and max(map(abs, fit["gradient"])) <= 0.01
                and all(c["difference"] < 0.002 and not c["crosses_node"] for c in fit["checks"])
                and max(agreement) < 0.002
            )
            assert qualified == fit["qualified"]
            if qualified:
                eligible.append(fit)
        selected = max(eligible, key=lambda f: f["score"]) if eligible else None
        assert selected == r["selected"]
        expected = {(sid, t["track_id"]): t for sid in sids for t in full[sid]["tracks"]}
        if selected:
            assert len(r["rows"]) == len(expected)
            assert {(t["session_id"], t["track_id"]) for t in r["rows"]} == set(expected)
            assert abs(sum(t["training_log_score"] for t in r["rows"]) - selected["score"]) < 1e-7
            for t in r["rows"]:
                numbers = expected[t["session_id"], t["track_id"]]["numbers"]
                weights = t["weights_given_signal"]
                assert (
                    len(numbers) == len(weights)
                    and min(weights) >= 0
                    and abs(sum(weights) - 1) < 1e-8
                )
                assert 0 <= t["signal_responsibility"] <= 1
                for n, w in zip(numbers, weights, strict=True):
                    if w * t["signal_responsibility"] >= 0.5:
                        strong[n].add(u["unit_id"])
        else:
            assert r["rows"] == []
        group_rows.append(
            dict(
                unit_id=u["unit_id"],
                scans=len(sids),
                qualified_starts=len(eligible),
                selected_start=selected["name"] if selected else None,
                exported_tracks=len(r["rows"]),
                available_utc_ns=end,
            )
        )
    assert len(seen) == 186 and seen | excluded == set(full)
    verify(bindings)
    rows = []
    for s in targets:
        mapped = {t["track_id"]: t for t in full[s["session_id"]]["tracks"]}
        available = {g for g, end in ends.items() if end < s["start_utc_ns"]}
        for t in s["tracks"]:
            base = mapped[t["track_id"]]
            assert t["ids"] == base["ids"]
            numbers = base["numbers"]
            weights = t["weights"]
            counts = [len(strong[n] & available) for n in numbers]
            map_slot = min(range(len(numbers)), key=lambda i: (-weights[i], numbers[i]))
            rows.append(
                dict(
                    dataset=s["panel"][:3],
                    panel=s["panel"],
                    session_id=s["session_id"],
                    track_id=t["track_id"],
                    available_groups=len(available),
                    one_group_mass=sum(w for w, c in zip(weights, counts, strict=True) if c >= 1),
                    two_group_mass=sum(w for w, c in zip(weights, counts, strict=True) if c >= 2),
                    target_signal_responsibility=t["signal_responsibility"],
                    map_two_groups=counts[map_slot] >= 2,
                )
            )
    aggregates = []
    for ds in ("DS7", "DS8", "DS9"):
        rr = [r for r in rows if r["dataset"] == ds]
        aggregates.append(
            dict(
                dataset=ds,
                tracks=len(rr),
                mean_one_group_mass=float(np.mean([r["one_group_mass"] for r in rr])),
                mean_two_group_mass=float(np.mean([r["two_group_mass"] for r in rr])),
                mean_signal_times_two_mass=float(
                    np.mean([r["two_group_mass"] * r["target_signal_responsibility"] for r in rr])
                ),
                two_mass_over_half=sum(r["two_group_mass"] > 0.5 for r in rr),
                map_two_groups=sum(r["map_two_groups"] for r in rr),
            )
        )
    save(
        HERE / "summary.json",
        dict(audit_passed=True, groups=group_rows, aggregates=aggregates, rows=rows),
    )
    lines = [
        "# Training-weighted support from target-disjoint donor groups",
        "",
        "All 72 target scans are excluded from donor fitting. Donor groups become available only after their last observation. Target distributions remain the original eight-scan q020 fits; no held outcome or reference error selected starts or groups.",
        "",
        "| Target dataset | Tracks | Mean one-group mass | Mean two-group mass | Mean target signal × two-group mass | Tracks with two-group mass >0.5 | MAP with two groups |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for a in aggregates:
        lines.append(
            f"| {a['dataset']} | {a['tracks']} | {100 * a['mean_one_group_mass']:.3f}% | {100 * a['mean_two_group_mass']:.3f}% | {100 * a['mean_signal_times_two_mass']:.3f}% | {a['two_mass_over_half']} | {a['map_two_groups']} |"
        )
    lines += [
        "",
        "Strong group support requires signal responsibility × conditional candidate weight ≥0.5 in at least one donor track in that group. Two-group support counts distinct fitted groups, not multiple tracks sharing geometry. These descriptive masses are not identity confidence or calibrated probabilities.",
        "",
        "| Donor group | Scans | Qualified starts /3 | Training-selected start | Exported tracks |",
        "|---|---:|---:|---|---:|",
    ]
    for g in group_rows:
        lines.append(
            f"| {g['unit_id']} | {g['scans']} | {g['qualified_starts']} | {g['selected_start']} | {g['exported_tracks']} |"
        )
    lines += [
        "",
        "![Target candidate support from independent donor groups](support.png)",
        "",
        "The auditor verifies hashes, disjoint recording coverage, group availability, optimizer/audit qualifications, training-only selection, row score sums and weight normalization before mapping candidates and aggregating support. It is not an independent radio-likelihood implementation or satellite-identity verifier. No residual correction or new geographic accuracy result is produced.",
        "",
        "[Protocol](PROTOCOL.md), [complete summary](summary.json), [group tests](tests.log), [optimizer tests](optimizer-tests.log), [evidence](evidence-sha256.json).",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
    x = np.arange(3)
    for j, (field, label) in enumerate(
        (("mean_one_group_mass", "One donor group"), ("mean_two_group_mass", "Two donor groups"))
    ):
        values = [100 * a[field] for a in aggregates]
        ax.bar(x + (j - 0.5) * 0.35, values, 0.35, label=label)
        for pos, v in zip(x + (j - 0.5) * 0.35, values, strict=True):
            ax.text(pos, v, f"{v:.2f}%", ha="center", va="bottom")
    ax.set_xticks(x, ["DS7", "DS8", "DS9"])
    ax.set_ylabel("Mean conditional target candidate mass (%)")
    ax.set_title("Donor-only q020 fits; strictly prior group availability")
    ax.legend()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("support." + suffix), dpi=160)
    plt.close(fig)
    print(group_rows, aggregates, flush=True)


if __name__ == "__main__":
    main()
