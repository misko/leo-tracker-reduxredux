"""Synthetic integration tests of the actual bounded prefit replay driver."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
import replay_prefit as driver

from leo.analysis.regional_position_fit import PositionFit
from leo.contracts.digests import canonical_digest


def setup_main(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "HERE", tmp_path)
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    plan = dict(
        source_sha256={},
        starts=["ordinary-coarse", "zero-timing"],
        solvers=["legacy", "bounded"],
        maximum_fits=4,
        fixed_position=True,
        maximum_seconds=20,
        maximum_iterations=600,
        maximum_bank_seconds=180,
        slope_half_width_hz_s=60,
        stationarity_threshold=0.001,
    )
    (tmp_path / "prefit-protocol.json").write_text(json.dumps(plan))
    (tmp_path / "published-v3.json").write_text(
        json.dumps(dict(manifest=dict(document={"session_id": "synthetic"})))
    )
    checkpoint = dict(
        checkpoints={
            "ordinary": dict(
                value={"unrelated": 1}, value_sha256=canonical_digest({"unrelated": 1})
            )
        }
    )
    (tmp_path / "verified-checkpoints.json").write_text(json.dumps(checkpoint))
    seed = np.array([4, -8, 1, 2, 3, 4, 5, 6, 7, 8.0])
    events = []

    def reconstruct(document, checkpoint):
        events.append("verified-objective")
        return object(), seed, dict(original_objective=123, reconstructed_objective=123)

    monkeypatch.setattr(driver, "reconstruct", reconstruct)
    monkeypatch.setattr(driver, "gradient_audit", lambda objective, vector: dict(synthetic=True))
    return plan, seed, events


def fake_fit(start):
    return PositionFit(start.copy(), 123, 5, 10, 0.0001, True, False, "synthetic", 1, 0.001)


def test_four_attempts_share_ordinary_provenance_and_exact_budgets(tmp_path, monkeypatch):
    _, seed, events = setup_main(tmp_path, monkeypatch)
    calls = []

    def legacy(objective, start, *, diagnostics, **options):
        assert events[0] == "verified-objective"
        calls.append(("legacy", start.copy(), options))
        fitted = fake_fit(start)
        start[:] = 999  # Driver must protect its shared ordinary seed and record.
        diagnostics["terminal"] = dict(vector=fitted.vector.tolist())
        return fitted

    def bounded(objective, start, **options):
        calls.append(("bounded", start.copy(), options))
        return fake_fit(start), {}

    monkeypatch.setattr(driver, "fit_position", legacy)
    monkeypatch.setattr(driver, "fit_bounded_position", bounded)
    original = seed.copy()
    driver.main()
    assert [c[0] for c in calls] == ["legacy", "bounded", "legacy", "bounded"]
    zero = original.copy()
    zero[7:] = 0
    for i, (_, initial, options) in enumerate(calls):
        np.testing.assert_array_equal(initial, original if i < 2 else zero)
        assert options == dict(
            fixed_position=True,
            slope_half_width_hz_s=60,
            maximum_seconds=20,
            maximum_iterations=600,
            rf_arm="fitted-c",
        )
    np.testing.assert_array_equal(seed, original)
    files = list((tmp_path / "prefit-attempts").glob("*.json"))
    assert len(files) == 4
    for path in files:
        row = json.loads(path.read_text())
        assert row["status"] == "complete"
        np.testing.assert_array_equal(row["initial_vector"][:2], original[:2])
        assert row["gradient_audits"]["returned"]["synthetic"]
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    driver.main()
    assert len(calls) == 4
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def test_failure_is_explicit_and_remaining_attempts_continue(tmp_path, monkeypatch):
    setup_main(tmp_path, monkeypatch)
    calls = []

    def legacy(objective, start, **options):
        calls.append("legacy")
        raise ValueError("synthetic failed prefit")

    def bounded(objective, start, **options):
        calls.append("bounded")
        return fake_fit(start), {}

    monkeypatch.setattr(driver, "fit_position", legacy)
    monkeypatch.setattr(driver, "fit_bounded_position", bounded)
    driver.main()
    assert len(calls) == 4
    rows = [json.loads(p.read_text()) for p in (tmp_path / "prefit-attempts").glob("*.json")]
    assert sum(r["status"] == "failed" for r in rows) == 2
    assert all("synthetic failed prefit" in r["error"] for r in rows if r["status"] == "failed")


@pytest.mark.parametrize("failure", ["objective", "source", "checkpoint", "budget"])
def test_verification_failures_prevent_every_fit(tmp_path, monkeypatch, failure):
    plan, _, _ = setup_main(tmp_path, monkeypatch)

    def forbidden_fit(*args, **kwargs):
        pytest.fail("Numerical fit must not start before verification")

    monkeypatch.setattr(driver, "fit_position", forbidden_fit)
    monkeypatch.setattr(driver, "fit_bounded_position", forbidden_fit)
    if failure == "objective":

        def reconstruct(*args):
            raise AssertionError("objective mismatch")

        monkeypatch.setattr(driver, "reconstruct", reconstruct)
    elif failure == "source":
        (tmp_path / "source.py").write_text("changed")
        plan["source_sha256"] = {"source.py": "0" * 64}
        (tmp_path / "prefit-protocol.json").write_text(json.dumps(plan))
    elif failure == "checkpoint":
        checkpoint = json.loads((tmp_path / "verified-checkpoints.json").read_text())
        checkpoint["checkpoints"]["ordinary"]["value_sha256"] = "wrong"
        (tmp_path / "verified-checkpoints.json").write_text(json.dumps(checkpoint))
    else:
        plan["maximum_fits"] = 5
        (tmp_path / "prefit-protocol.json").write_text(json.dumps(plan))
    with pytest.raises(AssertionError):
        driver.main()
    assert not (tmp_path / "prefit-attempts").exists()


def test_resume_rejects_foreign_attempt_digest(tmp_path, monkeypatch):
    setup_main(tmp_path, monkeypatch)
    (tmp_path / "prefit-attempts").mkdir()
    target = tmp_path / "prefit-attempts/ordinary-coarse-legacy.json"
    target.write_text(json.dumps(dict(protocol_sha256="foreign")))
    with pytest.raises(AssertionError):
        driver.main()
    assert json.loads(target.read_text())["protocol_sha256"] == "foreign"


def test_append_only_writer_preserves_existing_receipt(tmp_path):
    path = tmp_path / "receipt.json"
    driver.write(path, dict(proof=1))
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        driver.write(path, dict(proof=2))
    assert path.read_bytes() == before


def test_real_reconstruct_checks_objective_and_never_reads_reference(monkeypatch):
    class NoReference(dict):
        def __getitem__(self, key):
            if key.startswith("reference_"):
                pytest.fail("Reference information is evaluation-only")
            return super().__getitem__(key)

    source = SimpleNamespace(input_manifest_sha256="input", analysis_manifest_sha256="analysis")
    closed = []

    class Inputs:
        def __init__(self, path):
            pass

        def load(self, session_id):
            assert session_id == "synthetic"
            return source

        def close(self):
            closed.append(True)

    snapshot = SimpleNamespace(digest="tle", collected_utc_ns=100)

    class Archive:
        def __init__(self, path):
            pass

        def select_latest_before(self, cutoff):
            assert cutoff == 1_000_000_000_000 - 505_000_000_000
            return snapshot

        def read(self, selected):
            assert selected is snapshot
            return b"synthetic"

    prepared = SimpleNamespace(
        start_utc_ns=1_000_000_000_000, observations=object(), evidence_sha256="windows"
    )
    catalogue = SimpleNamespace(names=["STARLINK-synthetic"], satellite_numbers=np.array([100]))

    class Bank:
        numbers = np.array([100])

        def select(self, indices):
            np.testing.assert_array_equal(indices, [0])
            return self

    def build(*args, **kwargs):
        assert kwargs == dict(maximum_seconds=180)
        return Bank(), dict(synthetic=True)

    class Objective:
        value = 123.0

        def __init__(self, *args):
            pass

        def evaluate(self, seed):
            np.testing.assert_array_equal(seed, np.arange(10))
            return self.value, None, None

    monkeypatch.setattr(driver, "ScannerTrackingInputStore", Inputs)
    monkeypatch.setattr(driver, "TleArchiveReader", Archive)
    monkeypatch.setattr(driver, "prepare_position_windows", lambda value: prepared)
    monkeypatch.setattr(driver, "exclude_labelled_starlink_debris", lambda value: (value, []))
    monkeypatch.setattr(driver, "parse_element_sets", lambda value: catalogue)
    monkeypatch.setattr(driver, "build_regional_bank", build)
    monkeypatch.setattr(driver, "Hard60Objective", Objective)
    evidence = canonical_digest(dict(windows="windows", tle="tle", candidates=[100]))
    document = NoReference(
        session_id="synthetic",
        input_manifest_sha256="input",
        analysis_manifest_sha256="analysis",
        evidence_sha256=evidence,
        configuration=dict(prior={}),
        diagnostics=dict(
            snapshot_sha256="tle", snapshot_collected_utc_ns=100, bank=dict(retained_numbers=[100])
        ),
        reference_latitude_deg="forbidden",
        reference_longitude_deg="forbidden",
    )
    checkpoint = dict(
        point_key="ordinary",
        checkpoints={
            "b7-shared:ordinary": dict(
                value=dict(
                    result=dict(
                        bootstrap=dict(satellite_indices=[0]),
                        fits=dict(
                            V16=dict(
                                fit=dict(vector=list(range(10)), objective=123, stationarity=0.01)
                            )
                        ),
                    )
                )
            )
        },
    )
    _, seed, receipt = driver.reconstruct(document, checkpoint)
    np.testing.assert_array_equal(seed, np.arange(10))
    assert closed == [True]
    assert receipt["original_objective"] == receipt["reconstructed_objective"] == 123
    Objective.value = 124
    with pytest.raises(AssertionError):
        driver.reconstruct(document, checkpoint)
