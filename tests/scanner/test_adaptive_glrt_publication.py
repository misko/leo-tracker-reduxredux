import pytest

from leo.scanner.glrt_publication import validate_glrt_adaptive_binding
from tests.scanner.adaptive_glrt_publication_fixtures import MANIFEST, publication_fixture
from tests.scanner.adaptive_hop_fixtures import receipt_fixture


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["shadow", "adaptive"])
@pytest.mark.parametrize("count", [0, 1, 31])
def test_actual_events_not_retained_visit_count_define_inventory(rate, mode, count):
    receipt = receipt_fixture(rate=rate, mode=mode, count=count)
    publication = publication_fixture(receipt)
    validate_glrt_adaptive_binding(publication, receipt, input_manifest_sha256=MANIFEST)
    assert len(publication.evidence.results) == len(receipt.events)
    if count:
        assert len(publication.evidence.results) == receipt.complete_visit_count + 1
        assert publication.evidence.results[-1].verdict == "unavailable"
    if count > 1:
        assert publication.evidence.results[0].fractional_offset_samples == 0.375
        assert publication.evidence.results[0].epoch_sample_counter > 2**53


@pytest.mark.parametrize(
    "field,value",
    [
        ("generation", 72),
        ("session", 123),
        ("mode", "another-positive-profile"),
        ("expected_results", 30),
    ],
)
def test_changed_session_inventory_and_policy_rejected(field, value):
    receipt = receipt_fixture(count=31)
    publication = publication_fixture(receipt)
    evidence = publication.evidence.model_copy(update={field: value})
    publication = publication.model_copy(update={"evidence": evidence})
    with pytest.raises(ValueError):
        validate_glrt_adaptive_binding(publication, receipt, input_manifest_sha256=MANIFEST)


@pytest.mark.parametrize(
    "field,value",
    [
        ("rx", 0),
        ("channel", 4),
        ("edge", "upper"),
        ("visit", 35),
        ("valid_start", 5),
        ("verdict", "no_signal"),
    ],
)
def test_changed_result_geometry_or_absence_rejected(field, value):
    receipt = receipt_fixture(count=31)
    publication = publication_fixture(receipt)
    results = list(publication.evidence.results)
    results[0] = results[0].model_copy(update={field: value})
    evidence = publication.evidence.model_copy(update={"results": tuple(results)})
    with pytest.raises(ValueError):
        validate_glrt_adaptive_binding(
            publication.model_copy(update={"evidence": evidence}),
            receipt,
            input_manifest_sha256=MANIFEST,
        )


def test_cancelled_nominal_interval_does_not_attest_searched_iq():
    receipt = receipt_fixture(count=2)
    publication = publication_fixture(receipt)
    result = publication.evidence.results[-1]
    # Still an otherwise valid unavailable result, but claims unreceived source.
    result = result.model_copy(update={"search_end": result.valid_end})
    evidence = publication.evidence.model_copy(
        update={
            "results": publication.evidence.results[:-1] + (result,),
        }
    )
    with pytest.raises(ValueError, match="beyond delivered"):
        validate_glrt_adaptive_binding(
            publication.model_copy(update={"evidence": evidence}),
            receipt,
            input_manifest_sha256=MANIFEST,
        )


def test_advisory_error_only_is_allowed_but_cross_manifest_is_not():
    receipt = receipt_fixture(count=0)
    publication = publication_fixture(receipt).model_copy(
        update={
            "evidence": None,
            "error": "worker unavailable",
        }
    )
    validate_glrt_adaptive_binding(publication, receipt, input_manifest_sha256=MANIFEST)
    with pytest.raises(ValueError, match="different capture"):
        validate_glrt_adaptive_binding(
            publication, receipt, input_manifest_sha256="sha256:" + "e" * 64
        )
