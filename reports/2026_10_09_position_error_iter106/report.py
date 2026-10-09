"""Evaluation-only census report; importing this module reads no outcomes/reference."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")
VARIANTS = ("archive", "125", "100")


def load_terminal_rows(plan, digest, here=HERE):
    """Verify full terminal coverage before any evaluation reference is opened."""
    rows = {}
    for binding in plan["members"]:
        member = binding["member"]
        label = member["inventory_label"]
        path = here / "results" / f"{label}.json"
        if not path.exists():
            raise RuntimeError(f"{label} not terminal; reference evaluation withheld")
        row = json.loads(path.read_text())
        if row.get("status") not in ("complete", "failed", "input-failed"):
            raise RuntimeError(f"{label} not terminal; reference evaluation withheld")
        assert row["protocol_sha256"] == digest and row["member"] == member
        rows[label] = row
    return rows


def evaluation_document(binding, plan, root=ROOT, status_reader=None):
    """Metadata-only access to the original loader authority, never load_case."""
    from leo.contracts.digests import canonical_digest

    loader = binding["loader_binding"]

    def bound_read(name):
        path = root / name
        expected = plan["source_sha256"][name]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
        return json.loads(path.read_text())

    if loader.get("baseline_path"):
        if loader["baseline_path"] in plan["source_sha256"]:
            document = bound_read(loader["baseline_path"])
            authority = dict(path=loader["baseline_path"], kind="frozen-file-sha256")
        else:
            assert loader["kind"] == "completion"
            ancestor = bound_read(binding["result_source"])
            assert ancestor["member"] == binding["member"]
            document = json.loads((root / loader["baseline_path"]).read_text())
            expected = ancestor["baseline_document_digest"]
            assert canonical_digest(document) == expected
            authority = dict(
                path=loader["baseline_path"], kind="frozen-ancestor-canonical-digest",
                ancestor_path=binding["result_source"],
                ancestor_sha256=plan["source_sha256"][binding["result_source"]],
                document_digest=expected,
            )
    else:
        expected = loader.get("baseline_document_digest")
        if loader["kind"] == "legacy_ds16":
            name = "reports/2026_10_08_hard60_bounded_recovery/frozen-inputs.json"
            pinned = bound_read(name)[loader["legacy_label"]]
            assert pinned["session_id"] == binding["member"]["session_id"]
            expected = pinned["baseline_document_digest"]
        assert expected, "Missing frozen public-document identity"
        if status_reader is None:
            from leo.storage.regional_position_v2 import Hard60Store

            manifest = (
                Hard60Store(Path("/srv/bulk/leo")).status(binding["member"]["session_id"]).manifest
            )
            assert manifest is not None
            document = manifest.document.model_dump(mode="json")
        else:
            document = status_reader(binding["member"]["session_id"])
        assert canonical_digest(document) == expected
        authority = dict(kind="public-status-canonical-digest", document_digest=expected)
    assert document["session_id"] == binding["member"]["session_id"]
    assert document["input_manifest_sha256"] == loader["effective_input_digest"]
    return document, authority


def position_error(vector, document):
    """Use this member's persisted prior and evaluation reference, never CLI defaults."""
    import math

    from leo.analysis.regional_position_score import coordinates
    from leo.contracts.regional_position import RegionalPrior

    prior = RegionalPrior(
        latitude_deg=document["prior_latitude_deg"],
        longitude_deg=document["prior_longitude_deg"],
        radius_km=document["prior_radius_km"],
        altitude_m=0.0,
    )
    latitude, longitude = coordinates(prior, np.asarray(vector)[:2])
    a, b, c, d = map(
        math.radians,
        (
            latitude,
            longitude,
            document["reference_latitude_deg"],
            document["reference_longitude_deg"],
        ),
    )
    h = math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, h))))


def distribution(values):
    x = np.asarray(values, float)
    if not len(x):
        return None
    assert np.isfinite(x).all()
    return dict(
        n=len(x),
        mean=float(x.mean()),
        median=float(np.median(x)),
        p95=float(np.percentile(x, 95)),
        worst=float(x.max()),
    )


def paired(after, before):
    delta = np.asarray(after) - np.asarray(before)
    return dict(
        n=len(delta),
        mean_delta_km=float(delta.mean()),
        improved=int(sum(delta < -1e-6)),
        regressed=int(sum(delta > 1e-6)),
        regressed_over_1km=int(sum(delta > 1)),
        worst_regression_km=float(delta.max()),
    )


