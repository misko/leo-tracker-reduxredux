"""Posthoc four-case description using saved receipts; no RF or position fits.

The case panel was fixed for its known development outcomes. These diagnostics
never provide covariance inputs, classifier features or acceptance thresholds.
"""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
OLD = ROOT.parents[1]/"2026_11_02_generalized_corrections"
CASES = ("DS26-0309", "DS26-0307", "DS26-0315", "FRSH-0004")
MODES = ("mean_motion", "inclination", "RAAN")


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decompose(coefficients):
    """Population identity, not a claim of independent sample covariance."""
    a = np.asarray(coefficients, float)
    mean = a.mean(axis=0)
    centered = a-mean
    spread = centered.T@centered/len(a)
    second = a.T@a/len(a)
    bias = np.outer(mean, mean)
    if not np.allclose(second, spread+bias, atol=1e-12, rtol=1e-12):
        raise ValueError("Second moment decomposition failed")
    trace = float(np.trace(second))
    return mean, spread, second, dict(
        squared_mean_trace=float(mean@mean), centered_spread_trace=float(np.trace(spread)),
        second_moment_trace=trace, squared_mean_trace_fraction=float(mean@mean/trace) if trace else None)


def csv_write(path, rows):
    with Path(path).open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def saved_phase_order(native):
    """Recover the sorted original graph label order without rebuilding a fit."""
    inventory = read(native["inventory_path"])
    job = inventory["job"]
    source = Path(job["root"])/"family_cavity/position"/(job["case"]+".json")
    baseline = read(source)
    node = baseline["selected"]["node"] if baseline["accepted"] else baseline["baseline_node"]
    labels = {}
    for row in node["seed"]["rows"]:
        if row["active_curvature"]:
            j, n = row["candidate_index"], row["candidate_norad"]
            if j in labels and labels[j] != n:
                raise ValueError("Saved graph candidate number mismatch")
            labels[j] = n
    return [labels[j] for j in sorted(labels)], dict(path=str(source), sha256=sha(source))


