from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("dense_hybrid_combined")


def test_same_cutoff_producer_requires_original_archive_authority_and_all_bodies(trial):
    source = dict(archive="digest", authority="record", cutoff_utc_ns=123, body_digests=["a", "b"])
    request = dict(archive={"snapshots_sha256": "digest"}, authority="record", cutoff_utc_ns=123)
    assert trial.compatible_producer(source, request, ["b", "a", "a"])
    assert not trial.compatible_producer(source, request, ["a"])
    assert not trial.compatible_producer(dict(source, cutoff_utc_ns=124), request, ["a", "b"])
    assert not trial.compatible_producer(dict(source, authority="other"), request, ["a", "b"])


def test_first_use_charges_the_full_producer_process(trial):
    saved = dict(elapsed_s=22., cpu_s=21.)
    producer = dict(elapsed_s=4.5, cpu_s=4.4)
    raw = dict(acquire_cpu_s=32., acquire_wall_s=60., dense_compressed_MB=8100.)
    priced = trial.budgets(saved, producer, raw)
    assert priced["first_use_serial_saved_elapsed_s"] == 26.5
    assert priced["first_use_serial_saved_cpu_s"] == 25.4
    assert priced["first_use_required_acquire_MBps"] > priced["already_built_required_acquire_MBps"]
