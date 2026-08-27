from __future__ import annotations

import ast
import math
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from leo.analysis import catalogue_prediction as prediction_module
from leo.analysis.catalogue_prediction import (
    CataloguePredictionInputError,
    CataloguePredictionWorkLimitError,
    ExactTauPolicy,
    FrozenCatalogueCandidate,
    FrozenResponseFreeCandidateUniverse,
    KnownSiteRfAuthority,
    Sgp4SupportPredictionPolicy,
    TauGridPoint,
    build_sgp4_catalogue_prediction_bank,
    element_pair_digest,
)
from leo.contracts.catalogue_association import (
    CataloguePredictionBankV1,
    CataloguePredictionSupportObservationV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.sky.doppler import SPEED_OF_LIGHT_KM_S
from leo.sky.propagation import (
    ElementSetCatalogue,
    element_line_checksum,
    parse_element_sets,
)
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import ObservedTracks

_RF_HZ = 11_325_000_000.0
_BASE_LINE_ONE = "1 44714U 19074B   26232.62719907  .00001103  00000-0  92799-4 0  9995"
_BASE_LINE_TWO = "2 44714  53.0537 172.0234 0001334  87.1234 273.0021 15.06393004260123"


def _digest(kind: str, value: object) -> str:
    return canonical_digest({kind: value})


def _valid_element_line(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


def _element_record(catalog_number: int) -> str:
    first = _valid_element_line(f"1 {catalog_number:05d}{_BASE_LINE_ONE[7:]}")
    second = _valid_element_line(f"2 {catalog_number:05d}{_BASE_LINE_TWO[7:]}")
    return f"STARLINK-{catalog_number}\n{first}\n{second}"


def _snapshot_payload(numbers: tuple[int, ...] = (44714, 44715)) -> str:
    return "\n".join(_element_record(item) for item in numbers) + "\n"


def _catalogue(numbers: tuple[int, ...] = (44714, 44715)) -> ElementSetCatalogue:
    return parse_element_sets(_snapshot_payload(numbers))


def _as_snapshot_payload(value: str | ElementSetCatalogue) -> str:
    if isinstance(value, str):
        return value
    return _snapshot_payload(value.satellite_numbers)


def _support(catalogue: ElementSetCatalogue) -> CataloguePredictionSupportV1:
    anchor_utc_ns = max(catalogue.element_epoch_utc_ns()) + 60_000_000_000
    observations: list[CataloguePredictionSupportObservationV1] = []
    episode_ids = tuple(sorted(_digest("episode", index) for index in range(2)))
    for episode_index, episode_id in enumerate(episode_ids):
        for observation_index in range(2):
            center_utc_ns = (
                anchor_utc_ns + episode_index * 10_000_000_000 + observation_index * 2_000_000_000
            )
            observations.append(
                CataloguePredictionSupportObservationV1(
                    observation_id=_digest(
                        "observation",
                        (episode_index, observation_index),
                    ),
                    episode_id=episode_id,
                    support_start_utc_ns=center_utc_ns - 500_000_000,
                    support_center_utc_ns=center_utc_ns,
                    support_end_utc_ns=center_utc_ns + 500_000_000,
                    # Uniform aperture over [-0.5,+0.5] s.  These are
                    # (1, E[u], E[u^2]/2, E[u^3]/6).
                    factorial_support_moments_s=(1.0, 0.0, 1.0 / 24.0, 0.0),
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
    payload = {
        "schema_version": 1,
        "algorithm_version": "catalogue-prediction-support-v1",
        "episode_ids": episode_ids,
        "observations": [item.model_dump(mode="json") for item in ordered],
        "response_fields_excluded": True,
    }
    return CataloguePredictionSupportV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )


def _retime_support(
    support: CataloguePredictionSupportV1,
    *,
    earliest_center_utc_ns: int,
) -> CataloguePredictionSupportV1:
    delta_ns = earliest_center_utc_ns - min(
        item.support_center_utc_ns for item in support.observations
    )
    observations = tuple(
        CataloguePredictionSupportObservationV1(
            observation_id=item.observation_id,
            episode_id=item.episode_id,
            support_start_utc_ns=item.support_start_utc_ns + delta_ns,
            support_center_utc_ns=item.support_center_utc_ns + delta_ns,
            support_end_utc_ns=item.support_end_utc_ns + delta_ns,
            factorial_support_moments_s=item.factorial_support_moments_s,
        )
        for item in support.observations
    )
    payload = {
        "schema_version": 1,
        "algorithm_version": "catalogue-prediction-support-v1",
        "episode_ids": support.episode_ids,
        "observations": [item.model_dump(mode="json") for item in observations],
        "response_fields_excluded": True,
    }
    return CataloguePredictionSupportV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )


def _snapshot(
    snapshot_source: str | ElementSetCatalogue,
    support: CataloguePredictionSupportV1,
    *,
    collected_utc_ns: int | None = None,
    object_count: int | None = None,
) -> TleSnapshotRefV1:
    snapshot_payload = _as_snapshot_payload(snapshot_source)
    earliest = min(item.support_start_utc_ns for item in support.observations)
    return TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=(
            earliest - 10_000_000_000 if collected_utc_ns is None else collected_utc_ns
        ),
        digest=sha256_digest(snapshot_payload.encode("ascii")),
        object_count=(
            len(parse_element_sets(snapshot_payload)) if object_count is None else object_count
        ),
    )


def _site_rf_authority() -> KnownSiteRfAuthority:
    return KnownSiteRfAuthority.create(
        observer_site=ObserverSiteV1(
            latitude_deg=37.858988,
            longitude_deg=-122.478103,
            altitude_m=-29.0,
            label="synthetic-known-site",
        ),
        nominal_rf_hz=_RF_HZ,
    )


def _universe(
    support: CataloguePredictionSupportV1,
    numbers: tuple[int, ...],
    *,
    eligible_by_number: dict[int, tuple[str, ...]] | None = None,
    catalogue_field_delta_s: int = 0,
) -> FrozenResponseFreeCandidateUniverse:
    eligible_by_number = {} if eligible_by_number is None else eligible_by_number
    return FrozenResponseFreeCandidateUniverse(
        candidates=tuple(
            FrozenCatalogueCandidate(
                catalog_number=number,
                eligible_episode_ids=eligible_by_number.get(number, support.episode_ids),
            )
            for number in numbers
        ),
        selection_protocol_digest=_digest("selection-protocol", "frozen-synthetic-v1"),
        selection_policy_digest=_digest("selection-policy", "response-free-geometry-v1"),
        tle_membership_authority_digest=_digest(
            "tle-membership-authority",
            "externally-verified-snapshot-members-v1",
        ),
        catalogue_field_delta_s=catalogue_field_delta_s,
    )


def _members(
    snapshot_source: str | ElementSetCatalogue,
    numbers: tuple[int, ...],
) -> tuple[CatalogueVerifiedTleMemberV1, ...]:
    snapshot_payload = _as_snapshot_payload(snapshot_source)
    catalogue = parse_element_sets(snapshot_payload)
    epochs = dict(
        zip(
            catalogue.satellite_numbers,
            catalogue.element_epoch_utc_ns(),
            strict=True,
        )
    )
    return tuple(
        CatalogueVerifiedTleMemberV1(
            catalog_number=number,
            selected_element_digest=element_pair_digest(*_element_record(number).splitlines()[1:3]),
            element_epoch_utc_ns=epochs[number],
        )
        for number in numbers
    )


def _build(
    snapshot_source: str | ElementSetCatalogue,
    support: CataloguePredictionSupportV1,
    *,
    numbers: tuple[int, ...] = (44714, 44715),
    universe: FrozenResponseFreeCandidateUniverse | None = None,
    members: tuple[CatalogueVerifiedTleMemberV1, ...] | None = None,
    snapshot: TleSnapshotRefV1 | None = None,
    tau_policy: ExactTauPolicy | None = None,
    prediction_policy: Sgp4SupportPredictionPolicy | None = None,
    catalogue_field_delta_s: int = 0,
) -> CataloguePredictionBankV1:
    snapshot_payload = _as_snapshot_payload(snapshot_source)
    return build_sgp4_catalogue_prediction_bank(
        support,
        snapshot_payload,
        tle_snapshot=(_snapshot(snapshot_payload, support) if snapshot is None else snapshot),
        site_rf_authority=_site_rf_authority(),
        candidate_universe=(
            _universe(
                support,
                numbers,
                catalogue_field_delta_s=catalogue_field_delta_s,
            )
            if universe is None
            else universe
        ),
        verified_tle_members=(_members(snapshot_payload, numbers) if members is None else members),
        tau_policy=ExactTauPolicy.fixed_zero() if tau_policy is None else tau_policy,
        prediction_policy=prediction_policy,
        catalogue_field_delta_s=catalogue_field_delta_s,
    )


def test_real_sgp4_adapter_returns_complete_response_free_diagonal_bank() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)

    bank = _build(catalogue, support)

    assert bank.population_conditioning == "frozen-response-free-universe-v1"
    assert bank.prediction_error_model == "independent-diagonal-conditional-on-candidate-v1"
    assert bank.response_accessed is False
    assert bank.source_candidate_count == bank.returned_candidate_count == 2
    assert bank.truncated_candidate_count == 0
    assert tuple(item.catalog_number for item in bank.candidates) == (44714, 44715)
    expected_observations = tuple(sorted(item.observation_id for item in support.observations))
    for candidate in bank.candidates:
        assert tuple(item.tau_s for item in candidate.tau_states) == (0.0,)
        predictions = candidate.tau_states[0].predictions
        assert tuple(item.observation_id for item in predictions) == expected_observations
        assert all(math.isfinite(item.predicted_cfo_hz) for item in predictions)
        assert all(item.standard_uncertainty_hz >= 1.0 for item in predictions)