def diagnostics(rows, variant, arm):
    attempts = [r["raw"][variant][arm] for r in rows]
    fits = [a["fit"] for a in attempts if a["status"] == "complete"]
    selected = [r["operational"][variant][arm] for r in rows]
    result = dict(
        attempts=len(attempts),
        raw_failed=sum(a["status"] != "complete" for a in attempts),
        raw_qualified=sum(f["converged"] for f in fits),
        raw_unqualified=sum(not f["converged"] for f in fits),
        fallbacks=sum(r["fallback"] for r in selected),
        fallback_sources=dict(Counter(r["source"] for r in selected if r["fallback"])),
    )
    for name in (
        "posterior_rms_hz",
        "signal_windows",
        "elapsed_s",
        "evaluations",
        "independent_stationarity",
    ):
        result[name] = distribution([f[name] for f in fits if name in f])
    for name in ("frequency_nll", "timing_prior", "nuisance_prior"):
        result[name] = distribution([f["score_components"][name] for f in fits])
    for name in ("maximum_assignment_unweighted_rms_hz", "clock_l2"):
        result[name] = distribution([f["frequency_diagnostics"][name] for f in fits])
    result["mean_clutter_probability"] = distribution(
        [np.mean(f["frequency_diagnostics"]["clutter_probability"]) for f in fits]
    )
    changes = []
    if variant == "100":
        for row in rows:
            a, b = row["raw"]["100"][arm], row["raw"]["125"][arm]
            if a["status"] == b["status"] == "complete":
                x = np.asarray(a["fit"]["frequency_diagnostics"]["assigned_satellite"])
                y = np.asarray(b["fit"]["frequency_diagnostics"]["assigned_satellite"])
                assert x.shape == y.shape
                changes.append(float(np.mean(x != y)))
    result["assignment_changed_fraction_vs125"] = distribution(changes)
    return result


