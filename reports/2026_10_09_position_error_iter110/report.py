"""Post-selection pilot evaluation; importing this module reads no recording outcomes."""

import argparse
import hashlib
import json
import runpy
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter106/report.py"))
distribution, paired = PREVIOUS["distribution"], PREVIOUS["paired"]
ARMS, VARIANTS = ("fitted-c", "zero-c"), ("archive", "0.0", "0.5")


def controller_state(here, member, digest, terminal_status):
    folder = Path(here) / "controller-claims"
    label = member["inventory_label"]
    claim, exited = folder / f"{label}.json", folder / f"{label}.exit.json"
    result = dict(
        controller_status="unlaunched",
        claim=None,
        exit_receipt=None,
        exit_status=None,
        returncode=None,
        error=None,
    )
    if claim.exists():
        row = json.loads(claim.read_text())
        assert row["protocol_sha256"] == digest and row["member"] == member
        result.update(
            controller_status="claimed-without-terminal", claim=str(claim.relative_to(here))
        )
    if exited.exists():
        assert claim.exists(), "Exit receipt without matching launch claim"
        row = json.loads(exited.read_text())
        assert row["protocol_sha256"] == digest and row["member"] == member
        result.update(
            exit_receipt=str(exited.relative_to(here)),
            exit_status=row["status"],
            returncode=row.get("returncode"),
            error=row.get("error"),
        )
    if terminal_status != "pending":
        result["controller_status"] = (
            "terminal" if claim.exists() else "terminal-without-controller-claim"
        )
    return result


def raw_metrics(rows, rho, arm):
    attempts = [r.get("raw", {}).get(rho, {}).get(arm, dict(status="missing")) for r in rows]
    fits = [a["fit"] for a in attempts if a["status"] == "complete"]
    qualified = [
        bool(
            f["converged"]
            and f.get("independently_feasible", False)
            and np.isfinite(f.get("independent_stationarity", np.inf))
            and f["independent_stationarity"] <= 0.001
        )
        for f in fits
    ]
    operations = [r.get("operational", {}).get(rho, {}).get(arm) for r in rows]
    result = dict(
        expected=len(rows),
        statuses=dict(Counter(a["status"] for a in attempts)),
        qualified=sum(qualified),
        unqualified=len(fits) - sum(qualified),
        fallback=sum(bool(op["fallback"]) for op in operations if op is not None),
        operational_missing=sum(op is None for op in operations),
    )
    for key in (
        "posterior_rms_hz",
        "signal_windows",
        "elapsed_s",
        "evaluations",
        "optimizer_iterations_reported",
        "independent_stationarity",
    ):
        values = [f[key] for f in fits if f.get(key) is not None]
        result[key] = distribution(values)
        result[key + "_unavailable"] = len(fits) - len(values)
    for key in ("frequency_nll", "timing_prior", "nuisance_prior"):
        result[key] = distribution(
            [f["score_components"][key] for f in fits if key in f.get("score_components", {})]
        )
    return result