def test_predeclared_catalogue_field_shift_changes_only_response_free_predictions() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    true_time = _build(catalogue, support, numbers=(44714,))
    shifted = _build(
        catalogue,
        support,
        numbers=(44714,),
        catalogue_field_delta_s=500,
    )

    assert shifted.support.content_digest == true_time.support.content_digest
    assert shifted.propagation_model != true_time.propagation_model
    true_values = tuple(
        item.predicted_cfo_hz for item in true_time.candidates[0].tau_states[0].predictions
    )
    shifted_values = tuple(
        item.predicted_cfo_hz for item in shifted.candidates[0].tau_states[0].predictions
    )
    assert shifted_values != true_values
    assert shifted.response_accessed is False


def test_catalogue_field_must_match_response_free_universe_receipt() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)

    with pytest.raises(CataloguePredictionInputError, match="frozen candidate universe"):
        _build(
            catalogue,
            support,
            numbers=(44714,),
            universe=_universe(support, (44714,), catalogue_field_delta_s=0),
            catalogue_field_delta_s=500,
        )


@pytest.mark.parametrize("value", (False, -1, 30, 501))
def test_catalogue_field_shift_is_exact_and_bounded(value: object) -> None:
    catalogue = _catalogue()
    support = _support(catalogue)

    with pytest.raises(CataloguePredictionInputError, match="field delta"):
        build_sgp4_catalogue_prediction_bank(
            support,
            _snapshot_payload(),
            tle_snapshot=_snapshot(_snapshot_payload(), support),
            site_rf_authority=_site_rf_authority(),
            candidate_universe=_universe(support, (44714,)),
            verified_tle_members=_members(_snapshot_payload(), (44714,)),
            tau_policy=ExactTauPolicy.fixed_zero(),
            catalogue_field_delta_s=value,  # type: ignore[arg-type]
        )


