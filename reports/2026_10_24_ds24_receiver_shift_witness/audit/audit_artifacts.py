"""Independent saved-artifact audit; no fit or geographic truth is read."""
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MODELS = ("baseline", "sharedRF50")
ARMS = ("c0", "fitted_c")
PRIMARY = str(float(np.sqrt(2.)))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def score_svd(raw, uncertainty, sigma):
    """SVD in observation space, independent of producer's normal equations."""
    b = raw / sigma
    left, singular, _ = np.linalg.svd(uncertainty / sigma[:, None], full_matrices=False)
    projection = left.T @ b
    remainder = b - left @ projection
    quadratic = float(remainder @ remainder + np.sum(projection**2 / (1 + singular**2)))
    logdet = float(2 * np.log(sigma).sum() + np.log1p(singular**2).sum())
    return dict(quadratic=quadratic, logdet=logdet,
                negative_twice_log_density=quadratic+logdet+len(raw)*np.log(2*np.pi),
                mean_prediction_RMS_hz=float(np.sqrt(np.mean(raw**2))))


def main():
    expected = read(HERE / "baseline_membership.json")["cases"]
    heldroot = ROOT / "heldout"
    protocol = read(heldroot / "protocol.json")
    assert protocol["input_manifest_sha256"] == digest(heldroot / "input_manifest.json")
    assert protocol["source_sha256"] == digest(heldroot / "heldout.py")
    for item in protocol["dependencies"]:
        assert digest(item["path"]) == item["sha256"], item["path"]
    manifest = read(heldroot / "input_manifest.json")
    maximum_score_difference = 0.
    vectors = fits = 0
    crossover_rows = []
    geometry_rows = []
    result_bindings = []
    maxima = dict(phase_refresh=0., Gamma_change=0., held_prior_crosscovariance=0., geometry_term_closure=0.)
    for case, original in expected.items():
        item = manifest[case]
        assert digest(original["baseline_path"]) == original["baseline_sha256"] == item["baseline_sha256"]
        assert item["measurement_binding_sha256"] == original["original_measurement_binding_sha256"]
        baseline = read(original["baseline_path"])
        branch = baseline["selected"]["node"] if baseline["accepted"] else baseline["baseline_node"]
        all_labels = sorted({r["candidate_index"] for r in branch["seed"]["rows"]})
        native_noise = item["inherited_full_RF_fixed_noise"]
        assert native_noise["extra_parameter_BIC_gain"] > 0
        by_family = {f["candidate_index"]: f for f in original["family_membership"]}
        all_curved = set().union(*(set(f["curved_observation_ids"]) for f in by_family.values()))
        all_predictive = set().union(*(set(f["predictive_observation_ids"]) for f in by_family.values()))
        all_ids = all_curved | all_predictive
        covered = []
        for fold in item["folds"]:
            held = set(fold["held_families"])
            expected_curved = set().union(*(set(by_family[j]["curved_observation_ids"]) for j in held))
            expected_predictive = set().union(*(set(by_family[j]["predictive_observation_ids"]) for j in held))
            expected_held = expected_curved | expected_predictive
            assert set(fold["curved_held_ids"]) == expected_curved
            assert set(fold["predictive_held_ids"]) == expected_predictive
            assert set(fold["curved_training_ids"]) == all_curved-expected_curved
            assert set(fold["predictive_training_ids"]) == all_predictive-expected_predictive
            assert set(fold["curved_training_ids"]+fold["predictive_training_ids"]) == all_ids-expected_held
            covered.extend(expected_held)
            result_path = heldroot / "results" / f"{case}_fold{fold['fold']}.json"
            saved = read(result_path)
            assert saved["status"] == "complete", saved
            assert saved["protocol_sha256"] == digest(heldroot / "protocol.json")
            assert saved["source_sha256"] == digest(heldroot / "heldout.py")
            assert saved["baseline_sha256"] == original["baseline_sha256"]
            assert saved["input_binding_sha256"] == original["original_measurement_binding_sha256"]
            assert set(saved["held_families"]) == held
            result_bindings.append(dict(path=str(result_path), sha256=digest(result_path)))
            assert set(saved["arms"]) == set(ARMS)
            for arm, data in saved["arms"].items():
                assert set(data["fits"]) == set(MODELS)
                for fit in data["fits"].values():
                    fits += 1
                    assert len(fit["history"]) == 5
                    assert fit["training_curved_points"] == len(all_curved-expected_curved)
                    assert fit["training_predictive_points"] == len(all_predictive-expected_predictive)
                    assert np.max(np.abs(fit["endpoint_east_north_km"])) <= 12.500001
                    maxima["phase_refresh"] = max(maxima["phase_refresh"], fit["final_phase_change_s"])
                    maxima["Gamma_change"] = max(maxima["Gamma_change"], fit["training_final_log_precision_change"])
                for predictor in MODELS:
                    for endpoint in MODELS:
                        vector = data["crossover"][predictor][endpoint]
                        assert digest(vector["artifact"]) == vector["artifact_sha256"]
                        with np.load(vector["artifact"]) as a:
                            raw, uncertainty, sigma = a["raw"], a["uncertainty"], a["native_sigma"]
                            ids, family = a["observation_ids"].tolist(), a["family"]
                            assert len(ids) == len(set(ids)) and set(ids) == expected_held
                            np.testing.assert_array_equal(sigma, [native_noise["per_observation_noise_sigma_hz"][oid] for oid in ids])
                            held_slots = [all_labels.index(j) for j in held]
                            np.testing.assert_array_equal(a["reference"][held_slots],
                                np.asarray(original["original_phase_prior_means_s"])[held_slots])
                            assert hashlib.sha256(canonical(ids)).hexdigest() == vector["observation_id_sha256"] == fold["held_ids_sha256"]
                            assert set(family) == held
                            np.testing.assert_array_equal(a["position"], data["fits"][endpoint]["endpoint_east_north_km"])
                            for j in held:
                                assert set(np.asarray(ids)[family == j]) == set(by_family[j]["curved_observation_ids"]+by_family[j]["predictive_observation_ids"])
                            for scale in protocol["sigma_sensitivity_multipliers"]:
                                calculated = score_svd(raw, uncertainty, sigma*scale)
                                declared = vector["scores"][str(scale)]
                                for key, value in calculated.items():
                                    difference = abs(value-declared[key])
                                    maximum_score_difference = max(maximum_score_difference, difference)
                                    assert difference < 1e-4, (case, arm, predictor, endpoint, key, difference)
                        prior = vector["prior_audit"]
                        assert prior["maximum_held_training_loading"] == 0
                        maxima["held_prior_crosscovariance"] = max(maxima["held_prior_crosscovariance"], prior["maximum_held_trained_crosscovariance"])
                        np.testing.assert_allclose(prior["held_phase_variance"], 1., atol=1e-12)
                        maxima["phase_refresh"] = max(maxima["phase_refresh"], vector["phase_refresh_changes_s"][-1])
                        vectors += 1
                        score = vector["scores"][PRIMARY]
                        crossover_rows.append(dict(case=case, fold=fold["fold"], arm=arm, predictor=predictor,
                            endpoint=endpoint, dimensions=score["dimensions"], **{k: score[k] for k in (
                                "negative_twice_log_density", "quadratic", "logdet", "mean_prediction_RMS_hz")}))
            assert saved["seconds"] < 240
        assert len(covered) == len(set(covered)) == len(all_ids)
        assert set(covered) == all_ids
        geometry_path = ROOT / "geometry" / f"{case}.json"
        geometry = read(geometry_path)
        assert geometry["source_sha256"] == digest(ROOT / "geometry" / "geometry.py")
        assert geometry["baseline_sha256"] == original["baseline_sha256"]
        assert digest(geometry["rf50_path"]) == geometry["rf50_sha256"]
        assert geometry["measurement_binding"] == original["original_measurement_binding_sha256"]
        for sealed in geometry["source_seals"]:
            assert digest(sealed["path"]) == sealed["sha256"]
        result_bindings.append(dict(path=str(geometry_path), sha256=digest(geometry_path)))
        contracts = {data["saved_endpoint_replay"]["factor_contract"]
            for values in geometry["arms"].values() for data in values["models"].values()}
        assert len(contracts) == 1
        for arm, values in geometry["arms"].items():
            for model, data in values["models"].items():
                path = data["path"]
                assert len(path) == 11
                np.testing.assert_allclose([point["alpha"] for point in path], np.linspace(0, 1, 11), atol=1e-15)
                for point in path:
                    closure = abs(sum(point["terms"].values())-point["negative_twice_elbo"])
                    maxima["geometry_term_closure"] = max(maxima["geometry_term_closure"], closure)
                    assert closure < 1e-6
                    assert point["phase_converged"] and point["Gamma_converged"]
                    assert point["predictive_calibration_max_difference"] <= 1e-12
                geometry_rows.append(dict(case=case, arm=arm, model=model,
                    displacement_km=values["displacement_km"],
                    normalized_loss_change=path[-1]["negative_twice_elbo"]-path[0]["negative_twice_elbo"],
                    RMS_change_hz=path[-1]["RMS_hz"]-path[0]["RMS_hz"],
                    terms_change={k:path[-1]["terms"][k]-v for k,v in path[0]["terms"].items()}))
    assert fits == protocol["expected_position_fits"] == 24
    assert vectors == protocol["expected_crossover_vectors"] == 48
    aggregates = []
    for case in expected:
        for arm in ARMS:
            score = {(pred, end):sum(r["negative_twice_log_density"] for r in crossover_rows
                if r["case"] == case and r["arm"] == arm and r["predictor"] == pred and r["endpoint"] == end)
                for pred in MODELS for end in MODELS}
            aggregates.append(dict(case=case, arm=arm,
                own_model_gain=score["baseline", "baseline"]-score["sharedRF50", "sharedRF50"],
                movement_gain_under_baseline=score["baseline", "baseline"]-score["baseline", "sharedRF50"],
                movement_gain_under_sharedRF50=score["sharedRF50", "baseline"]-score["sharedRF50", "sharedRF50"],
                predictor_gain_at_baseline=score["baseline", "baseline"]-score["sharedRF50", "baseline"],
                predictor_gain_at_sharedRF50=score["baseline", "sharedRF50"]-score["sharedRF50", "sharedRF50"]))
    output = dict(status="passed", source_sha256=digest(Path(__file__)), GPS_used=False,
        no_position_fitting=True, score_reconstruction="Independent observation-space SVD", position_fits=fits,
        covariance_vectors=vectors, sensitivity_scores=3*vectors,
        maximum_saved_score_reconstruction_difference=maximum_score_difference, maxima=maxima,
        results=result_bindings, primary_crossover_aggregates=aggregates,
        crossover_rows=crossover_rows, geometry_rows=geometry_rows)
    (HERE / "artifact_audit.json").write_text(json.dumps(output, indent=2)+"\n")
    print(json.dumps({k:v for k,v in output.items() if k not in ("results", "crossover_rows", "geometry_rows")}, indent=2))


if __name__ == "__main__":
    main()