def summarize(plan, receipts, digest):
    lookup = {r["member"]["inventory_label"]: r for r in receipts}
    assert len(lookup) == len(receipts)
    assert len(plan["members"]) == 12
    rows = []
    for binding in plan["members"]:
        member = binding["member"]
        row = lookup.get(member["inventory_label"], dict(member=member, status="pending"))
        assert row["member"] == member
        if row["status"] != "pending":
            assert row["protocol_sha256"] == digest
        rows.append(row)
    assert set(lookup) <= {r["member"]["inventory_label"] for r in rows}
    complete = all(r["status"] == "complete" and "errors" in r for r in rows)
    summary = dict(
        protocol_sha256=digest,
        complete=complete,
        scope="Consumed conditional pilot",
        coverage=[
            dict(
                member=r["member"],
                status=r["status"],
                error=r.get("error"),
                evaluation_authority=r.get("evaluation_authority"),
                controller=r.get("controller", dict(controller_status="not-inspected")),
            )
            for r in rows
        ],
        groups={},
        gates=None,
        paired_rows=[],
    )
    groups = {d: [r for r in rows if r["member"]["dataset"] == d] for d in ("DS16", "DS17", "DS18")}
    assert all(len(v) == 4 for v in groups.values())
    groups["Pooled"] = rows
    for name, members in groups.items():
        entry = dict(
            membership=len(members),
            statuses=dict(Counter(r["status"] for r in members)),
            position=None,
            comparisons=None,
            raw={},
        )
        entry["reconstruction_seconds"] = distribution(
            [r["reconstruction_seconds"] for r in members if "reconstruction_seconds" in r]
        )
        entry["recording_total_seconds"] = distribution(
            [r["elapsed_s"] for r in members if "elapsed_s" in r]
        )
        entry["recording_peak_memory_bytes"] = None
        entry["memory_note"] = (
            "Not measured by frozen engine; synthetic109 peaks are not recording measurements"
        )
        for arm in ARMS:
            entry["raw"][arm] = {rho: raw_metrics(members, rho, arm) for rho in ("0.0", "0.5")}
        if complete:
            entry["position"], entry["comparisons"] = {}, {}
            for arm in ARMS:
                errors = {v: [r["errors"][v][arm] for r in members] for v in VARIANTS}
                entry["position"][arm] = {v: distribution(x) for v, x in errors.items()}
                entry["comparisons"][arm] = {
                    f"{a}-{b}": paired(errors[a], errors[b])
                    for a, b in (("0.5", "0.0"), ("0.0", "archive"), ("0.5", "archive"))
                }
        summary["groups"][name] = entry
    if complete:
        criteria = plan["progression_gates"]
        pool = summary["groups"]["Pooled"]
        positions, raw = pool["position"], pool["raw"]
        fitted_a, fitted_b = positions["fitted-c"]["0.5"], positions["fitted-c"]["0.0"]
        zero_a, zero_b = positions["zero-c"]["0.5"], positions["zero-c"]["0.0"]
        metrics = [raw[a][rho] for a in ARMS for rho in ("0.0", "0.5")]
        gates = dict(
            all48_raw_qualified=(
                sum(m["qualified"] for m in metrics) == 48
                and sum(m["fallback"] for m in metrics) == 0
            ),
            fitted_mean=fitted_a["mean"]
            <= (1 - criteria["fitted_mean_improvement_fraction_minimum"]) * fitted_b["mean"],
            fitted_median=fitted_a["median"] <= fitted_b["median"],
            paired_regressions=all(
                pool["comparisons"][a]["0.5-0.0"]["worst_regression_km"]
                <= criteria["both_arms_maximum_paired_regression_km"]
                for a in ARMS
            ),
            worst=all(positions[a]["0.5"]["worst"] <= positions[a]["0.0"]["worst"] for a in ARMS),
            zero_mean=zero_a["mean"]
            <= (1 + criteria["zero_c_mean_maximum_worsening_fraction"]) * zero_b["mean"],
            actual_elapsed=all(
                m["elapsed_s"] is not None
                and m["elapsed_s"]["n"] == 12
                and m["elapsed_s"]["worst"] <= criteria["absolute_fit_budget_seconds"]
                for m in metrics
            ),
        )
        summary["gates"] = dict(
            checks=gates,
            passed=all(gates.values()),
            interpretation="Mechanism screening only; not independent validation",
        )
        summary["paired_rows"] = [
            dict(member=r["member"], arm=a, errors={v: r["errors"][v][a] for v in VARIANTS})
            for r in rows
            for a in ARMS
        ]
    return summary


