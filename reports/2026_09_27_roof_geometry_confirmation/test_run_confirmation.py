from types import SimpleNamespace

import pytest

import run_confirmation as runner


def test_confirmation_entries_match_frozen_four():
    entries, manifest_sha, inventory_sha = runner.confirmation_entries()
    assert len(entries) == 4
    assert len({entry["session_id"] for entry in entries}) == 4
    assert all(entry["ready"] and entry["pose_verified"] for entry in entries)
    assert manifest_sha == runner.FROZEN_MANIFEST_SHA256
    assert inventory_sha.startswith("sha256:")
    assert [entry["session_id"] for entry in entries] == list(runner.FROZEN_SESSION_IDS)


def test_confirmation_manifest_digest_fails_closed():
    with pytest.raises(ValueError, match="manifest digest changed"):
        runner.verify_manifest_digest(b"not the frozen manifest")


def test_frequency_configuration_is_digest_bound_and_converged():
    config, artifact_sha = runner.frozen_frequency()
    assert config["converged"] is True
    assert config["parameters"]["optimizer_success"] is True
    assert artifact_sha.startswith("sha256:")


def test_reception_configuration_is_deserialized_without_refitting(monkeypatch):
    monkeypatch.setattr(
        runner.base, "frozen_models_and_endpoints",
        lambda: pytest.fail("confirmation must not refit reception models"))
    detection, continuous, variance, bias, hashes = runner.frozen_reception()
    assert detection.outcome == "detection"
    assert continuous.outcome == "continuous"
    assert variance > 0 and bias == pytest.approx(2380.1434201757074)
    assert all(value.startswith("sha256:") for value in hashes.values())


def test_reception_input_retains_physical_pair_identity(monkeypatch):
    prepared = SimpleNamespace(tracks=[SimpleNamespace(
        track_id="track", observation_ids=["train", "reserve"],
        training_mask=[True, False])])
    rows = [{"track_id": "track", "observation_id": "reserve",
             "physical_pair_key": "pair", "anchor_key": "anchor",
             "receiver_id": "rx0", "matched": True}]
    adapted = {"track": [{"observation_index": 1, "matched": True}]}
    monkeypatch.setattr(runner.base, "reception_inputs", lambda *args: adapted)
    actual, receipt = runner.reception_inputs(prepared, rows, object(), object())
    assert actual["track"][0]["physical_pair_key"] == "pair"
    assert actual["track"][0]["anchor_key"] == "anchor"
    assert receipt == [{"track_id": "track", "observation_id": "reserve",
                        "anchor_key": "anchor", "physical_pair_key": "pair",
                        "receiver_id": "rx0", "matched": True}]


def test_confirmation_budget_is_frozen_before_loading(monkeypatch):
    monkeypatch.setattr(runner, "confirmation_entries", lambda: pytest.fail("loaded inputs"))
    with pytest.raises(ValueError, match="frozen at 160"):
        runner.run_scan(0, 159)