def test_exact_ascii_snapshot_bytes_are_accepted_without_a_detached_catalogue() -> None:
    payload = _snapshot_payload()
    catalogue = parse_element_sets(payload)
    support = _support(catalogue)

    bank = build_sgp4_catalogue_prediction_bank(
        support,
        payload.encode("ascii"),
        tle_snapshot=_snapshot(payload, support),
        site_rf_authority=_site_rf_authority(),
        candidate_universe=_universe(support, (44714,)),
        verified_tle_members=_members(payload, (44714,)),
        tau_policy=ExactTauPolicy.fixed_zero(),
    )

    assert tuple(item.catalog_number for item in bank.candidates) == (44714,)


def test_input_order_cannot_change_candidate_or_prediction_order() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    forward = _build(catalogue, support)
    reversed_payload = _snapshot_payload((44715, 44714))
    reverse = _build(
        reversed_payload,
        support,
        numbers=(44715, 44714),
        universe=_universe(support, (44715, 44714)),
        members=tuple(reversed(_members(catalogue, (44714, 44715)))),
        snapshot=_snapshot(reversed_payload, support),
    )

    assert reverse.candidates == forward.candidates
    assert reverse.tle_snapshot.digest != forward.tle_snapshot.digest


def test_noncausal_snapshot_fails_before_any_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    earliest = min(item.support_start_utc_ns for item in support.observations)

    def forbidden_propagation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("causality must fail before SGP4")

    monkeypatch.setattr(prediction_module, "propagate_grid", forbidden_propagation)
    with pytest.raises(CataloguePredictionInputError, match="strictly pre-measurement"):
        _build(
            catalogue,
            support,
            snapshot=_snapshot(catalogue, support, collected_utc_ns=earliest),
        )


