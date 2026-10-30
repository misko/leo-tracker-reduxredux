"""Evaluate frozen whole-cohort ALGO02/03 outputs; truth is reporting-only."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from leo.qualification.algo03_promotion import qualify


ARMS = ("c0", "fitted_c")
RELEASE_MANIFEST_SHA256 = "6dd58bbbe5e7d1f881c820edf0bee0345952a365553afaf37f457dfcec189545"


def read(path):
    return json.loads(Path(path).read_text())


def optional(path):
    return read(path) if Path(path).exists() else None


def distance_km(position, truth):
    lat, lon, tlat, tlon = map(math.radians, (*position, *truth))
    a = math.sin((lat - tlat) / 2) ** 2 + math.cos(lat) * math.cos(tlat) * math.sin((lon - tlon) / 2) ** 2
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def endpoint_result(state, arm, seconds, truth, available_observations=None):
    gates = arm.get("gates", {}).get("tracks", []) + arm.get("linear_gates", []) if arm else []
    ids = [identifier for gate in gates for identifier in gate.get("observation_ids", [])]
    published_count = (len(set(ids)) if all("observation_ids" in gate for gate in gates)
                       else None) if gates else None
    associated = len(set(arm["associated_ids"])) if arm and "associated_ids" in arm else published_count
    return dict(state=state, total_seconds=seconds,
                error_km=distance_km(arm["endpoint_latlon"], truth) if state == "complete" else None,
                endpoint_latlon=arm.get("endpoint_latlon") if arm else None,
                frequency_RMS_hz=arm.get("RMS_hz") if arm else None,
                negative_twice_elbo=arm.get("negative_twice_elbo") if arm else None,
                associated_points_from_terminal_gates=published_count,
                associated_points=associated,
                available_GLRT_observations=available_observations,
                associated_percent=(100 * associated / available_observations
                                    if associated is not None and available_observations else None))


def observation_denominator(case, folder, baseline):
    """Count only hash-verified observations from the public paired export."""
    descriptor_path = (Path(baseline["descriptor_path"]) if baseline and baseline.get("descriptor_path")
                       else folder / "evaluation-export/descriptor.json")
    if not descriptor_path.exists():
        return None, "Paired public export unavailable"
    try:
        descriptor = read(descriptor_path)
        if (descriptor["terminal"] != baseline["terminal"]
                or descriptor["input_sha256"] != case["input"]["sha256"]):
            raise ValueError("Observation export differs from paired baseline")
        name = descriptor["case"] + "/observations.json"
        path = Path(descriptor["root"]) / name
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != descriptor["files"][name]:
            raise ValueError("Exported observation bytes changed")
        observations = read(path)
        ids = [row["observation_id"] for row in observations]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate exported observation identity")
        return len(ids), None
    except (OSError, ValueError, KeyError, TypeError) as error:
        return None, f"{type(error).__name__}: {error}"


def rows_for_case(case, folder, truth, *, frozen_release_verified):
    """Represent every arm even if inference never produced a position."""
    base = optional(folder / "baseline-receipt.json")
    recovery = optional(folder / "candidate-receipt.json")
    available_observations, denominator_failure = observation_denominator(case, folder, base)
    terminal_path = Path(recovery["terminal_path"]) if recovery and recovery.get("terminal_path") else folder / "algo03/terminal.json"
    terminal = optional(terminal_path)
    base_state = base["state"] if base else "missing"
    base_terminal = base.get("terminal", {}) if base else {}
    base_seconds = base_terminal.get("elapsed_seconds", base.get("seconds", 0)) if base else 0
    candidate_state = recovery["state"] if recovery else "missing"
    added_seconds = recovery.get("seconds", 0) if recovery else 0
    candidate_seconds = base_seconds + added_seconds
    selected = terminal.get("selected") if terminal else None
    changed = bool(terminal and terminal.get("decision") != "ALGO02_fallback" and selected)
    proof_failure = None
    if terminal and terminal.get("schema_version") == 2:
        try:
            from leo.contracts.fast_graph_position_v2 import validate_terminal
            validate_terminal(terminal, input_sha256=case["input"]["sha256"])
            if candidate_state == "complete" and terminal["state"] != "complete":
                raise ValueError("Candidate receipt contradicts its terminal state")
            if terminal["baseline"] != base_terminal:
                raise ValueError("Candidate embeds another ALGO02 comparator")
            if changed:
                from algo03_production_worker import verify_selected
                if verify_selected(terminal, terminal_path.parent / "recovery") != terminal["rf_checks"]:
                    raise ValueError("Candidate scientific proof checks changed")
        except (ValueError, OSError, KeyError, TypeError) as error:
            proof_failure = f"{type(error).__name__}: {error}"
            candidate_state = "failed"
    elif changed or candidate_state == "complete":
        proof_failure = "Candidate lacks the deployed version-two envelope"
        candidate_state = "failed"
    if candidate_state == "complete" and not terminal:
        candidate_state = "failed"
    baseline_clean = bool(base_terminal.get("read_audit", {}).get("all_launched_processes_accounted")
                          and base_terminal["read_audit"].get("denied_paths") == [])
    recovery_clean = bool(terminal and (terminal.get("read_audit") or {}).get("verified"))
    published_clean = recovery_clean if changed else baseline_clean
    candidate_provenance = (not changed or bool(terminal and terminal.get("schema_version") == 2 and
                            terminal.get("matched_c_inputs") is True and
                            terminal.get("future_TLE_used") is False and
                            terminal.get("reference_usage") == "none" and proof_failure is None))
    cohort = dict(job_id=case["case"], dataset=case["dataset"],
                  acquisition_mode="fast" if case["recording_format"] == "short_window_iq_recording" else "adaptive")
    rows = []
    for arm in ARMS:
        original = base_terminal.get("arms", {}).get(arm)
        candidate = selected["arms"][arm] if changed else original
        baseline = endpoint_result(base_state, original, base_seconds, truth, available_observations)
        result = endpoint_result(candidate_state, candidate, candidate_seconds, truth, available_observations)
        result["added_seconds"] = added_seconds
        row = dict(**cohort, arm=arm, baseline=baseline, candidate=result,
                   matched_c_inputs=base_terminal.get("matched_c_inputs") is True and candidate_provenance,
                   causal_only=base_terminal.get("future_TLE_used") is False and candidate_provenance,
                   no_GPS_inference=base_terminal.get("reference_usage") == "none" and candidate_provenance,
                   read_audit_verified=published_clean,
                   recovery_read_audit_verified=recovery_clean,
                   frozen_release_verified=frozen_release_verified,
                   decision=terminal.get("decision") if terminal else recovery.get("decision") if recovery else None,
                   baseline_reused_production=bool(base and base.get("reused_production")),
                   input_sha256=case["input"]["sha256"] if case.get("input") else None,
                   baseline_runtime_freeze_sha256=base.get("runtime_freeze_sha256") if base else None,
                   candidate_runtime_freeze_sha256=recovery.get("runtime_freeze_sha256") if recovery else None,
                   observation_denominator_failure=denominator_failure,
                   failure=proof_failure or (terminal.get("failure") if terminal else None) or
                           (recovery.get("reason") if recovery else "candidate receipt absent"),
                   baseline_reason=base_terminal.get("reason", base.get("reason") if base else None),
                   added_points=candidate.get("added_points", 0) if candidate else 0,
                   observation_sets_changed=changed,
                   frequency_objectives_comparable_across_algorithms=not changed)
        rows.append(row)
    return cohort, rows


def plot_report(rows, datasets, output):
    """Show common qualified pairs; retain full cohort panel counts explicitly."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures = {name: plt.subplots(len(datasets), 2, figsize=(11, 3.3 * len(datasets)),
                                 squeeze=False, constrained_layout=True)
               for name in ("error-cdf", "paired-error", "runtime")}
    counts = []
    for index, dataset in enumerate(datasets):
        for column, arm in enumerate(ARMS):
            members = [r for r in rows if r["dataset"] == dataset and r["arm"] == arm]
            pairs = [r for r in members if all(r[m]["state"] == "complete" and
                     r[m]["error_km"] is not None for m in ("baseline", "candidate"))]
            runtimes = [r for r in members if r["baseline"]["state"] == "complete" and
                        r["candidate"]["state"] == "complete"]
            counts.append(dict(dataset=dataset, arm=arm, cohort=len(members),
                               common_qualified_pairs=len(pairs), runtime_pairs=len(runtimes)))
            title = f"{dataset} · {arm} · {len(pairs)}/{len(members)} common pairs"
            ax = figures["error-cdf"][1][index, column]
            for model, label in (("baseline", "ALGO02"), ("candidate", "ALGO03")):
                errors = sorted(r[model]["error_km"] for r in pairs)
                if errors:
                    ax.step(errors, [(n + 1) / len(errors) for n in range(len(errors))],
                            where="post", label=label)
            ax.set(title=title, xlabel="Position error (km)", ylabel="Empirical CDF", ylim=(0, 1))
            if pairs:
                ax.legend()
            for name, field, selected, label in (
                    ("paired-error", "error_km", pairs, "Position error (km)"),
                    ("runtime", "total_seconds", runtimes, "Total processing time (s)")):
                ax = figures[name][1][index, column]
                x = [r["baseline"][field] for r in selected]
                y = [r["candidate"][field] for r in selected]
                ax.scatter(x, y, s=10, alpha=.55)
                maximum = max([*x, *y, 1]) * 1.04
                ax.plot([0, maximum], [0, maximum], color="gray", linestyle="--", linewidth=1)
                ax.set(title=title, xlabel="ALGO02 · " + label, ylabel="ALGO03 · " + label,
                       xlim=(0, maximum), ylim=(0, maximum))
            for _, axes in figures.values():
                axes[index, column].grid(alpha=.2)
    for name, (figure, _) in figures.items():
        figure.savefig(output / (name + ".png"), dpi=160)
        plt.close(figure)
    (output / "figure-denominators.json").write_text(json.dumps(counts, indent=2) + "\n")
    return counts


