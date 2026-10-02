"""Runtime-rate qualification tests; radio access is never implicit."""

import importlib.util
import sys
from collections import Counter
from pathlib import Path

import pytest


@pytest.fixture
def qualification(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "tools"))
    spec = importlib.util.spec_from_file_location(
        "qualify_adaptive_runtime_rate", root / "tools/qualify_adaptive_runtime_rate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("branch", range(4))
def test_quarter_probability_branches(qualification, monkeypatch, branch):
    def choice(serial, ordinal, domain, size):
        assert (serial, ordinal, domain, size) == ("radio", 42, "rate-1p25-quarter-v1", 4)
        return branch
    monkeypatch.setattr(qualification, "deterministic_uniform_choice", choice)
    assert qualification.proposed_rate("radio", 42) == (1_250_000 if branch == 0 else 2_500_000)


def test_reproducible_distribution(qualification):
    rates = [qualification.proposed_rate("radio", i) for i in range(12000)]
    assert rates == [qualification.proposed_rate("radio", i) for i in range(12000)]
    counts = Counter(rates)
    assert set(counts) == {1_250_000, 2_500_000}
    assert counts[1_250_000] / len(rates) == pytest.approx(0.25, abs=0.015)


@pytest.mark.hardware  # Optional deployed acquisition package; no RF access.
@pytest.mark.parametrize("rate", [1_250_000, 2_500_000])
def test_runtime_wire_roundtrip(qualification, rate):
    from pluto_plus.adaptive_scan import ScanSetup
    setup = qualification.build_setup(rate)
    assert setup.protocol_version == 2
    assert setup.source_rate_hz == setup.analog_bandwidth_hz == rate
    assert setup.rx_mask == 3
    assert setup.duration_ms == 10_000
    assert setup.dwell_ms == 120
    assert ScanSetup.unpack(setup.pack()) == setup


@pytest.mark.hardware  # Optional deployed acquisition package; no RF access.
def test_default_does_not_capture(qualification, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["qualification", "--output-root", str(tmp_path)])
    assert qualification.main() == 0
    assert '"source_rate_hz": 1250000' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


@pytest.mark.hardware  # Optional protocol package only; synthetic IQ, no radio.
@pytest.mark.parametrize("change", [None, "rate", "samples", "bytes"])
def test_native_visit_geometry(qualification, change):
    from types import SimpleNamespace
    from pluto_plus.adaptive_scan import VisitResult

    record = SimpleNamespace(result=VisitResult.COMPLETE, source_rate_hz=1_250_000,
                             protocol_version=2, valid_start=100, valid_end=150100,
                             iq_bytes=1_200_000)
    if change == "rate":
        record.source_rate_hz = 2_500_000
    if change == "samples":
        record.valid_end += 1
    visit = SimpleNamespace(record=record, iq=bytes(1_200_000 if change != "bytes" else 600_000))
    if change:
        with pytest.raises(ValueError):
            qualification.validate_visit(visit)
    else:
        qualification.validate_visit(visit)