def test_snapshot_count_must_match_the_complete_parsed_catalogue() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    with pytest.raises(CataloguePredictionInputError, match="object count"):
        _build(
            catalogue,
            support,
            snapshot=_snapshot(catalogue, support, object_count=1),
        )


def test_duplicate_parsed_catalogue_identity_fails_closed() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    duplicate = ElementSetCatalogue(
        names=(catalogue.names[0], f"{catalogue.names[0]}-duplicate"),
        satellite_numbers=(catalogue.satellite_numbers[0], catalogue.satellite_numbers[0]),
        satellites=(catalogue.satellites[0], catalogue.satellites[0]),
    )
    with pytest.raises(CataloguePredictionInputError, match="one element per catalogue number"):
        _build(
            duplicate,
            support,
            numbers=(44714,),
            members=_members(catalogue, (44714,)),
            snapshot=_snapshot(duplicate, support),
        )


def test_verified_members_exactly_cover_the_frozen_universe_before_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogue = _catalogue()
    support = _support(catalogue)

    def forbidden_propagation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("membership must fail before SGP4")

    monkeypatch.setattr(prediction_module, "propagate_grid", forbidden_propagation)
    with pytest.raises(CataloguePredictionInputError, match="exactly cover"):
        _build(
            catalogue,
            support,
            members=_members(catalogue, (44714,)),
        )


def test_verified_member_epoch_is_rechecked_against_the_parsed_satrec() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    members = _members(catalogue, (44714, 44715))
    poisoned = (
        members[0].model_copy(update={"element_epoch_utc_ns": members[0].element_epoch_utc_ns + 1}),
        members[1],
    )
    with pytest.raises(CataloguePredictionInputError, match="parsed element epoch"):
        _build(catalogue, support, members=poisoned)


@pytest.mark.parametrize("poison_kind", ("support", "snapshot", "member"))
def test_model_copy_contract_poisons_are_revalidated_before_propagation(
    monkeypatch: pytest.MonkeyPatch,
    poison_kind: str,
) -> None:
    payload = _snapshot_payload()
    catalogue = parse_element_sets(payload)
    support = _support(catalogue)
    snapshot = _snapshot(payload, support)
    members = _members(payload, (44714, 44715))
    if poison_kind == "support":
        support = support.model_copy(update={"content_digest": _digest("stale", "support")})
    elif poison_kind == "snapshot":
        snapshot = snapshot.model_copy(update={"object_count": 0})
    else:
        members = (
            members[0].model_copy(update={"catalog_number": 0}),
            members[1],
        )

    def forbidden_propagation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("contract validation must fail before SGP4")

    monkeypatch.setattr(prediction_module, "propagate_grid", forbidden_propagation)
    with pytest.raises(CataloguePredictionInputError, match="valid, closed V1"):
        _build(
            payload,
            support,
            snapshot=snapshot,
            members=members,
        )