def summarize(plan, rows, digest):
    """Rows already carry evaluation-only errors added after sealed winner selection."""
    lookup = {r["member"]["inventory_label"]: r for r in rows}
    assert len(lookup) == len(rows)
    coverage, allrows = [], []
    for binding in plan["members"]:
        member = binding["member"]
        row = lookup.get(member["inventory_label"], dict(status="pending", member=member))
        assert row["member"] == member
        if row["status"] != "pending":
            assert row["protocol_sha256"] == digest
        row = dict(row, loader_kind=binding["loader_binding"]["kind"])
        allrows.append(row)
        coverage.append(
            dict(
                member=member,
                status=row["status"],
                error=row.get("error"),
                loader_kind=row["loader_kind"],
                evaluation_authority=row.get("evaluation_authority"),
            )
        )
    assert set(lookup) <= {r["member"]["inventory_label"] for r in allrows}
    groups = {
        d: [r for r in allrows if r["member"]["dataset"] == d] for d in ("DS16", "DS17", "DS18")
    }
    groups["Pooled"] = allrows
    groups["DS16-original48"] = [r for r in groups["DS16"] if r["loader_kind"] == "legacy_ds16"]
    groups["DS16-added15"] = [r for r in groups["DS16"] if r["loader_kind"] != "legacy_ds16"]
    for exposure, name in ((True, "DS18-prior24"), (False, "DS18-other10-consumed")):
        groups[name] = [
            r
            for r in groups["DS18"]
            if (r["member"].get("exposure") == "previously_evaluated_consumed") == exposure
        ]
    summary = dict(
        protocol_sha256=digest,
        coverage=coverage,
        groups={},
        gates={},
        complete=all(r["status"] == "complete" for r in allrows),
    )
    summary["paired_rows"] = [
        dict(
            member=r["member"],
            arm=arm,
            archive_km=r["errors"]["archive"][arm],
            control125_km=r["errors"]["125"][arm],
            candidate100_km=r["errors"]["100"][arm],
            candidate_minus_control_km=r["errors"]["100"][arm] - r["errors"]["125"][arm],
        )
        for r in allrows
        if r["status"] == "complete"
        for arm in ARMS
    ]
    for name, members in groups.items():
        done = [r for r in members if r["status"] == "complete"]
        entry = dict(
            membership=len(members),
            complete=len(done),
            statuses=dict(Counter(r["status"] for r in members)),
            position=None,
            comparisons=None,
            available_diagnostics={},
        )
        for arm in ARMS:
            entry["available_diagnostics"][arm] = {
                v: diagnostics(done, v, arm) for v in ("125", "100")
            }
        if members and len(done) == len(members):
            entry["position"], entry["comparisons"] = {}, {}
            for arm in ARMS:
                errors = {v: [r["errors"][v][arm] for r in done] for v in VARIANTS}
                entry["position"][arm] = {v: distribution(x) for v, x in errors.items()}
                entry["comparisons"][arm] = {
                    f"{a}-{b}": paired(errors[a], errors[b])
                    for a, b in (("100", "125"), ("125", "archive"), ("100", "archive"))
                }
        summary["groups"][name] = entry
    if summary["complete"]:
        criteria = plan["decision_criteria"]
        for arm in ARMS:
            pooled = summary["groups"]["Pooled"]
            a, b = pooled["position"][arm]["100"], pooled["position"][arm]["125"]
            gates = {
                name: a[name]
                <= (1 - criteria[f"pooled_{name}_minimum_improvement_fraction"]) * b[name]
                for name in ("mean", "median")
            }
            gates["dataset_means"] = all(
                summary["groups"][d]["position"][arm]["100"]["mean"]
                <= (1 + criteria["maximum_dataset_mean_regression_fraction"])
                * summary["groups"][d]["position"][arm]["125"]["mean"]
                for d in ("DS16", "DS17", "DS18")
            )
            gates["tails"] = all(
                a[k] <= (1 + criteria["maximum_pooled_p95_and_worst_regression_fraction"]) * b[k]
                for k in ("p95", "worst")
            )
            pairs = pooled["comparisons"][arm]
            gates["regression_count"] = (
                pairs["100-archive"]["regressed_over_1km"]
                <= pairs["125-archive"]["regressed_over_1km"]
            )
            summary["gates"][arm] = dict(
                checks=gates,
                passed=all(gates.values()),
                frozen_regression_definition=criteria.get("paired_regression_count"),
                candidate_vs_control_regressed_over_1km=pairs["100-125"]["regressed_over_1km"],
                stricter_zero_new_regressions_sensitivity=(
                    pairs["100-125"]["regressed_over_1km"] == 0
                ),
                sensitivity_is_not_frozen_gate=True,
            )
    return summary


def plot(summary, rows, destination):
    if not summary["complete"]:
        return False
    from matplotlib.figure import Figure

    figure = Figure(figsize=(14, 8), layout="constrained")
    axes = figure.subplots(2, 3)
    for i, arm in enumerate(ARMS):
        for variant in VARIANTS:
            x = np.sort([r["errors"][variant][arm] for r in rows])
            axes[i, 0].plot(x, np.arange(1, len(x) + 1) / len(x), label=variant)
        axes[i, 0].set(xlabel="Position error (km)", ylabel="Cumulative fraction", title=arm)
        axes[i, 0].set_xscale("symlog", linthresh=1)
        axes[i, 0].legend()
        control = [r["errors"]["125"][arm] for r in rows]
        candidate = [r["errors"]["100"][arm] for r in rows]
        axes[i, 1].scatter(control, candidate, s=12, alpha=0.7)
        high = max(control + candidate)
        axes[i, 1].plot([0, high], [0, high], color="gray", linewidth=0.8)
        axes[i, 1].set(xlabel="125 Hz error (km)", ylabel="100 Hz error (km)")
        axes[i, 1].set_xscale("symlog", linthresh=1)
        axes[i, 1].set_yscale("symlog", linthresh=1)
        for j, variant in enumerate(VARIANTS):
            means = [
                summary["groups"][d]["position"][arm][variant]["mean"]
                for d in ("DS16", "DS17", "DS18")
            ]
            axes[i, 2].bar(np.arange(3) + (j - 1) * 0.25, means, width=0.25, label=variant)
        axes[i, 2].set_xticks(range(3), ["DS16", "DS17", "DS18"])
        axes[i, 2].set_ylabel("Mean position error (km)")
        axes[i, 2].legend()
    figure.suptitle("Consumed full-census comparison; no independent-validation claim")
    figure.savefig(destination, dpi=160)
    return True


