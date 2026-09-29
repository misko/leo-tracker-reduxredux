"""Independent dictionary-based agreement audit and matched control summary."""

import math
from collections import defaultdict

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from study import HERE, ROOT, read, save, verify  # noqa: E402


def independent(a, b):
    assert a["snapshot"] == b["snapshot"] and a["catalogue_size"] == b["catalogue_size"]
    p, q = (
        dict(zip(a["ids"], a["weights"], strict=True)),
        dict(zip(b["ids"], b["weights"], strict=True)),
    )
    ids = sorted(p.keys() & q.keys())
    return dict(
        left_candidates=len(p),
        right_candidates=len(q),
        common_ids=ids,
        intersection=len(ids),
        left_common_mass=math.fsum(p[k] for k in ids),
        right_common_mass=math.fsum(q[k] for k in ids),
        agreement_mass=math.fsum(p[k] * q[k] for k in ids),
        left_map=min(p, key=lambda k: (-p[k], k)),
        right_map=min(q, key=lambda k: (-q[k], k)),
        map_equal=min(p, key=lambda k: (-p[k], k)) == min(q, key=lambda k: (-q[k], k)),
        positive_product_rows=sum(p[k] * q[k] > 0 for k in ids),
    )


def main():
    verify(read(HERE / "seal.json")["sha256"])
    assert read(HERE / "exit.json")["exit_code"] == 0
    plan = read(HERE / "plan.json")
    original = {s["session_id"]: s for s in read(ROOT / plan["coherence"])["scans"]}
    outcomes = read(HERE / "result.json")["scans"]
    by_ds = defaultdict(list)
    for scan in outcomes:
        expected = sorted(
            [p for p in original[scan["session_id"]]["pairs"] if p["selected"]],
            key=lambda p: (p["rx0"], p["rx1"]),
        )
        assert len(expected) == len(scan["pairs"])
        for pair, source in zip(scan["pairs"], expected, strict=True):
            for k in ("rx0", "rx1", "channel", "rf_hz"):
                assert pair[k] == source[k]
            group = [
                (p["rx0"], p["rx1"])
                for p in expected
                if p["channel"] == source["channel"] and p["rf_hz"] == source["rf_hz"]
            ]
            rotated = group[1:] + group[:1]
            control = (
                dict(zip(group, rotated, strict=True))[(source["rx0"], source["rx1"])][1]
                if len(group) > 1
                else None
            )
            assert control == pair["control_rx1"]
            for mode, tid in (("actual", pair["rx1"]), ("control", control)):
                exists = pair["rx0"] in scan["tracks"] and tid in scan["tracks"]
                assert exists == (pair[mode] is not None)
                if exists:
                    replay = independent(scan["tracks"][pair["rx0"]], scan["tracks"][tid])
                    for key, value in replay.items():
                        if isinstance(value, float):
                            assert math.isclose(
                                value, pair[mode][key], abs_tol=1e-12, rel_tol=1e-12
                            )
                        else:
                            assert value == pair[mode][key]
            by_ds[scan["dataset"]].append(
                {
                    **pair,
                    "signal_responsibilities": [
                        scan["tracks"][pair[k]]["signal_responsibility"]
                        if pair[k] in scan["tracks"]
                        else None
                        for k in ("rx0", "rx1")
                    ],
                }
            )
    summary = {}
    for ds, pairs in by_ds.items():
        actual = [p["actual"] for p in pairs if p["actual"] is not None]
        matched = [p for p in pairs if p["actual"] is not None and p["control"] is not None]
        signal_min = [min(p["signal_responsibilities"]) for p in pairs if p["actual"] is not None]
        summary[ds] = dict(
            median_min_signal_responsibility=float(np.median(signal_min)),
            both_signal_above_half=sum(v > 0.5 for v in signal_min),
            selected=len(pairs),
            eligible=len(actual),
            missing=len(pairs) - len(actual),
            nonempty=sum(p["intersection"] > 0 for p in actual),
            median_intersection=float(np.median([p["intersection"] for p in actual])),
            map_equal=sum(p["map_equal"] for p in actual),
            agreement_above_099=sum(p["agreement_mass"] > 0.99 for p in actual),
            median_agreement=float(np.median([p["agreement_mass"] for p in actual])),
            median_left_common_mass=float(np.median([p["left_common_mass"] for p in actual])),
            median_right_common_mass=float(np.median([p["right_common_mass"] for p in actual])),
            zero_weight_overlap=sum(
                p["intersection"] > 0 and p["positive_product_rows"] == 0 for p in actual
            ),
            matched_controls=len(matched),
            matched_actual_mean=float(np.mean([p["actual"]["agreement_mass"] for p in matched])),
            matched_control_mean=float(np.mean([p["control"]["agreement_mass"] for p in matched])),
            matched_actual_map=sum(p["actual"]["map_equal"] for p in matched),
            matched_control_map=sum(p["control"]["map_equal"] for p in matched),
            actual_above_control=sum(
                p["actual"]["agreement_mass"] > p["control"]["agreement_mass"] for p in matched
            ),
            actual_below_control=sum(
                p["actual"]["agreement_mass"] < p["control"]["agreement_mass"] for p in matched
            ),
            control_singletons=sum(p["control_reason"] == "singleton" for p in pairs),
        )
    save(HERE / "summary.json", dict(audit_passed=True, datasets=summary))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
    names = sorted(summary)
    x = np.arange(3)
    axes[0].bar(
        x,
        [summary[d]["nonempty"] / summary[d]["eligible"] for d in names],
        label="Nonempty bank overlap",
    )
    axes[0].bar(
        x,
        [summary[d]["map_equal"] / summary[d]["eligible"] for d in names],
        width=0.4,
        label="Same conditional MAP",
    )
    axes[0].set_title("All bank-eligible selected pairs")
    for offset, mode, label in (
        (-0.18, "actual", "Selected pair"),
        (0.18, "control", "Shuffled RX1"),
    ):
        axes[1].bar(
            x + offset, [summary[d][f"matched_{mode}_mean"] for d in names], width=0.36, label=label
        )
    axes[1].set_title("Matched control population: mean agreement mass")
    for ax in axes:
        ax.set_xticks(x, names)
        ax.set_ylim(0, 1.05)
        ax.legend(fontsize=8)
    fig.suptitle("Shared candidate support — conditional model agreement, not verified identity")
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("support." + suffix), dpi=160)
    plt.close(fig)
    print(summary)


if __name__ == "__main__":
    main()
