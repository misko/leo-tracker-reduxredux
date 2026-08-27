from __future__ import annotations

import inspect

import pytest

from leo.analysis import catalogue_population as population_module
from leo.analysis.catalogue_population import (
    CataloguePopulationInputError,
    CataloguePopulationWorkLimitError,
    StarlinkHorizonPopulationPolicy,
    select_response_free_starlink_population,
)
from leo.analysis.catalogue_prediction import (
    ExactTauPolicy,
    KnownSiteRfAuthority,
    Sgp4SupportPredictionPolicy,
    TauGridPoint,
    build_sgp4_catalogue_prediction_bank,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionSupportObservationV1,
    CataloguePredictionSupportV1,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.sky.propagation import element_line_checksum, parse_element_sets

_BASE_LINE_ONE = "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9995"
_BASE_LINE_TWO = "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260123"
_VISIBLE_OFFSET_S = 59_460


def _valid_element_line(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


def _element_record(catalog_number: int, name: str) -> str:
    first = _valid_element_line(f"1 {catalog_number:05d}{_BASE_LINE_ONE[7:]}")
    second = _valid_element_line(f"2 {catalog_number:05d}{_BASE_LINE_TWO[7:]}")
    return f"{name}\n{first}\n{second}"


def _snapshot_payload() -> str:
    return (
        "\n".join(
            (
                _element_record(44714, "STARLINK-44714"),
                _element_record(44715, "STARLINK-44715"),
                _element_record(44716, "ONEWEB-44716"),
            )
        )
        + "\n"
    )


def _support(payload: str) -> CataloguePredictionSupportV1:
    catalogue = parse_element_sets(payload)
    anchor_utc_ns = catalogue.element_epoch_utc_ns()[0] + _VISIBLE_OFFSET_S * 1_000_000_000
    episode_ids = (
        canonical_digest({"episode": 0}),
        canonical_digest({"episode": 1}),
    )
    observations: list[CataloguePredictionSupportObservationV1] = []
    for episode_index, episode_id in enumerate(episode_ids):
        for observation_index in range(2):
            center = anchor_utc_ns + episode_index * 2_000_000_000 + observation_index * 500_000_000
            observations.append(
                CataloguePredictionSupportObservationV1(
                    observation_id=canonical_digest(
                        {"observation": (episode_index, observation_index)}
                    ),
                    episode_id=episode_id,
                    support_start_utc_ns=center - 10_000_000,
                    support_center_utc_ns=center,
                    support_end_utc_ns=center + 10_000_000,
                    factorial_support_moments_s=(1.0, 0.0, 1.0 / 60_000.0, 0.0),
                )
            )
    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (
                item.episode_id,
                item.support_center_utc_ns,
                item.observation_id,
            ),
        )
    )
    document = {
        "schema_version": 1,
        "algorithm_version": "catalogue-prediction-support-v1",
        "episode_ids": tuple(sorted(episode_ids)),
        "observations": [item.model_dump(mode="json") for item in ordered],
        "response_fields_excluded": True,
    }
    return CataloguePredictionSupportV1.model_validate(
        {**document, "content_digest": canonical_digest(document)}
    )


def _snapshot_ref(payload: str, support: CataloguePredictionSupportV1) -> TleSnapshotRefV1:
    return TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=min(item.support_start_utc_ns for item in support.observations)
        - 3_600_000_000_000,
        digest=sha256_digest(payload.encode("ascii")),
        object_count=3,
    )


def _site() -> ObserverSiteV1:
    return ObserverSiteV1(
        latitude_deg=37.858988,
        longitude_deg=-122.478103,
        altitude_m=-29.0,
        label="synthetic-known-site",
    )


def _tau() -> ExactTauPolicy:
    return ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=(TauGridPoint(-5.0, 0.0), TauGridPoint(0.0, 0.0), TauGridPoint(5.0, 0.0)),
    )


def test_complete_response_free_population_selects_starlink_only() -> None:
    payload = _snapshot_payload()
    support = _support(payload)
    population = select_response_free_starlink_population(
        support,
        payload,
        tle_snapshot=_snapshot_ref(payload, support),
        observer_site=_site(),
        tau_policy=_tau(),
        field_delta_s=0,
        selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
    )

    assert population.snapshot_object_count == 3
    assert population.starlink_object_count == 2
    assert population.selected_candidate_count == 2
    assert tuple(item.catalog_number for item in population.universe.candidates) == (44714, 44715)
    assert all(
        item.eligible_episode_ids == support.episode_ids for item in population.universe.candidates
    )
    assert tuple(item.catalog_number for item in population.verified_tle_members) == (44714, 44715)
    assert population.universe.tle_membership_authority_digest == (
        population.tle_membership_authority_digest
    )
    assert population.universe.catalogue_field_delta_s == 0
    assert population.response_accessed is False
    assert population.candidate_ranking_performed is False
    assert population.candidate_truncation_performed is False
    assert population.propagation_complete_for_association is True


