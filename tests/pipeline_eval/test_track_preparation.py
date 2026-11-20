import json
from dataclasses import replace
from hashlib import sha256

import numpy as np
import pytest

from leo.analysis import polynomial_tracklets as reference
from leo.sky import propagation
from tools.pipeline_eval import original_receiver
from tools.pipeline_eval.variants import track_preparation as variant


def test_element_checksum_preserves_all_ascii_columns_and_original_unicode_errors():
    element_line_checksum = propagation.element_line_checksum
    for code in range(128):
        line = ("-0123456789 abc+" * 4 + chr(code) * 30)[:69]
        assert variant.element_checksum(line, element_line_checksum) == element_line_checksum(line)
    assert variant.element_checksum("", element_line_checksum) == 0
    fallback = []

    def original(line):
        fallback.append(line)
        return element_line_checksum(line)

    assert variant.element_checksum("١٢-", original) == 4
    with pytest.raises(ValueError):
        variant.element_checksum("²", original)
    assert fallback == ["١٢-", "²"]


def test_checksum_port_preserves_the_existing_malformed_line_rejection(monkeypatch):
    original = propagation.element_line_checksum
    line = "1 " + " " * 66
    with pytest.raises(propagation.ElementSetError, match="fails its checksum"):
        propagation._validate_element_line(line + "0", "1 ", 1)
    monkeypatch.setattr(
        propagation,
        "element_line_checksum",
        lambda value: variant.element_checksum(value, original),
    )
    propagation._validate_element_line(line + "1", "1 ", 1)
    with pytest.raises(propagation.ElementSetError, match="fails its checksum"):
        propagation._validate_element_line(line + "0", "1 ", 1)


@pytest.mark.parametrize("geometry", ["regular", "shuffled", "clustered", "singular", "short"])
def test_shared_polynomial_support_preserves_complete_fit_and_rejections(geometry):
    cfg = replace(reference.TrackConfig(), min_points=10, min_span_s=5.0)
    times = np.linspace(0.0, 45.0, 96)
    if geometry == "clustered":
        times = np.r_[np.linspace(0.0, 1.0, 48), np.linspace(44.0, 45.0, 48)]
    elif geometry == "singular":
        times = np.r_[np.zeros(48), np.full(48, 45.0)]
    predicted = 30_000.0 + times * 350.0 - 4.0 * times**2
    noisy = reference._wrap(predicted + 1e-3 * np.sin(times), cfg.alias_spacing_hz)
    indices = np.arange(len(times))
    if geometry == "shuffled":
        indices = np.random.default_rng(53).permutation(indices)
    elif geometry == "short":
        indices = indices[:3]
    common = times, noisy, indices, predicted[indices], cfg
    expected = reference._best_piece(*common)
    actual = variant.best_piece(reference, *common)
    assert variant.fingerprint(actual) == variant.fingerprint(expected)
    if actual is not None:
        assert not np.shares_memory(actual["indices"], indices)


def test_fingerprint_detects_signed_float_and_observation_order():
    assert variant.fingerprint(np.array([-0.0])) != variant.fingerprint(np.array([0.0]))
    assert variant.fingerprint([{"id": 1}, {"id": 2}]) != variant.fingerprint(
        [{"id": 2}, {"id": 1}]
    )


def test_public_cli_preserves_paired_result_and_backend_override(tmp_path, monkeypatch, capsys):
    archive = tmp_path / "causal"
    archive.mkdir()
    entry = archive / "13.tle"
    entry.write_bytes(b"causal catalogue")
    request = tmp_path / "request.json"
    compact = dict(archive=str(archive), tile=[0.0, 0.0], width_km=25.0)
    request.write_text(
        json.dumps(
            dict(
                compact=compact,
                causal_snapshots={
                    entry.name: sha256(entry.read_bytes()).hexdigest(),
                },
            )
        )
    )
    paired = dict(
        status="ok",
        boundary="paired fixture",
        metrics={},
        arms={
            "c0": {"latlon": [0.0, 0.0]},
            "fitted_c": {"latlon": [0.01, 0.01]},
        },
    )
    monkeypatch.setattr(original_receiver, "receiver_assets", lambda _: {})

    def solve(receiver, values, backend, timeout):
        assert (receiver, values, backend, timeout) == (tmp_path, compact, "shared", 45)
        return dict(result=paired)

    monkeypatch.setattr(variant, "solve", solve)
    variant.main(
        [
            "--receiver",
            str(tmp_path),
            "--request",
            str(request),
            "--request-sha256",
            sha256(request.read_bytes()).hexdigest(),
            "--backend",
            "shared",
            "--timeout",
            "45",
        ]
    )
    assert json.loads(capsys.readouterr().out) == paired
