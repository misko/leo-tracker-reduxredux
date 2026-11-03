"""Independent saved-artifact checks; imports neither experiment runner nor scorer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_hash(path, expected):
    assert digest(path) == expected.removeprefix("sha256:"), str(path)


def events(score, frequency, truth, threshold, step=4.4e-6):
    period = 1 / step
    error = abs((frequency - truth + period / 2) % period - period / 2)
    detected = score > threshold
    return detected, detected & (error <= 1000)


def simulation_audit():
    folder = HERE / "simulation/final"
    config = read(folder / "frozen_protocol.json")
    summary = read(folder / "summary.json")
    recommendation = read(folder / "frozen_recommendation.json")
    thresholds = read(folder / "frozen_thresholds.json")
    normalizers = read(folder / "frozen_normalizers.json")
    for item in (summary, recommendation, thresholds):
        check_hash(folder / "frozen_protocol.json", item["protocol_sha256"])
    for name, source in config["sources"].items():
        check_hash(Path(source["path"]), source["sha256"])
        check_hash(folder / "frozen_sources" / name, source["sha256"])
    methods = list(thresholds["thresholds"]["white"])
    members = config["union"]["members"]
    archive_count = 0

    def archive(name, environment):
        nonlocal archive_count
        with np.load(folder / f"{name}.npz") as saved:
            data = {key: saved[key] for key in saved.files}
        if name.startswith("normalization_"):
            archive_count += 1
            return data
        z = np.column_stack(
            [
                (data[f"{m}__score"] - normalizers[environment][m]["mean"])
                / normalizers[environment][m]["std"]
                for m in members
            ]
        )
        winner = z.argmax(axis=1)
        rows = np.arange(len(winner))
        np.testing.assert_allclose(data["multiscale_union__score"], z[rows, winner])
        member_cfo = np.column_stack([data[f"{m}__cfo_hz"] for m in members])
        np.testing.assert_array_equal(data["multiscale_union__cfo_hz"], member_cfo[rows, winner])
        np.testing.assert_array_equal(data["multiscale_union_cfo64__score"], z[rows, winner])
        np.testing.assert_array_equal(
            data["multiscale_union_cfo64__cfo_hz"], data["gaussian_coherent__cfo_hz"]
        )
        for method in methods:
            assert np.isfinite(data[f"{method}__score"]).all()
            assert np.isfinite(data[f"{method}__cfo_hz"]).all()
        archive_count += 1
        return data

    descriptive = {}
    for environment, norms in normalizers.items():
        data = archive(f"normalization_{environment}", environment)
        for member, norm in norms.items():
            np.testing.assert_allclose(norm["mean"], data[f"{member}__score"].mean())
            np.testing.assert_allclose(norm["std"], data[f"{member}__score"].std())
        calibration = archive(f"calibration_{environment}", environment)
        null = archive(f"heldout_null_{environment}", environment)
        descriptive[environment] = {}
        for method in methods:
            threshold = thresholds["thresholds"][environment][method]
            assert threshold == np.quantile(calibration[f"{method}__score"], 0.99, method="higher")
            assert (
                int((null[f"{method}__score"] > threshold).sum())
                == summary["null"][environment][method]["false_alarms"]
            )
            descriptive[environment][method] = float(
                np.quantile(null[f"{method}__score"], 0.99, method="higher")
            )

    dev_null = archive("development_null", "white")
    for method, threshold in recommendation["development_thresholds"].items():
        assert threshold == np.quantile(dev_null[f"{method}__score"], 0.99, method="higher")
    cell_events = {}
    signal_cells = 0
    for stage, cells in (
        ("development", recommendation["development"]),
        ("heldout", summary["signals"]),
    ):
        cell_events[stage] = {}
        for scenario, snrs in cells.items():
            environment = config["scenarios"][scenario]["environment"]
            for snr, cell in snrs.items():
                data = archive(f"{stage}_{scenario}_{snr}", environment)
                truth = np.load(folder / f"{stage}_{scenario}_{snr}_truth.npy")
                cell_events[stage][scenario, snr] = {}
                for method in methods:
                    options = [("development", recommendation["development_thresholds"][method])]
                    if stage == "heldout":
                        options = [
                            ("trained_threshold", thresholds["thresholds"][environment][method]),
                            ("descriptive_heldout_1pct", descriptive[environment][method]),
                        ]
                    for label, threshold in options:
                        detected, joint = events(
                            data[f"{method}__score"], data[f"{method}__cfo_hz"], truth, threshold
                        )
                        claimed = (
                            cell[method]
                            if stage == "development"
                            else cell["methods"][method][label]
                        )
                        assert int(detected.sum()) == claimed["detected"]
                        assert int(joint.sum()) == claimed["correct_detections"]
                        assert len(truth) == claimed["count"]
                        if label != "descriptive_heldout_1pct":
                            cell_events[stage][scenario, snr][method] = (detected, joint)
                if stage == "heldout":
                    with np.load(folder / f"decisions_{scenario}_{snr}.npz") as decisions:
                        for method, pair in cell_events[stage][scenario, snr].items():
                            for event_name, event in zip(("detected", "joint"), pair, strict=True):
                                np.testing.assert_array_equal(
                                    decisions[f"{method}__{event_name}"], event
                                )
                signal_cells += 1
    rule = config["selection_rule"]
    phase_cells = [
        (scenario, str(snr))
        for scenario in rule["primary_phase_scenarios"]
        for snr in config["snr_db"]
    ]
    eligible = []
    development = cell_events["development"]
    for method, item in recommendation["recommendation"]["candidates"].items():
        objective = np.mean([development[key][method][1].mean() for key in phase_cells])
        coherent = development["coherent", str(rule["coherent_constraint_snr_db"])]
        differences = {
            base: coherent[method][0].mean() - coherent[base][0].mean()
            for base in rule["coherent_constraint_baselines"]
        }
        passes = all(
            delta >= -rule["maximum_detection_regression"] for delta in differences.values()
        )
        assert bool(passes) == item["eligible"]
        np.testing.assert_allclose(objective, item["development_joint_objective"])
        for base, delta in differences.items():
            np.testing.assert_allclose(delta, item["coherent_detection_difference"][base])
        if passes:
            eligible.append((-objective, method))
    selected = min(eligible)[1] if eligible else None
    assert (
        selected == recommendation["recommendation"]["selected"] == thresholds["recommended_method"]
    )
    heldout = cell_events["heldout"]
    means = {m: float(np.mean([heldout[key][m][1].mean() for key in phase_cells])) for m in methods}
    for base, item in summary["selected_equal_weight_phase_joint_difference"].items():
        np.testing.assert_allclose(means[selected] - means[base], item["difference"])
    return {
        "archives_checked": archive_count,
        "signal_cells_checked": signal_cells,
        "methods": len(methods),
        "selected": selected,
        "heldout_phase_joint_rates": means,
        "source_and_snapshot_hashes_checked": 2 * len(config["sources"]),
    }


def planted_recovery(candidate, rate, config):
    injection = config["injections"]
    period = rate / 750
    distance = abs(candidate["epoch_sample"] - injection["epoch_sample"]) % period
    distance = min(distance, period - distance)
    frequency_error = abs(
        candidate["seed_cfo_hz"] + candidate.get("cfo_hz", 0.0) - injection["cfo_hz"]
    )
    timing = distance <= rate * config["epoch_recovery_tolerance_s"]
    cfo = frequency_error <= config["cfo_recovery_tolerance_hz"]
    return {
        "epoch_error_samples": distance,
        "cfo_error_hz": frequency_error,
        "timing_recovered": timing,
        "cfo_recovered": cfo,
        "joint_recovered": timing and cfo,
    }


def recorded_audit():
    folder = HERE / "recorded"
    results = read(folder / "results.json")
    provenance = read(folder / "provenance.json")
    selection = read(folder / "selection.json")
    config = selection["config"]
    check_hash(folder / "matrices.npz", results["matrices_sha256"])
    check_hash(folder / "provenance.json", results["provenance_sha256"])
    check_hash(folder / "selection.json", provenance["selection_sha256"])
    for name, expected in provenance["sources"].items():
        check_hash(ROOT / name, expected)
    dataset = ROOT / "reports/2026_09_26_ds5_server_eval/dataset"
    check_hash(dataset / "cases.json", selection["manifest_sha256"])
    for case in selection["cases"]:
        check_hash(dataset / case["raw_npy"]["path"], case["raw_npy"]["sha256"])
    comparisons = 0
    for row in results["raw"] + results["injected"]:
        bank = {c["candidate_id"]: c for c in row["candidate_bank"]}
        for aperture in row["scores"].values():
            for result in aperture.values():
                ranking = result["ranking"]
                assert result["winner"] == ranking[0]
                assert sorted(c["candidate_id"] for c in ranking) == sorted(bank)
                assert all(
                    a["score"] >= b["score"]
                    for a, b in zip(ranking, ranking[1:], strict=False)
                )
                for candidate in ranking:
                    assert all(
                        candidate[key] == value
                        for key, value in bank[candidate["candidate_id"]].items()
                    )
                winner = result["winner"]
                confirmation = result["confirmation_fixed_timing_frequency"]
                np.testing.assert_allclose(
                    confirmation["total_cfo_hz"], winner["seed_cfo_hz"] + winner["cfo_hz"]
                )
                assert confirmation["cfo_hz"] == confirmation["control_cfo_hz"] == winner["cfo_hz"]
                if "recovery" in result:
                    assert planted_recovery(winner, row["rate_hz"], config) == result["recovery"]
                    assert (
                        any(
                            planted_recovery(c, row["rate_hz"], config)["joint_recovered"]
                            for c in ranking
                        )
                        == result["retained_estimate_oracle_recovery"]
                    )
                comparisons += 1
        if "pattern" in row:
            grid = np.fft.fftfreq(config["fft_size"], d=config["symbol_step_s"])
            survival = [planted_recovery(c, row["rate_hz"], config) for c in bank.values()]
            assert any(c["timing_recovered"] for c in survival) == row["planted_timing_in_bank"]
            assert (
                any(c["joint_recovered"] for c in survival)
                == row["planted_seed_timing_cfo_in_bank"]
            )
            reachable = any(
                s["timing_recovered"]
                and np.min(abs(c["seed_cfo_hz"] + grid - config["injections"]["cfo_hz"]))
                <= config["cfo_recovery_tolerance_hz"]
                for c, s in zip(bank.values(), survival, strict=True)
            )
            assert bool(reachable) == row["planted_timing_cfo_grid_reachable"]
    return {
        "raw_cases": len(results["raw"]),
        "injected_cases": len(results["injected"]),
        "method_aperture_rankings_checked": comparisons,
        "input_files_hashed": len(selection["cases"]),
    }


if __name__ == "__main__":
    result = {"simulation": simulation_audit(), "recorded": recorded_audit(), "passed": True}
    result["audit_source_sha256"] = digest(Path(__file__))
    (HERE / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
