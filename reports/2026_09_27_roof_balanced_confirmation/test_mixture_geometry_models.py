from dataclasses import asdict
import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

import mixture_calibration_inputs as adapter
import mixture_geometry_models as geometry
import mixture_reception_core as core
import model_eval


HERE = Path(__file__).resolve().parent


def endpoint(row, east):
    channel, edge = row.channel_edge.split(":", 1)
    return {"session_id": row.session_id, "split": "cal",
            "track_id": row.track_id, "receiver_id": row.receiver_id,
            "channel": channel, "edge": edge,
            "sample_rate_hz": row.sample_rate, "anchor_margin": row.anchor_margin,
            "matched": row.matched,
            "log_margin_ratio_rx1_rx0": row.log_ratio if row.matched else None,
            "east": float(east), "up": 0.}


def theta(source):
    return np.asarray(source["coefficients"]["detection"] +
                      source["coefficients"]["ratio"] +
                      [source["log_sigma"]], float)


def test_real_all_rows_all_candidates_match_direct_core_tensors():
    bundle = geometry.load_geometry_bundle()
    tracks, _receipt = adapter.load_joined()
    payload = json.loads((HERE / "mixture_calibration_polished.json").read_text())
    full = payload["descriptive_full_six"]
    schema = adapter.FeatureSchema(**{
        key: tuple(value) if isinstance(value, list) else value
        for key, value in full["feature_schema"].items()})
    assert sum(len(track.rows) for track in tracks) == 6378
    for arm in geometry.ARMS:
        built, layout, _names = adapter.build_arm(tracks, schema, arm, core)
        source = full["models"][arm]
        parameter = theta(source)
        pd = layout.detection_size
        pr = layout.ratio_size
        detection_rows = []
        ratio_rows = []
        direct_logits = []
        direct_ratio = []
        for joined, tensor in zip(tracks, built, strict=True):
            weights = np.exp(joined.log_weights)
            for candidate in range(3):
                for index, row in enumerate(joined.rows):
                    east = (row.east[candidate] if arm == "mixture"
                            else float(weights @ row.east))
                    value = endpoint(row, east)
                    detection_rows.append(value); ratio_rows.append(value)
                    direct_logits.append(float(
                        tensor.detection_design[candidate, index] @ parameter[:pd]))
                    direct_ratio.append(float(
                        tensor.ratio_design[candidate, index] @ parameter[pd:pd + pr]))
        exported = bundle.models[arm]
        probability = model_eval.predict(exported.detection, detection_rows)
        exported_design = model_eval._design(
            detection_rows, exported.detection.outcome,
            exported.detection.direction, template=exported.detection)[0]
        logits = exported_design @ np.asarray(exported.detection.coefficients)
        ratio = model_eval.predict(exported.ratio, ratio_rows)
        assert logits == pytest.approx(direct_logits, abs=2e-14)
        assert probability == pytest.approx(
            1. / (1. + np.exp(-np.asarray(direct_logits))), abs=2e-14)
        assert ratio == pytest.approx(direct_ratio, abs=2e-12)
        assert exported.ratio_variance == source["variance"]


def test_synthetic_direction_slopes_rx_sign_and_unseen_rate_reference():
    models = geometry.load_geometry_models()
    for exported in models.values():
        template = {"session_id": "s", "split": "cal", "track_id": "t",
                    "channel": "1", "edge": "lower",
                    "sample_rate_hz": "10000000", "anchor_margin": 1.,
                    "matched": True, "log_margin_ratio_rx1_rx0": 0., "up": 0.}
        dcoef = exported.detection.coefficients[
            exported.detection.feature_names.index("signed_east")]
        dscale = exported.detection.scales[
            exported.detection.numeric_names.index("signed_east")]
        rcoef = exported.ratio.coefficients[
            exported.ratio.feature_names.index("east")]
        rscale = exported.ratio.scales[
            exported.ratio.numeric_names.index("east")]
        for receiver, sign in (("rx0", 1.), ("rx1", -1.)):
            rows = [dict(template, receiver_id=receiver, east=east)
                    for east in (-1., 0., 1.)]
            probability = model_eval.predict(exported.detection, rows)
            logits = np.log(probability) - np.log1p(-probability)
            assert np.diff(logits) == pytest.approx([sign * dcoef / dscale] * 2)
            means = model_eval.predict(exported.ratio, rows)
            assert np.diff(means) == pytest.approx([rcoef / rscale] * 2)
        reference = dict(template, receiver_id="rx0", east=.2)
        unseen = dict(reference, sample_rate_hz="5000000")
        assert model_eval.predict(exported.detection, [reference, unseen])[0] == pytest.approx(
            model_eval.predict(exported.detection, [reference, unseen])[1])
        assert model_eval.predict(exported.ratio, [reference, unseen])[0] == pytest.approx(
            model_eval.predict(exported.ratio, [reference, unseen])[1])


def test_fitted_model_serialization_roundtrip():
    models = geometry.load_geometry_models()
    row = {"session_id": "s", "split": "cal", "track_id": "t",
           "receiver_id": "rx0", "channel": "2", "edge": "upper",
           "sample_rate_hz": "7500000", "anchor_margin": .5,
           "matched": True, "log_margin_ratio_rx1_rx0": .1,
           "east": -.3, "up": .8}
    for exported in models.values():
        for fitted in (exported.detection, exported.ratio):
            restored = model_eval.FittedModel(**json.loads(json.dumps(asdict(fitted))))
            assert model_eval.predict(restored, [row]) == pytest.approx(
                model_eval.predict(fitted, [row]))


def test_rejects_coefficient_shape_or_failed_gate():
    payload = json.loads((HERE / "mixture_calibration_polished.json").read_text())
    malformed = copy.deepcopy(payload)
    malformed["descriptive_full_six"]["models"]["mixture"][
        "coefficients"]["detection"].pop()
    with pytest.raises(ValueError, match="shape mismatch"):
        geometry.export_models(malformed)
    rejected = copy.deepcopy(payload)
    rejected["advancement_gate"]["advance"] = False
    with pytest.raises(ValueError, match="gates did not pass"):
        geometry.export_models(rejected)


def test_bundle_is_accepted_hash_bound_and_immutable_mapping():
    bundle = geometry.load_geometry_bundle()
    assert set(bundle.models) == {"mean", "mixture"}
    assert bundle.calibration_sha256.startswith("sha256:")
    with pytest.raises(TypeError):
        bundle.models["bad"] = bundle.models["mean"]