def test_selected_element_digest_is_recomputed_from_the_exact_propagated_pair() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    [member] = _members(catalogue, (44714,))

    bank = _build(
        catalogue,
        support,
        numbers=(44714,),
        members=(member,),
    )

    assert bank.candidates[0].selected_element_digest == member.selected_element_digest


def test_changed_orbit_with_same_catalogue_number_and_epoch_fails_before_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_payload = _snapshot_payload()
    catalogue = parse_element_sets(original_payload)
    support = _support(catalogue)
    original_members = _members(original_payload, (44714, 44715))
    lines = original_payload.splitlines()
    line_index = next(index for index, line in enumerate(lines) if line.startswith("2 44714"))
    changed = lines[line_index].replace(" 53.0537 ", " 54.0537 ", 1)
    lines[line_index] = _valid_element_line(changed)
    changed_payload = "\n".join(lines) + "\n"
    changed_catalogue = parse_element_sets(changed_payload)
    assert changed_catalogue.satellite_numbers == catalogue.satellite_numbers
    assert changed_catalogue.element_epoch_utc_ns() == catalogue.element_epoch_utc_ns()

    def forbidden_propagation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("selected-element authentication must fail before SGP4")

    monkeypatch.setattr(prediction_module, "propagate_grid", forbidden_propagation)
    with pytest.raises(CataloguePredictionInputError, match="exact propagated line pair"):
        _build(
            changed_payload,
            support,
            members=original_members,
            snapshot=_snapshot(changed_payload, support),
        )


def test_snapshot_bytes_must_match_the_snapshot_reference_before_parsing_or_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_payload = _snapshot_payload()
    catalogue = parse_element_sets(original_payload)
    support = _support(catalogue)
    changed_payload = original_payload + "\n"

    def forbidden_propagation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("snapshot authentication must fail before SGP4")

    monkeypatch.setattr(prediction_module, "propagate_grid", forbidden_propagation)
    with pytest.raises(CataloguePredictionInputError, match="authority digest"):
        _build(
            changed_payload,
            support,
            members=_members(original_payload, (44714, 44715)),
            snapshot=_snapshot(original_payload, support),
        )


def test_candidate_eligibility_produces_exact_episode_support_and_no_truncation() -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    selected_episode = support.episode_ids[1]
    universe = _universe(
        support,
        (44714,),
        eligible_by_number={44714: (selected_episode,)},
    )

    bank = _build(
        catalogue,
        support,
        numbers=(44714,),
        universe=universe,
        members=_members(catalogue, (44714,)),
    )

    expected = tuple(
        sorted(
            item.observation_id
            for item in support.observations
            if item.episode_id == selected_episode
        )
    )
    assert bank.source_candidate_count == bank.returned_candidate_count == 1
    assert bank.truncated_candidate_count == 0
    assert (
        tuple(item.observation_id for item in bank.candidates[0].tau_states[0].predictions)
        == expected
    )


def test_unknown_candidate_episode_fails_before_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    universe = _universe(
        support,
        (44714,),
        eligible_by_number={44714: (_digest("episode", "not-in-support"),)},
    )

    def forbidden_propagation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("coverage must fail before SGP4")

    monkeypatch.setattr(prediction_module, "propagate_grid", forbidden_propagation)
    with pytest.raises(CataloguePredictionInputError, match="unknown.*episode"):
        _build(
            catalogue,
            support,
            numbers=(44714,),
            universe=universe,
            members=_members(catalogue, (44714,)),
        )