def diagnostic_tables(summary):
    lines = [
        "",
        "Available raw-fit diagnostics (not full-census accuracy estimates):",
        "",
        "| Group | Arm | Hz | Raw qualified/attempts | Failed | Fallbacks | Mean seconds |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    frequency = [
        "",
        "Frequency/association diagnostics are distinct from position:",
        "",
        "| Group | Arm | Hz | Median posterior RMS Hz | Mean clutter | Mean changed assignments |",
        "|---|---|---:|---:|---:|---:|",
    ]

    def value(row, key, statistic="mean"):
        metric = row.get(key)
        return "—" if metric is None else f"{metric[statistic]:.4f}"

    for group in ("DS16", "DS17", "DS18", "Pooled"):
        for arm, variants in summary["groups"][group]["available_diagnostics"].items():
            for variant, d in variants.items():
                lines.append(
                    f"| {group} | {arm} | {variant} | {d['raw_qualified']}/{d['attempts']} "
                    f"| {d['raw_failed']} | {d['fallbacks']} | {value(d, 'elapsed_s')} |"
                )
                frequency.append(
                    f"| {group} | {arm} | {variant} "
                    f"| {value(d, 'posterior_rms_hz', 'median')} "
                    f"| {value(d, 'mean_clutter_probability')} "
                    f"| {value(d, 'assignment_changed_fraction_vs125')} |"
                )
    return lines + frequency


def main():
    # Reference access is confined to this explicitly invoked evaluation entry point.
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    terminal_rows = load_terminal_rows(plan, digest)
    rows = []
    for binding in plan["members"]:
        row = terminal_rows[binding["member"]["inventory_label"]]
        if row["status"] == "complete":
            archive_path = ROOT / binding["b7_source"]
            assert (
                hashlib.sha256(archive_path.read_bytes()).hexdigest()
                == plan["source_sha256"][binding["b7_source"]]
            )
            archive = json.loads(archive_path.read_text())["stages"]["B7"]
            document, authority = evaluation_document(binding, plan)
            row["evaluation_authority"] = authority
            # Prove each persisted evaluation frame/reference reproduces its archived error.
            for arm in ARMS:
                np.testing.assert_allclose(
                    position_error(archive[arm]["vector"], document),
                    archive[arm]["error_km"],
                    atol=1e-8,
                    rtol=0,
                )
            row["errors"] = {
                v: {
                    a: position_error(
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
        "# Frequency-width comparison",
        "",
        f"Complete membership: {summary['complete']}.",
        "Consumed development only. Missing/failed inputs withhold full position metrics.",
        "Reference values do not guide model construction, starts or winners. A legacy loader compares an archived error field only for artifact consistency; see [the dependency audit](REFERENCE_DEPENDENCY_AUDIT.md).",
        "",
        "| Dataset | Arm | Model | n | Mean km | Median km | p95 km | Worst km |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, entry in summary["groups"].items():
        if entry["position"] is None:
            text.append(
                f"\n{group}: {entry['complete']}/{entry['membership']} complete; "
                "position metrics withheld.\n"
            )
            continue
        for arm, variants in entry["position"].items():
            for variant, m in variants.items():
                text.append(
                    f"| {group} | {arm} | {variant} | {m['n']} | {m['mean']:.4f} "
                    f"| {m['median']:.4f} | {m['p95']:.4f} | {m['worst']:.4f} |"
                )
    text += [
        "",
        "Predeclared gates: `" + json.dumps(summary["gates"]) + "`",
        "Frozen regression criterion: relative to the same archived B7 endpoint, "
        "compare >1 km regression counts for candidate and control. Candidate-versus-control "
        "counts and the stricter zero-new-regressions sensitivity are also reported separately; "
        "the sensitivity does not replace the frozen gate.",
        "",
        "Complete coverage and separate fit diagnostics: [summary.json](summary.json). "
        "Different-width objective values do not rank models.",
    ]
    text += diagnostic_tables(summary)
    if plot(summary, rows, HERE / "comparison.png"):
        text += ["", "![Position comparisons](comparison.png)"]
    (HERE / "RESULTS.md").write_text("\n".join(text) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate-sealed-results", action="store_true", required=True)
    parser.parse_args()
    main()
