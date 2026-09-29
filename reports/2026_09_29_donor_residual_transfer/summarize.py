"""Least-squares and matched-group audit of conditional residual transfer."""
# ruff: noqa: E501 -- report tables and prose.

from collections import defaultdict

import matplotlib
import numpy as np
from residual import errors, transfer
from study import HERE, read, save, verify

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def median(values):
    return float(np.median(values)) if values else None


def main():
    bindings = read(HERE / "input-seal.json")["sha256"]
    donors = []
    targets = []
    counts = []
    for u in read(HERE / "plan.json")["units"]:
        folder = HERE / "runs" / u["unit_id"]
        assert read(folder / "exit.json")["exit_code"] == 0
        for n, h in read(folder / "seal.json")["sha256"].items():
            assert n not in bindings or bindings[n] == h
            bindings[n] = h
        r = read(folder / "result.json")
        assert r["unit_id"] == u["unit_id"] and r["role"] == u["role"]
        assert abs(r["training_score"] - u["training_score"]) < 1e-7
        covered = {(c["session_id"], c["track_id"]) for c in r["cases"] + r["exclusions"]}
        assert len(covered) == r["tracks"]
        for c in r["cases"]:
            t = np.asarray(c["times"])
            e = np.asarray(c["residual"])
            m = np.asarray(c["mask"], bool)
            assert m.sum() >= 5 and np.ptp(t[m]) >= 5 and (~m).any()
            coef = np.linalg.lstsq(
                np.column_stack((np.ones(m.sum()), t[m] - np.mean(t[m]))), e[m], rcond=None
            )[0]
            assert abs(coef[0] - c["shape"]["residual_center"]) < 1e-7
            assert abs(coef[1] - c["shape"]["slope"]) < 1e-7
            assert abs(t[m].mean() - c["shape"]["time_center"]) < 1e-10
            assert c["candidate_weight"] * c["signal_responsibility"] >= 0.5
            assert c["available_utc_ns"] == u["available_utc_ns"]
        (donors if u["role"] == "donor" else targets).extend(r["cases"])
        counts.append(
            dict(
                unit_id=u["unit_id"],
                role=u["role"],
                tracks=r["tracks"],
                eligible_cases=len(r["cases"]),
                exclusions=len(r["exclusions"]),
            )
        )
    verify(bindings)
    assert sum(c["tracks"] for c in counts if c["role"] == "target") == 4328
    assert sum(c["tracks"] for c in counts if c["role"] == "donor") == 10930
    rows = []
    for target in targets:
        fit = transfer(target, donors)
        row = {k: target[k] for k in ("unit_id", "session_id", "track_id", "number")}
        row.update(matched=fit is not None, baseline=errors(target, 0.0))
        if fit:
            index = defaultdict(list)
            for d in donors:
                if (
                    d["available_utc_ns"] < target["start_utc_ns"]
                    and d["receiver_id"] == target["receiver_id"]
                    and d["rf_hz"] == target["rf_hz"]
                ):
                    index[d["unit_id"]].append(d)
            expected = []
            candidate = []
            control = []
            for key, dd in index.items():
                a = [d["shape"]["slope"] for d in dd if d["number"] == target["number"]]
                b = [d["shape"]["slope"] for d in dd if d["number"] != target["number"]]
                if a and b:
                    expected.append(key)
                    candidate.append(median(a))
                    control.append(median(b))
            assert expected == fit["groups"] and len(expected) >= 2
            assert (
                candidate == fit["candidate_group_slopes"]
                and control == fit["control_group_slopes"]
            )
            assert (
                median(candidate) == fit["candidate_slope"]
                and median(control) == fit["control_slope"]
            )
            row.update(
                transfer=fit,
                candidate=errors(target, fit["candidate_slope"]),
                control=errors(target, fit["control_slope"]),
            )
            # Reconstruct forecasts without the scoring helper.
            for arm, slope in (
                ("baseline", 0.0),
                ("candidate", fit["candidate_slope"]),
                ("control", fit["control_slope"]),
            ):
                m = np.asarray(target["mask"], bool)
                e = np.asarray(target["residual"])
                t = np.asarray(target["times"])
                held = e[~m] - np.mean(e[m]) - slope * (t[~m] - np.mean(t[m]))
                assert abs(float(np.median(abs(held))) - row[arm]["held_median_abs"]) < 1e-7
        rows.append(row)
    aggregates = []
    for panel in [u["unit_id"] for u in read(HERE / "plan.json")["units"] if u["role"] == "target"]:
        rr = [r for r in rows if r["unit_id"] == panel and r["matched"]]
        aggregates.append(
            dict(
                panel=panel,
                matched_cases=len(rr),
                median_held_abs={
                    arm: median([r[arm]["held_median_abs"] for r in rr])
                    for arm in ("baseline", "candidate", "control")
                },
                candidate_beats_baseline=sum(
                    r["candidate"]["held_median_abs"] < r["baseline"]["held_median_abs"] for r in rr
                ),
                candidate_beats_control=sum(
                    r["candidate"]["held_median_abs"] < r["control"]["held_median_abs"] for r in rr
                ),
                median_paired_gain=median(
                    [
                        r["baseline"]["held_median_abs"] - r["candidate"]["held_median_abs"]
                        for r in rr
                    ]
                ),
            )
        )
    save(
        HERE / "summary.json",
        dict(audit_passed=True, counts=counts, aggregates=aggregates, rows=rows),
    )
    lines = [
        "# Conditional residual-slope transfer from independent donors",
        "",
        "Diagnostic only: candidate cases are selected by training signal × candidate weight ≥0.5 and adequate training span. Slopes and eligibility use no target held data. These errors are not normalized predictive likelihoods or geographic errors.",
        "",
        "| Target panel | Matched cases | Baseline held median abs (Hz) | Candidate slope | RX/RF control | Candidate beats baseline | Candidate beats control |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    def fmt(x):
        return "—" if x is None else f"{x:.3f}"

    for a in aggregates:
        e = a["median_held_abs"]
        n = a["matched_cases"]
        lines.append(
            f"| {a['panel']} | {n} | {fmt(e['baseline'])} | {fmt(e['candidate'])} | {fmt(e['control'])} | {a['candidate_beats_baseline']}/{n} | {a['candidate_beats_control']}/{n} |"
        )
    lines += [
        "",
        "Zero matched cases mean unavailable evidence, not successful prediction. All 4,328 target tracks remain in coverage denominators; the table describes only the explicitly matched cases. Per-track medians are aggregated equally, and tracks/receivers within recordings are dependent.",
        "",
        "![Matched conditional residual forecast errors](transfer.png)",
        "",
        "[Protocol](PROTOCOL.md), [all eligibility and outcomes](summary.json), [tests](tests.log), [evidence hashes](evidence-sha256.json).",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    shown = [a for a in aggregates if a["matched_cases"]]
    fig, ax = plt.subplots(figsize=(9, 4), layout="constrained")
    x = np.arange(len(shown))
    for j, arm in enumerate(("baseline", "candidate", "control")):
        ax.bar(x + (j - 1) * 0.25, [a["median_held_abs"][arm] for a in shown], 0.25, label=arm)
    ax.set_xticks(x, [a["panel"].replace("_", " ") for a in shown])
    ax.set_ylabel("Median of case held median abs residual (Hz)")
    ax.set_title("Same target cases; training offsets and causal donor slopes")
    ax.legend()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / ("transfer." + suffix), dpi=160)
    plt.close(fig)
    print(aggregates, flush=True)


if __name__ == "__main__":
    main()