def test_declared_work_cap_fails_before_grid_or_propagation_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogue = _catalogue()
    support = _support(catalogue)

    def forbidden_knots(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("work cap must fail before grid materialization")

    monkeypatch.setattr(prediction_module, "_integration_knots", forbidden_knots)
    with pytest.raises(CataloguePredictionWorkLimitError, match="work cap"):
        _build(
            catalogue,
            support,
            prediction_policy=Sgp4SupportPredictionPolicy(
                maximum_propagated_states=1,
            ),
        )


def test_all_tau_shifted_instants_are_validated_before_first_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _snapshot_payload()
    catalogue = parse_element_sets(payload)
    support = _retime_support(_support(catalogue), earliest_center_utc_ns=2_000_000_000)
    snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=1,
        digest=sha256_digest(payload.encode("ascii")),
        object_count=len(catalogue),
    )
    tau_policy = ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=(
            TauGridPoint(-5.0, 0.0),
            TauGridPoint(0.0, 0.0),
            TauGridPoint(5.0, 0.0),
        ),
    )

    def forbidden_propagation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("shifted-time validation must finish before SGP4")

    monkeypatch.setattr(prediction_module, "propagate_grid", forbidden_propagation)
    with pytest.raises(CataloguePredictionInputError, match="tau-shifted support instants"):
        _build(
            payload,
            support,
            snapshot=snapshot,
            members=_members(payload, (44714, 44715)),
            tau_policy=tau_policy,
        )


def _fake_polynomial_observer(
    reference_utc_ns: int,
    polynomial: tuple[float, float, float, float],
) -> Callable[[object, ObserverSiteV1, SamplingGrid], ObservedTracks]:
    def fake_observe(
        _propagated: object,
        _observer: ObserverSiteV1,
        grid: SamplingGrid,
    ) -> ObservedTracks:
        offsets_s = (np.asarray(grid.utc_ns, dtype=np.int64) - reference_utc_ns).astype(
            np.float64
        ) / 1e9
        c0, c1, c2, c3 = polynomial
        shift_hz = c0 + c1 * offsets_s + c2 * offsets_s**2 + c3 * offsets_s**3
        range_rate = -shift_hz * SPEED_OF_LIGHT_KM_S / _RF_HZ
        samples = len(grid)
        return ObservedTracks(
            azimuth_deg=np.zeros((1, samples), dtype=np.float64),
            elevation_deg=np.full((1, samples), 45.0, dtype=np.float64),
            range_km=np.full((1, samples), 1_000.0, dtype=np.float64),
            range_rate_km_s=range_rate[np.newaxis, :],
            altitude_km=np.full((1, samples), 550.0, dtype=np.float64),
            usable=np.ones(1, dtype=np.bool_),
            anchor_index=grid.anchor_index,
        )

    return fake_observe


def test_field_time_tau_integrates_linear_doppler_at_t_plus_tau_plus_u(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    reference_utc_ns = min(item.support_center_utc_ns for item in support.observations)
    intercept_hz = 2_000.0
    slope_hz_s = 17.5
    monkeypatch.setattr(
        prediction_module,
        "observe_grid",
        _fake_polynomial_observer(
            reference_utc_ns,
            (intercept_hz, slope_hz_s, 0.0, 0.0),
        ),
    )
    tau_policy = ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=(
            TauGridPoint(5.0, -1.0),
            TauGridPoint(0.0, 0.0),
            TauGridPoint(-5.0, -1.0),
        ),
    )

    bank = _build(
        catalogue,
        support,
        numbers=(44714,),
        members=_members(catalogue, (44714,)),
        tau_policy=tau_policy,
    )

    candidate = bank.candidates[0]
    assert tuple(item.tau_s for item in candidate.tau_states) == (-5.0, 0.0, 5.0)
    target_id = min(
        support.observations,
        key=lambda item: item.support_center_utc_ns,
    ).observation_id
    by_tau = {
        state.tau_s: next(
            item.predicted_cfo_hz for item in state.predictions if item.observation_id == target_id
        )
        for state in candidate.tau_states
    }
    assert by_tau[0.0] == pytest.approx(intercept_hz, abs=1e-6)
    assert by_tau[5.0] - by_tau[-5.0] == pytest.approx(10.0 * slope_hz_s, abs=1e-6)