def plot(summary, receipts, path):
    if not summary["complete"]:
        return False
    from matplotlib.figure import Figure

    figure = Figure(figsize=(11, 8), layout="constrained")
    axes = figure.subplots(2, 2)
    for index, arm in enumerate(ARMS):
        for variant in VARIANTS:
            x = np.sort([r["errors"][variant][arm] for r in receipts])
            axes[index, 0].step(x, np.arange(1, len(x) + 1) / len(x), where="post", label=variant)
        axes[index, 0].set(xlabel="Position error (km)", ylabel="Cumulative fraction", title=arm)
        axes[index, 0].legend()
        control = [r["errors"]["0.0"][arm] for r in receipts]
        candidate = [r["errors"]["0.5"][arm] for r in receipts]
        high = max(control + candidate)
        axes[index, 1].scatter(control, candidate)
        axes[index, 1].plot([0, high], [0, high], color="gray")
        axes[index, 1].set(xlabel="rho0 control error (km)", ylabel="rho0.5 error (km)")
    figure.suptitle("12 consumed recordings; conditional mechanism pilot")
    figure.savefig(path, dpi=160)
    return True


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    rows = []
    for binding in plan["members"]:
        path = HERE / "results" / f"{binding['member']['inventory_label']}.json"
        row = (
            json.loads(path.read_text())
            if path.exists()
            else dict(member=binding["member"], protocol_sha256=digest, status="pending")
        )
        assert row["member"] == binding["member"] and row["protocol_sha256"] == digest
        row["controller"] = controller_state(HERE, binding["member"], digest, row["status"])
        for rho in ("0.0", "0.5"):
            for arm in ARMS:
                attempt_path = (
                    HERE
                    / "attempts"
                    / binding["member"]["inventory_label"]
                    / f"rho{rho}-{arm}.json"
                )
                if not attempt_path.exists():
                    continue
                attempt = json.loads(attempt_path.read_text())
                assert (
                    attempt["protocol_sha256"] == digest and attempt["member"] == binding["member"]
                )
                assert attempt["rho"] == float(rho) and attempt["arm"] == arm
                old = row.setdefault("raw", {}).setdefault(rho, {}).get(arm)
                assert old is None or old == attempt
                row["raw"][rho][arm] = attempt
        if row["status"] == "complete":
            source = ROOT / binding["b7_source"]
            assert (
                hashlib.sha256(source.read_bytes()).hexdigest()
                == plan["source_sha256"][binding["b7_source"]]
            )
            archive = json.loads(source.read_text())["stages"]["B7"]
            document, authority = PREVIOUS["evaluation_document"](binding, plan)
            row["evaluation_authority"] = authority
            error = PREVIOUS["position_error"]
            for arm in ARMS:
                np.testing.assert_allclose(
                    error(archive[arm]["vector"], document),
                    archive[arm]["error_km"],
                    atol=1e-8,
                    rtol=0,
                )
            row["errors"] = {
                v: {
                    a: error(
                        archive[a]["vector"]
                        if v == "archive"
                        else row["operational"][v][a]["fit"]["vector"],
                        document,
                    )
                    for a in ARMS
                }
                for v in VARIANTS
            }
        rows.append(row)
    summary = summarize(plan, rows, digest)
    (HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    text = [
        "# Conditional persistence pilot",
        "",
        f"Full matched12 coverage: {summary['complete']}.",
        "Consumed development only; no replacement members or validation claim.",
        "",
        "| Group | Arm | Model | n | Mean km | Median km | p95 km | Worst km |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, entry in summary["groups"].items():
        if entry["position"] is None:
            continue
        for arm, variants in entry["position"].items():
            for variant, m in variants.items():
                text.append(
                    f"| {group} | {arm} | {variant} | {m['n']} | {m['mean']:.4f} "
                    f"| {m['median']:.4f} | {m['p95']:.4f} | {m['worst']:.4f} |"
                )
    if not summary["complete"]:
        text += [
            "",
            "Aggregate accuracy and progression gates withheld until full matched coverage.",
        ]
    text += ["", "| Member | Result | Controller | Exit | Error |", "|---|---|---|---|---|"]
    for covered in summary["coverage"]:
        c = covered["controller"]
        exit_value = (
            c.get("returncode") if c.get("returncode") is not None else c.get("exit_status")
        )
        error = (
            str(covered.get("error") or c.get("error") or "—")
            .replace("|", "\\|")
            .replace("\n", " ")
        )
        label = covered["member"]["inventory_label"]
        controller_label = c["controller_status"]
        if c.get("claim"):
            controller_label = f"[{controller_label}]({c['claim']})"
        text.append(
            f"| {label} | {covered['status']} | {controller_label} | {exit_value} | {error} |"
        )
    text += [
        "",
        "Frozen gates: `" + json.dumps(summary["gates"]) + "`",
        "",
        "| Arm | rho | Raw qualified/12 | Failed | Fallback | Median RMS Hz | Max elapsed s |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, variants in summary["groups"]["Pooled"]["raw"].items():
        for rho, m in variants.items():
            rms = m["posterior_rms_hz"]
            elapsed = m["elapsed_s"]
            text.append(
                f"| {arm} | {rho} | {m['qualified']}/12 | {m['statuses'].get('failed', 0)} "
                f"| {m['fallback']} | {rms['median'] if rms else '—'} "
                f"| {elapsed['worst'] if elapsed else '—'} |"
            )
    text += [
        "",
        "Frequency fit uses model-specific responsibilities; sequence NLL is not an accuracy gate. "
        "Runtime includes warm-start asymmetry, and the90s deadline is checked between calls. "
        "Actual elapsed time above90s fails the reported gate even if the fit qualified. "
        "Unavailable iteration counts remain null. Full coverage and separate diagnostics: "
        "[summary.json](summary.json).",
    ]
    text += [
        "",
        "Recording peak memory was not measured and is unavailable; synthetic109 memory "
        "is not substituted. Reported fit elapsed time, recording reconstruction and total "
        "time are distinct. Extra reporter/independent-check time is not imputed to a fit.",
    ]
    if plot(summary, rows, HERE / "comparison.png"):
        text += ["", "![Paired and cumulative errors](comparison.png)"]
    (HERE / "RESULTS.md").write_text("\n".join(text) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate-sealed-results", action="store_true", required=True)
    parser.parse_args()
    main()