def main():
    paths = dict(combined=OLD/"evaluation/combined_results.json", roster=OLD/"evaluation/rf_roster.json",
                 inventory=OLD/"covariance/derived_inventory.json", positions=OLD/"position_results.csv")
    records = {r["case"]:r for r in read(paths["combined"])["rows"]}
    roster = {r["case"]:r for r in read(paths["roster"])["cases"]}
    inventory = {r["case"]:r for r in read(paths["inventory"])["rows"]}
    positions = {(r["case"],r["arm"],r["method"]):r for r in csv.DictReader(paths["positions"].open())}
    outputs, summaries, history_rows, arm_rows = [], [], [], []
    for case in CASES:
        record = records[case]
        receipt = record["prior_receipt"]
        source = inventory[case]
        if (receipt["selected_family"] != source["selected_family"]
                or not np.allclose(receipt["coefficient_covariance"], source["coefficient_covariance"], atol=1e-12)):
            raise ValueError("Inventory metadata does not describe runtime covariance")
        native = read(roster[case]["input_path"])
        phase_order, phase_source = saved_phase_order(native)
        midpoint = receipt["common_epoch_utc_ns"][1]
        nominal_age = (midpoint-receipt["nominal_epoch_utc_ns"])/3.6e12
        historical = receipt["historical_projection"]
        a = np.asarray([r["coefficients"] for r in historical])
        mean, spread, second, decomposition = decompose(a)
        if not np.allclose(second, receipt["second_moment"], atol=1e-12):
            raise ValueError("Saved historical coefficients differ from runtime second moment")
        covariance = np.asarray(receipt["coefficient_covariance"])
        eigen, vectors = np.linalg.eigh(covariance)
        unbounded, raw_vectors = np.linalg.eigh(.5*np.eye(3)+.5*second)
        scales = source["mode_metadata"]
        sigma = np.asarray([scales["mean_motion_sigma_rev_day"], scales["inclination_sigma_deg"], scales["raan_sigma_deg"]])
        ages = [(midpoint-r["epoch_utc_ns"])/3.6e12 for r in historical]
        direction = np.diag(second)/np.trace(second)
        summary = dict(case=case, target_family=receipt["selected_family"], historical_epochs=len(a),
            nominal_age_h=nominal_age, mean_historical_age_h=float(np.mean(ages)),
            minimum_historical_age_h=min(ages), maximum_historical_age_h=max(ages),
            mean_extra_historical_age_h=float(np.mean(ages)-nominal_age),
            squared_mean_trace_fraction=decomposition["squared_mean_trace_fraction"],
            maximum_unbounded_covariance_eigenvalue=float(unbounded[-1]),
            maximum_bounded_covariance_eigenvalue=float(eigen[-1]),
            upper_capped_directions=int(np.sum(unbounded>16+1e-10)),
            lower_floored_directions=int(np.sum(unbounded<1-1e-10)),
            represented_state_energy_fraction=receipt["represented_energy_fraction"])
        for k, mode in enumerate(MODES):
            summary[mode+"_signed_mean_standardized"] = float(mean[k])
            summary[mode+"_centered_SD_standardized"] = float(np.sqrt(spread[k,k]))
            summary[mode+"_second_moment_trace_fraction"] = float(direction[k])
            summary[mode+"_incumbent_physical_SD"] = float(sigma[k])
            summary[mode+"_signed_mean_physical"] = float(mean[k]*sigma[k])
        for item, age in zip(historical, ages):
            history_rows.append(dict(case=case, target_family=receipt["selected_family"], historical_age_h=age,
                epoch_utc_ns=item["epoch_utc_ns"], alignment_s=item["alignment_s"],
                mean_motion=item["coefficients"][0], inclination=item["coefficients"][1], RAAN=item["coefficients"][2]))
        arms = {}
        for arm in ("c0", "fitted_c"):
            A = record["variants"]["A"]["raw_endpoints"][arm]
            B = record["variants"]["A+B"]["raw_endpoints"][arm]
            pa = np.asarray(A["history"][-1]["posterior_phase"])
            pb = np.asarray(B["history"][-1]["posterior_phase"])
            if pa.shape != pb.shape:
                raise ValueError("Saved phase vectors use different orders")
            label_order = phase_order
            labels_known = len(label_order) == len(pa) and all(
                c["norad"] in label_order for c in A["exact_checks"])
            target_index = label_order.index(receipt["selected_family"]) if labels_known else None
            target_delta = float((pb-pa)[target_index]) if labels_known else None
            ap, bp = positions[(case,arm,"A")], positions[(case,arm,"A+B")]
            selected_A = record["variants"]["A"]["selected_output"][arm]
            selected_A_x = selected_A.get("x", native["baseline_arms"][arm]["endpoint_east_north_km"])
            arms[arm] = dict(
                saved_A_qualified=A["qualified"], saved_B_qualified=B["qualified"],
                A_policy_accepted=record["variants"]["A"]["accepted"], A_selected_source=selected_A["source"],
                candidate_movement_from_selected_A_km=float(np.linalg.norm(np.asarray(B["x"])-selected_A_x)),
                raw_A_movement_from_selected_A_km=float(np.linalg.norm(np.asarray(A["x"])-selected_A_x)),
                raw_A_to_B_curved_RMS_change_hz=B["rms_hz"]-A["rms_hz"],
                phase_norad_order=label_order if labels_known else None,
                phase_label_source=phase_source if labels_known else None,
                phase_vector_A_s=pa.tolist(), phase_vector_B_s=pb.tolist(),
                phase_vector_change_s=(pb-pa).tolist(),
                maximum_absolute_phase_change_s=float(max(abs(pb-pa))),
                target_phase_change_s=target_delta,
                saved_mode_posterior_available=False, saved_receiver_posterior_available=False,
                mode_posterior=None, receiver_posterior=None,
                posthoc_A_position_error_m=float(ap["error_m"]),
                posthoc_B_position_error_m=float(bp["error_m"]),
                posthoc_position_error_change_m=float(bp["error_m"])-float(ap["error_m"]))
            arm_rows.append(dict(case=case, arm=arm, **{k:v for k,v in arms[arm].items()
                if not isinstance(v,(dict,list))}))
        summaries.append(summary)
        outputs.append(dict(case=case, summary=summary, historical_signed_mean=mean.tolist(),
            centered_population_spread=spread.tolist(), squared_mean_component=np.outer(mean,mean).tolist(),
            uncentered_second_moment=second.tolist(), decomposition=decomposition,
            incumbent_mode_physical_SD=sigma.tolist(), physical_units=["rev/day","deg","deg"],
            covariance=covariance.tolist(), covariance_eigenvalues=eigen.tolist(),
            covariance_eigenvectors_columns=vectors.tolist(), unbounded_covariance_eigenvalues=unbounded.tolist(),
            unbounded_principal_direction=raw_vectors[:,-1].tolist(), arms=arms,
            native_input_sha256=sha(roster[case]["input_path"]),
            covariance_history_sha256=receipt["history_sha256"],
            nominal_epoch_utc_ns=receipt["nominal_epoch_utc_ns"],
            RF_cutoff_utc_ns=native["scan_receipt"]["cutoff_utc_ns"]))
    packet = dict(posthoc_development_panel=True, fixed_cases=list(CASES),
        old_RF_and_published_position_outcomes_used_for_description=True,
        new_covariance_construction_or_selection=False, new_RF_or_position_fits=False,
        classifier_or_acceptance_rule_created=False,
        limitations="Four selected development cases; correlated historical revisions; standardized "
            "directions are not orthogonal physical energy. Squared mean is descriptive bias, not "
            "a justified orbit mean correction. Old mode/receiver posteriors were not persisted; "
            "none are reconstructed here.",
        inputs={name:dict(path=str(path),sha256=sha(path)) for name,path in paths.items()},
        source_sha256=sha(__file__),cases=outputs)
    (ROOT/"old_b_panel.json").write_text(json.dumps(packet,indent=2,allow_nan=False)+"\n")
    csv_write(ROOT/"old_b_panel_summary.csv", summaries)
    csv_write(ROOT/"old_b_panel_history.csv", history_rows)
    csv_write(ROOT/"old_b_panel_arms.csv", arm_rows)
    plot(outputs, history_rows)
    print(json.dumps(dict(cases=summaries, arm_diagnostics=arm_rows),indent=2))


def plot(cases, history):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2,2,figsize=(11,7),layout="constrained")
    for ax, result in zip(axes.flat, cases):
        case=result["case"];rows=sorted([r for r in history if r["case"]==case],key=lambda r:r["historical_age_h"])
        for mode,color in zip(MODES,["#2166ac","#1b9e77","#d95f02"]):
            ax.plot([r["historical_age_h"] for r in rows],[r[mode] for r in rows],"o-",label=mode,color=color)
        ax.axhline(0,color=".5",linewidth=.7)
        ax.axvline(result["summary"]["nominal_age_h"],color=".3",linestyle="--",linewidth=1,label="Nominal age")
        s=result["summary"]
        ax.set_title(f"{case}: signed-mean share {s['squared_mean_trace_fraction']:.1%}; cap directions {s['upper_capped_directions']}")
        ax.set_xlabel("Propagation age at observation midpoint (h)")
        ax.set_ylabel("Saved standardized history coefficient")
        ax.grid(alpha=.15)
    axes[0,0].legend(frameon=False,fontsize=8)
    fig.suptitle("Four selected development cases: historical spread includes signed differences",fontsize=13)
    for ext in ("png","pdf"):fig.savefig(ROOT/f"old_b_panel.{ext}",dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