def test_factorial_moments_match_analytic_cubic_support_integral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalogue = _catalogue()
    support = _support(catalogue)
    first = min(support.observations, key=lambda item: item.support_center_utc_ns)
    reference_utc_ns = first.support_center_utc_ns
    # f(u) = 1000 + 10u + 3u^2 + 4u^3.  Under a symmetric uniform
    # aperture u in [-0.5,+0.5], E[u]=E[u^3]=0 and E[u^2]=1/12.
    monkeypatch.setattr(
        prediction_module,
        "observe_grid",
        _fake_polynomial_observer(reference_utc_ns, (1_000.0, 10.0, 3.0, 4.0)),
    )

    bank = _build(
        catalogue,
        support,
        numbers=(44714,),
        members=_members(catalogue, (44714,)),
    )
    prediction = next(
        item
        for item in bank.candidates[0].tau_states[0].predictions
        if item.observation_id == first.observation_id
    )

    assert prediction.predicted_cfo_hz == pytest.approx(1_000.0 + 3.0 / 12.0, abs=1e-6)


def test_tau_policy_rejects_a_truncated_bounded_grid() -> None:
    with pytest.raises(CataloguePredictionInputError, match=r"exact -5, 0, and \+5"):
        ExactTauPolicy(
            policy="bounded-profile-minus5-plus5-v1",
            points=(TauGridPoint(-4.0, 0.0), TauGridPoint(0.0, 0.0), TauGridPoint(5.0, 0.0)),
        )


def test_tau_must_be_canonical_at_nanosecond_resolution() -> None:
    with pytest.raises(CataloguePredictionInputError, match="canonical at UTC-ns"):
        TauGridPoint(5e-16, 0.0)


def test_tau_policy_rejects_duplicate_nanosecond_states() -> None:
    with pytest.raises(CataloguePredictionInputError, match="unique in UTC ns"):
        ExactTauPolicy(
            policy="fixed-tau-zero-v1",
            points=(TauGridPoint(0.0, 0.0), TauGridPoint(-0.0, -1.0)),
        )


def test_tau_log_prior_weights_remove_a_huge_common_offset_canonically() -> None:
    policy = ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=(
            TauGridPoint(-5.0, 1e308),
            TauGridPoint(0.0, 1e308),
            TauGridPoint(5.0, 1e308),
        ),
    )

    assert tuple(item.log_prior_weight for item in policy.points) == (0.0, 0.0, 0.0)


def test_tau_log_prior_unrepresentable_dynamic_range_fails_closed() -> None:
    with pytest.raises(CataloguePredictionInputError, match="dynamic range"):
        ExactTauPolicy(
            policy="bounded-profile-minus5-plus5-v1",
            points=(
                TauGridPoint(-5.0, -1e308),
                TauGridPoint(0.0, 0.0),
                TauGridPoint(5.0, 1e308),
            ),
        )


def test_valid_support_subclass_with_response_poison_is_never_read() -> None:
    class PoisonedSupport(CataloguePredictionSupportV1):
        @property
        def measured_cfo_hz(self) -> float:
            raise AssertionError("response poison was read")

    catalogue = _catalogue()
    clean = _support(catalogue)
    poisoned = PoisonedSupport.model_validate(clean.model_dump(mode="json"))

    bank = _build(catalogue, poisoned, numbers=(44714,))

    assert bank.support.content_digest == clean.content_digest
    assert bank.response_accessed is False


def test_prediction_adapter_imports_only_pure_contract_and_sky_layers() -> None:
    path = Path(prediction_module.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module)
    forbidden_roots = (
        "sqlalchemy",
        "psycopg",
        "fastapi",
        "httpx",
        "typer",
        "leo.storage",
        "leo.operations",
        "leo.catalog",
        "leo.api",
        "leo.cli",
        "leo.application",
        "leo.presentation",
        "leo.processing",
        "leo.radio",
        "leo.acquisition",
        "leo.analysis.catalogue_association",
    )
    offending = {
        module
        for module in imported
        for root in forbidden_roots
        if module == root or module.startswith(f"{root}.")
    }
    assert not offending
    imported_symbols = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "SupportIntegratedCfoObservationV1" not in imported_symbols
    assert "PhysicalEpisodeGraphV1" not in imported_symbols
