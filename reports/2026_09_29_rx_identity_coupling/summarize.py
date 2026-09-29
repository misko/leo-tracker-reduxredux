"""Explicit assignment enumeration independently audits mixture scores."""

import math

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from study import HERE, ROOT, read, save, verify  # noqa: E402


def lse(values):
    top = max(values)
    return top + math.log(math.fsum(math.exp(v - top) for v in values))


def single(t):
    return lse(
        [math.log(0.8 / len(t["ids"])) + v for v in t["signal"]] + [math.log(0.2) + t["background"]]
    )


def pair(a, b, rho):
    pa = dict(zip(a["ids"], a["signal"], strict=True))
    pb = dict(zip(b["ids"], b["signal"], strict=True))
    common = pa.keys() & pb.keys()
    values = []
    if rho < 1:
        weight = math.log(0.64 * (1 - rho) / (len(pa) * len(pb)))
        values += [weight + x + y for x in pa.values() for y in pb.values()]
    if rho and common:
        weight = math.log(0.64 * rho / len(common))
        values += [weight + pa[k] + pb[k] for k in sorted(common)]
    values += [math.log(0.16 / len(pa)) + x + b["background"] for x in pa.values()]
    values += [math.log(0.16 / len(pb)) + y + a["background"] for y in pb.values()]
    values += [
        math.log(0.04 + (0.64 * rho if not common else 0)) + a["background"] + b["background"]
    ]
    return lse(values)


def main():
    plan = read(HERE / "plan.json")
    source = {s["session_id"]: s for s in read(ROOT / plan["pair_source"])["scans"]}
    bindings = read(HERE / "input-seal.json")["sha256"]
    rows = []
    for unit in plan["units"]:
        folder = HERE / "runs" / unit["unit_id"]
        assert read(folder / "exit.json")["exit_code"] == 0
        for n, h in read(folder / "seal.json")["sha256"].items():
            assert n not in bindings or bindings[n] == h
            bindings[n] = h
        result = read(folder / "result.json")
        assert result["audit_passed"]
        states = {
            mode: {(r["session_id"], r["track_id"]): r[mode] for r in result["potentials"]}
            for mode in ("train", "joint")
        }
        expected = {"all": [], "matched": [], "shuffled": []}
        for sid in unit["group"]["session_ids"]:
            for p in source[sid]["pairs"]:
                a, b = (sid, p["rx0"]), (sid, p["rx1"])
                expected["all"].append((a, b))
                if p["control_rx1"] is not None:
                    expected["matched"].append((a, b))
                    expected["shuffled"].append((a, (sid, p["control_rx1"])))
        for key, arm in result["arms"].items():
            population, value = key.rsplit("_", 1)
            rho = float(value)
            calculated = {}
            for mode, field in (("train", "training_pairs"), ("joint", "joint_pairs")):
                tracks = states[mode]
                pairs = [(tuple(r["left"]), tuple(r["right"])) for r in arm[field]]
                assert pairs == expected[population]
                flat = [i for p in pairs for i in p]
                assert len(flat) == len(set(flat)) == arm["paired_tracks"]
                assert len(tracks) - len(flat) == arm["unpaired_tracks"]
                pair_scores = []
                for (a, b), r in zip(pairs, arm[field], strict=True):
                    score = pair(tracks[a], tracks[b], rho)
                    assert abs(score - r["log_density"]) < 1e-8
                    assert abs(sum(r["prior_masses"]) - 1) < 1e-12
                    pair_scores.append(score)
                calculated[mode] = math.fsum(
                    pair_scores + [single(t) for k, t in tracks.items() if k not in set(flat)]
                )
            assert abs(calculated["train"] - arm["training_log_score"]) < 1e-7
            assert abs(calculated["joint"] - calculated["train"] - arm["held_log_score"]) < 1e-7
        base = result["arms"]["all_0"]["held_log_score"]
        rows.append(
            dict(
                unit_id=unit["unit_id"],
                primary={
                    str(rho): result["arms"][f"all_{rho}"]["held_log_score"] - base
                    for rho in plan["couplings"]
                },
                matched={
                    str(rho): result["arms"][f"matched_{rho}"]["held_log_score"] - base
                    for rho in plan["couplings"]
                },
                shuffled={
                    str(rho): result["arms"][f"shuffled_{rho}"]["held_log_score"] - base
                    for rho in plan["couplings"]
                },
            )
        )
    verify(bindings)
    totals = {}
    for rho in ("0.5", "1"):
        actual = [r["primary"][rho] for r in rows]
        control = [r["matched"][rho] - r["shuffled"][rho] for r in rows]
        totals[rho] = dict(
            primary_better=sum(v > 1e-7 for v in actual),
            primary_tied=sum(abs(v) <= 1e-7 for v in actual),
            primary_median_delta=float(np.median(actual)),
            control_better=sum(v > 1e-7 for v in control),
            control_median_delta=float(np.median(control)),
        )
    save(HERE / "summary.json", dict(audit_passed=True, rows=rows, totals=totals))
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), layout="constrained", sharex=True)
    x = np.arange(len(rows))
    for j, rho in enumerate(("0.5", "1")):
        axes[0].bar(
            x + (j - 0.5) * 0.35,
            [r["primary"][rho] for r in rows],
            width=0.35,
            label="coupling " + rho,
        )
        axes[1].bar(
            x + (j - 0.5) * 0.35,
            [r["matched"][rho] - r["shuffled"][rho] for r in rows],
            width=0.35,
            label="coupling " + rho,
        )
    axes[0].set_ylabel("Held Δnats vs independent")
    axes[1].set_ylabel("Matched selected − shuffled Δnats")
    for ax in axes:
        ax.axhline(0, color="black", linewidth=0.7)
        ax.legend()
    axes[1].set_xticks(x, [r["unit_id"].replace("_", " ") for r in rows], rotation=65, ha="right")
    fig.suptitle("Uncertain shared identity at unchanged locations — no geographic fit")
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("comparison." + suffix), dpi=160)
    plt.close(fig)
    print(totals)


if __name__ == "__main__":
    main()
