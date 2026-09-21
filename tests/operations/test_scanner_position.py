from types import SimpleNamespace

import pytest

import leo.operations.scanner_position as subject
from tests.application.test_scanner_tracking import source


def test_missing_trajectory_publishes_explicit_insufficiency_png():
    diagnostic, png = subject.build_scan_position_diagnostic(
        source=source(),
        trajectory=None,
        product=SimpleNamespace(original_tle_snapshot=None),
    )
    assert diagnostic.state == "insufficient"
    assert "no-causal-associated-trajectory-evidence" in diagnostic.reasons
    assert diagnostic.candidate_latitude_deg is None
    assert not diagnostic.position_fix_claimed
    assert diagnostic.position_prior.center_latitude_deg == 39.7392
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_future_catalogue_is_rejected_before_parsing(monkeypatch):
    data = source()
    start = data.timing.first_sample_estimate_utc_ns
    monkeypatch.setattr(subject, "parse_element_sets", lambda _: pytest.fail("parsed future input"))
    diagnostic, _png = subject.build_scan_position_diagnostic(
        source=data,
        trajectory=SimpleNamespace(),
        catalogue_payload="future",
        product=SimpleNamespace(original_tle_snapshot=SimpleNamespace(collected_utc_ns=start)),
    )
    assert diagnostic.state == "insufficient"
    assert "catalogue-not-strictly-before-capture" in diagnostic.reasons


def test_future_element_epoch_is_excluded_even_in_older_snapshot(monkeypatch):
    data = source()
    start = data.timing.first_sample_estimate_utc_ns

    class Catalogue:
        satellite_numbers = (12345,)

        def __len__(self):
            return 1

        def element_epoch_utc_ns(self):
            return (start + 1,)

    monkeypatch.setattr(subject, "parse_element_sets", lambda _: Catalogue())
    diagnostic, _png = subject.build_scan_position_diagnostic(
        source=data,
        trajectory=SimpleNamespace(hypotheses=()),
        catalogue_payload="old",
        product=SimpleNamespace(
            original_tle_snapshot=SimpleNamespace(collected_utc_ns=start - 1),
            tle_candidates=(
                SimpleNamespace(
                    hypothesis_rank=1,
                    abstention_recommended=False,
                    leading_catalog_number=12345,
                ),
            ),
        ),
    )
    assert diagnostic.state == "insufficient"
    assert "selected-element-unavailable-or-future-epoch" in diagnostic.reasons
    assert diagnostic.fit_observation_count == 0