def test_population_receipt_feeds_authenticated_prediction_bank() -> None:
    payload = _snapshot_payload()
    support = _support(payload)
    snapshot = _snapshot_ref(payload, support)
    tau = _tau()
    population = select_response_free_starlink_population(
        support,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        tau_policy=tau,
        field_delta_s=0,
        selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
    )
    bank = build_sgp4_catalogue_prediction_bank(
        support,
        payload,
        tle_snapshot=snapshot,
        site_rf_authority=KnownSiteRfAuthority.create(
            observer_site=_site(), nominal_rf_hz=11_440_312_498.0
        ),
        candidate_universe=population.universe,
        verified_tle_members=population.verified_tle_members,
        tau_policy=tau,
        prediction_policy=Sgp4SupportPredictionPolicy(maximum_propagated_states=1_000),
    )

    assert bank.returned_candidate_count == 2
    assert bank.truncated_candidate_count == 0
    assert tuple(item.catalog_number for item in bank.candidates) == (44714, 44715)
    assert bank.response_accessed is False


def test_field_and_tau_support_change_the_response_free_policy_digest() -> None:
    payload = _snapshot_payload()
    support = _support(payload)
    snapshot = _snapshot_ref(payload, support)
    first = select_response_free_starlink_population(
        support,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        tau_policy=_tau(),
        field_delta_s=0,
        selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
    )
    second = select_response_free_starlink_population(
        support,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        tau_policy=ExactTauPolicy.fixed_zero(),
        field_delta_s=0,
        selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
    )

    assert first.selection_policy_digest != second.selection_policy_digest
    assert first.exact_time_count > second.exact_time_count

    shifted = select_response_free_starlink_population(
        support,
        payload,
        tle_snapshot=snapshot,
        observer_site=_site(),
        tau_policy=_tau(),
        field_delta_s=500,
        selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
    )
    assert shifted.universe.catalogue_field_delta_s == 500
    assert shifted.selection_policy_digest != first.selection_policy_digest


def test_snapshot_and_stale_contract_poisons_fail_before_selection() -> None:
    payload = _snapshot_payload()
    support = _support(payload)
    snapshot = _snapshot_ref(payload, support)
    poisoned_payload = payload.replace("53.0537", "54.0537", 1)
    with pytest.raises(CataloguePopulationInputError, match="bytes"):
        select_response_free_starlink_population(
            support,
            poisoned_payload,
            tle_snapshot=snapshot,
            observer_site=_site(),
            tau_policy=_tau(),
            field_delta_s=0,
            selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
        )

    poisoned_support = support.model_copy(update={"content_digest": "sha256:" + "0" * 64})
    with pytest.raises(CataloguePopulationInputError, match="support is invalid"):
        select_response_free_starlink_population(
            poisoned_support,
            payload,
            tle_snapshot=snapshot,
            observer_site=_site(),
            tau_policy=_tau(),
            field_delta_s=0,
            selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
        )


def test_work_cap_fails_before_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _snapshot_payload()
    support = _support(payload)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("propagation occurred before the work cap")

    monkeypatch.setattr(population_module, "propagate_grid", forbidden)
    with pytest.raises(CataloguePopulationWorkLimitError, match="coarse"):
        select_response_free_starlink_population(
            support,
            payload,
            tle_snapshot=_snapshot_ref(payload, support),
            observer_site=_site(),
            tau_policy=_tau(),
            field_delta_s=0,
            selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
            policy=StarlinkHorizonPopulationPolicy(maximum_coarse_propagated_states=1),
        )

    with pytest.raises(CataloguePopulationWorkLimitError, match="field-time"):
        select_response_free_starlink_population(
            support,
            payload,
            tle_snapshot=_snapshot_ref(payload, support),
            observer_site=_site(),
            tau_policy=_tau(),
            field_delta_s=0,
            selection_protocol_digest=canonical_digest({"protocol": "synthetic"}),
            policy=StarlinkHorizonPopulationPolicy(maximum_exact_time_count=3),
        )


def test_selector_input_surface_cannot_receive_cfo_or_episode_graph() -> None:
    signature = inspect.signature(select_response_free_starlink_population)
    source = inspect.getsource(population_module)

    assert "graph" not in signature.parameters
    assert "measured_cfo_hz" not in source
    assert "PhysicalEpisodeGraphV1" not in source
    assert "from leo.analysis.catalogue_association" not in source
    assert "leo.storage" not in source