def verify_release(runtime):
    manifest = runtime / "reports/ALGO03/releases/2026-10-30-r1/manifest.json"
    if not manifest.exists():
        return False
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != RELEASE_MANIFEST_SHA256:
        return False
    for relative, expected in read(manifest)["sha256"].items():
        path = runtime / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected.removeprefix("sha256:"):
            return False
    return True


def run(args):
    if args.output.exists():
        raise ValueError("Refusing to overwrite an evaluation report")
    args.output.mkdir(parents=True)
    verified = verify_release(args.study / "runtime-candidate")
    amendment = optional(args.study / "scope-amendment-fast-only.json")
    allowed = set(amendment["members"]) if amendment else None
    cohort, rows = [], []
    for dataset in args.datasets:
        document = read(args.study / "datasets" / (dataset + ".json"))
        for case in document["cases"]:
            if allowed is not None and case["case"] not in allowed:
                continue
            item, case_rows = rows_for_case(case, args.study / "cases" / case["case"], args.truth,
                                            frozen_release_verified=verified)
            cohort.append(item)
            rows.extend(case_rows)
    result = qualify(cohort, rows)
    plot_report(rows, args.datasets, args.output)
    evidence = dict(evaluation_reference=list(args.truth), evaluation_only=True,
                    scope_amendment=amendment,
                    full_member_denominators=True, frequency_objectives_separate_from_accuracy=True,
                    cohort=cohort, rows=rows)
    (args.output / "evidence.json").write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    (args.output / "qualification.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    flat = []
    for row in rows:
        item = {k: v for k, v in row.items() if k not in {"baseline", "candidate"}}
        for model in ("baseline", "candidate"):
            item.update({model + "_" + k: v for k, v in row[model].items()})
        flat.append(item)
    with (args.output / "positions.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    lines = ["# ALGO03 versus production ALGO02: fast-scan evaluation" if amendment else
             "# ALGO03 versus production ALGO02: whole-dataset evaluation", "",
             f"Promotion criteria: **{'pass' if result['passed'] else 'not met'}**. "
             f"All {len(cohort)} acquisitions remain in the denominator; both c arms are reported.", "",
             "| Dataset | Arm | ALGO02 / ALGO03 qualified | ALGO02 mean / median km | ALGO03 mean / median km |",
             "| --- | --- | --- | --- | --- |"]
    if amendment:
        lines[2] += " Adaptive recordings are excluded by explicit user instruction; original dataset manifests are unchanged."
    def value(number):
        return "unavailable" if number is None else f"{number:.3f}"
    for dataset in args.datasets:
        for arm in ARMS:
            saved = result["summaries"]["dataset:" + dataset][arm]
            base, candidate = saved["baseline"], saved["candidate"]
            lines.append(f"| {dataset} | {arm} | {saved['baseline_complete']} / {saved['candidate_complete']} "
                         f"of {saved['cohort_count']} | {value(base['mean_km'])} / {value(base['median_km'])} "
                         f"| {value(candidate['mean_km'])} / {value(candidate['median_km'])} |")
    lines += ["", "Mean, median and tails use common qualified pairs. Coverage uses every acquisition. "
              "Missing inputs and execution failures have no invented position error. ALGO03 fallback positions "
              "equal their ALGO02 comparator; recovery time is still added to original ALGO02 runtime.", "",
              "Geographic truth enters only this reporting tool. Frequency RMS and raw objectives remain in "
              "positions.csv; objectives from different observation sets are not treated as localization improvements.", "",
              "Association counts use each published arm's explicit observation identities. Percentages use "
              "all unique GLRT observations in the hash-verified paired public export; an unavailable export "
              "leaves the denominator and percentage blank.", "",
              "![Position error CDF by dataset and c arm](error-cdf.png)", "",
              "![Paired position errors](paired-error.png)", "",
              "![Baseline and total candidate runtimes](runtime.png)", "",
              "[Exact figure denominators](figure-denominators.json)", "",
              f"The evaluation reference is {list(args.truth)}. All datasets are from that user-confirmed site; "
              "these results do not establish accuracy at a different site.", "",
              "[All positions and failures](positions.csv) · [Exact rows and provenance](evidence.json) · "
              "[Predeclared qualification criteria and every failed gate](qualification.json)", ""]
    (args.output / "README.md").write_text("\n".join(lines))
    print(json.dumps(dict(cohort=len(cohort), arms=len(rows), passed=result["passed"],
                          failed_gates=len(result["failures"]))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--datasets", nargs="+", default=["DS23", "DS24", "DS26"])
    parser.add_argument("--truth", nargs=2, type=float, required=True)
    run(parser.parse_args())
