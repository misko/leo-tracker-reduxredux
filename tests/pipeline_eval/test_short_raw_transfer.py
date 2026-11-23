from hashlib import sha256
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def driver(monkeypatch):
    report = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(report))
    return import_module("short_raw_0180")


def test_transfer_source_identity_accepts_recorded_and_integrated_builds(driver):
    observed = sha256(driver.BOOTSTRAP.read_bytes()).hexdigest()
    assert driver.proof_sources(observed)[driver.BOOTSTRAP.name] == observed
    assert driver.proof_sources(driver.PROOF_SOURCES[driver.BOOTSTRAP.name]) == driver.PROOF_SOURCES
    with pytest.raises(ValueError, match="Unreviewed"):
        driver.proof_sources("0" * 64)


def test_transfer_keeps_the_base_options_and_changes_only_the_new_case(driver):
    assert driver.LEGACY.id == "DS30-0180"
    assert driver.LEGACY.order == ("stock", "candidate")
    assert driver.candidate_flags(driver.LEGACY) == ("--prove-empty-graph", "--one-pass-web-png")
    assert driver.TRANSFER.id == "DS30-0102"
    assert driver.TRANSFER.order == ("candidate", "stock")
    assert driver.candidate_flags(driver.TRANSFER) == (*driver.FLAGS, "--prove-graph-time-support")
    assert (driver.TRANSFER.windows, driver.TRANSFER.snapshots) == (124, 51)


def test_causal_staging_preserves_signed_aliases_with_one_copy(driver, tmp_path):
    source = tmp_path / "source/archive/space-track"
    source.mkdir(parents=True)
    body = b"same snapshot"
    names = {name: sha256(body).hexdigest() for name in ("1-a.tle", "2-a.tle")}
    for name in names:
        (source / name).write_bytes(body)
    target = tmp_path / "target"
    proof = driver.stage_orbits(target, source.parents[1], names, 3, expected_count=2)
    assert proof == dict(snapshots=2, unique=1, copied_bytes=len(body), logical_bytes=2 * len(body))
    staged = target / "archive/space-track"
    a, b = (staged / name for name in names)
    assert a.read_bytes() == b.read_bytes() == body
    assert a.stat().st_ino == b.stat().st_ino


def test_causal_staging_rejects_over_budget_or_future_before_copy(driver, tmp_path, monkeypatch):
    source = tmp_path / "source/archive/space-track"
    source.mkdir(parents=True)
    body = b"abcde"
    names = {"3-a.tle": sha256(body).hexdigest()}
    (source / "3-a.tle").write_bytes(body)
    target = tmp_path / "target"
    with pytest.raises(ValueError, match="Invalid causal orbit"):
        driver.stage_orbits(target, source.parents[1], names, 3, expected_count=1)
    monkeypatch.setattr(driver, "ORBIT_LIMIT", len(body) - 1)
    with pytest.raises(ValueError, match="exceeds"):
        driver.stage_orbits(target, source.parents[1], names, 4, expected_count=1)
    assert not target.exists()


def test_warming_rejects_signed_overruns_and_checks_exact_member_bytes(
    driver, tmp_path, monkeypatch
):
    triage = import_module("triage_bounds")
    member = tmp_path / "iq.zst"
    member.write_bytes(b"abcde")
    reader = SimpleNamespace(
        manifest_sha256="sha256:manifest",
        path=tmp_path,
        manifest=SimpleNamespace(
            chunks=[SimpleNamespace(payload_relative_path=member.name, compressed_bytes=5)]
        ),
    )
    monkeypatch.setattr(triage, "ShortWindowReader", lambda path: reader)
    input_manifest = [(tmp_path / "manifest.json", "sha256:manifest")]
    assert triage.warm_recording(input_manifest, maximum_bytes=5) == 5
    with pytest.raises(ValueError, match="conditioning budget"):
        triage.warm_recording(input_manifest, maximum_bytes=4)
    member.write_bytes(b"abcdef")
    with pytest.raises(ValueError, match="signed byte count"):
        triage.warm_recording(input_manifest, maximum_bytes=5)


def test_publication_seal_covers_both_terminal_output_trees(driver, tmp_path):
    for name in (
        "admission.json",
        "offer.json",
        "candidate-clock.json",
        "candidate.stdout",
        "candidate.stderr",
        "stock-clock.json",
        "stock.stdout",
        "stock.stderr",
    ):
        (tmp_path / name).write_bytes(name.encode())
    for mode in driver.TRANSFER.order:
        (tmp_path / mode).mkdir()
        (tmp_path / mode / "terminal.json").write_bytes(mode.encode())
    sealed = driver.output_digests(tmp_path, driver.TRANSFER.order)
    (tmp_path / "candidate" / "terminal.json").write_bytes(b"changed")
    current = driver.output_digests(tmp_path, driver.TRANSFER.order)
    assert {name for name, digest in sealed.items() if current[name] != digest} == {
        "candidate/terminal.json"
    }
