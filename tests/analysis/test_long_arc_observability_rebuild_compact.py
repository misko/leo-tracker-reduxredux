from __future__ import annotations

import gc
import tracemalloc
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from leo.analysis.catalogue_prediction import (
    ExactTauPolicy,
    FrozenCatalogueCandidate,
    FrozenResponseFreeCandidateUniverse,
    KnownSiteRfAuthority,
    Sgp4SupportPredictionPolicy,
    TauGridPoint,
)
from leo.analysis.catalogue_prediction_array_view import (
    catalogue_prediction_array_view_from_bank,
)
from leo.analysis.research import long_arc_observability_rebuild as rebuild_module
from leo.analysis.research.compact_catalogue_prediction_bank import (
    CompactCataloguePredictionBank,
    CompactCataloguePredictionBankError,
    materialize_compact_candidate,
    open_compact_catalogue_prediction_array_bank_view,
    open_compact_prediction_arrays,
    verify_compact_catalogue_prediction_bank,
)
from leo.analysis.research.long_arc_observability_rebuild import (
    CompactFieldBankRebuildPolicy,
    LongArcObservabilityRebuildError,
    SealedFieldBankReceipt,
    SealedFieldCandidateReceipt,
    SealedResponseFreeBankInventory,
    iter_rebuilt_digest_identical_compact_field_banks,
)
from leo.contracts.catalogue_association import (
    CandidateObservationPredictionV1,
    CandidateTauStateV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportObservationV1,
    CataloguePredictionSupportV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import canonical_digest, sha256_digest
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1

_FIELDS = (-500, 0, 500)


def _digest(label: str, value: object) -> str:
    return canonical_digest({label: value})


def _support(observation_count: int) -> CataloguePredictionSupportV1:
    episode_id = _digest("episode", observation_count)
    base_ns = 1_800_000_000_000_000_000
    observations = tuple(
        CataloguePredictionSupportObservationV1(
            observation_id=_digest("observation", (observation_count, index)),
            episode_id=episode_id,
            support_start_utc_ns=base_ns + index * 1_000_000_000,
            support_center_utc_ns=base_ns + index * 1_000_000_000 + 10_000_000,
            support_end_utc_ns=base_ns + index * 1_000_000_000 + 20_000_000,
            factorial_support_moments_s=(1.0, 0.0, 0.0, 0.0),
        )
        for index in range(observation_count)
    )
    payload = {
        "schema_version": 1,
        "algorithm_version": "catalogue-prediction-support-v1",
        "episode_ids": (episode_id,),
        "observations": [item.model_dump(mode="json") for item in observations],
        "response_fields_excluded": True,
    }
    return CataloguePredictionSupportV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )


def _tau_policy(point_count: int) -> ExactTauPolicy:
    if point_count == 1:
        return ExactTauPolicy.fixed_zero()
    points = tuple(
        TauGridPoint(
            tau_s=-5.0 + 10.0 * index / (point_count - 1),
            log_prior_weight=-abs(-5.0 + 10.0 * index / (point_count - 1)),
        )
        for index in range(point_count)
    )
    return ExactTauPolicy(
        policy="bounded-profile-minus5-plus5-v1",
        points=points,
    )


@dataclass(slots=True)
class _FakeBuilder:
    metadata: dict[int, tuple[str, str, int]]
    calls: list[tuple[int, tuple[int, ...]]]

    def __call__(
        self,
        support: CataloguePredictionSupportV1,
        snapshot_payload: bytes | str,
        *,
        tle_snapshot: TleSnapshotRefV1,
        site_rf_authority: KnownSiteRfAuthority,
        candidate_universe: FrozenResponseFreeCandidateUniverse,
        verified_tle_members: tuple[CatalogueVerifiedTleMemberV1, ...],
        tau_policy: ExactTauPolicy,
        prediction_policy: Sgp4SupportPredictionPolicy | None = None,
        catalogue_field_delta_s: int = 0,
    ) -> CataloguePredictionBankV1:
        del snapshot_payload
        policy = prediction_policy or Sgp4SupportPredictionPolicy()
        numbers = tuple(item.catalog_number for item in candidate_universe.candidates)
        self.calls.append((catalogue_field_delta_s, numbers))
        assert catalogue_field_delta_s == candidate_universe.catalogue_field_delta_s
        assert numbers == tuple(item.catalog_number for item in verified_tle_members)
        observation_ids = tuple(sorted(item.observation_id for item in support.observations))
        reference_ns = min(item.support_center_utc_ns for item in support.observations)
        candidates: list[CatalogueCandidatePredictionV1] = []
        for selected in candidate_universe.candidates:
            name, element_digest, epoch_ns = self.metadata[selected.catalog_number]
            tau_states = tuple(
                CandidateTauStateV1(
                    tau_s=point.tau_s,
                    log_prior_weight=point.log_prior_weight,
                    predictions=tuple(
                        CandidateObservationPredictionV1(
                            observation_id=observation_id,
                            predicted_cfo_hz=(
                                catalogue_field_delta_s * 0.125
                                + selected.catalog_number * 0.25
                                + point.tau_s * 2.0
                                + observation_index * 0.5
                            ),
                            standard_uncertainty_hz=(
                                1.0
                                + selected.catalog_number % 17 * 0.01
                                + observation_index * 0.001
                            ),
                        )
                        for observation_index, observation_id in enumerate(observation_ids)
                    ),
                )
                for point in tau_policy.points
            )
            candidates.append(
                CatalogueCandidatePredictionV1(
                    catalog_number=selected.catalog_number,
                    object_name=name,
                    selected_element_digest=element_digest,
                    element_epoch_utc_ns=epoch_ns,
                    element_age_s_at_reference=abs(reference_ns - epoch_ns) / 1e9,
                    eligible_episode_ids=selected.eligible_episode_ids,
                    tau_states=tau_states,
                )
            )
        configuration_digest = canonical_digest(
            {
                "algorithm_version": "sgp4-wgs72-local-cubic-diagonal-v1",
                "site_rf_authority_digest": site_rf_authority.content_digest,
                "prediction_policy_digest": policy.digest,
                "catalogue_field_delta_s": catalogue_field_delta_s,
            }
        )
        propagation_model = (
            f"sgp4-wgs72-local-cubic-diagonal-v1-{configuration_digest.removeprefix('sha256:')}"
        )
        return CataloguePredictionBankV1.create(
            support=support,
            tle_snapshot=tle_snapshot,
            observer_site=site_rf_authority.observer_site,
            nominal_rf_hz=site_rf_authority.nominal_rf_hz,
            selection_protocol_digest=candidate_universe.selection_protocol_digest,
            selection_policy_digest=candidate_universe.selection_policy_digest,
            tle_membership_authority_digest=(candidate_universe.tle_membership_authority_digest),
            verified_tle_members=verified_tle_members,
            propagation_model=propagation_model,
            candidates=tuple(candidates),
            source_candidate_count=len(candidates),
            tau_search_policy=tau_policy.policy,
        )


@dataclass(slots=True)
class _Fixture:
    support: CataloguePredictionSupportV1
    raw_tle: bytes
    tle_snapshot: TleSnapshotRefV1
    observer_site: ObserverSiteV1
    selection_protocol_digest: str
    tau_policy: ExactTauPolicy
    prediction_policy: Sgp4SupportPredictionPolicy
    inventory: SealedResponseFreeBankInventory
    expected_banks: dict[int, CataloguePredictionBankV1]
    fake_builder: _FakeBuilder


def _receipt_payload(receipt: SealedFieldBankReceipt) -> dict[str, object]:
    return {
        "field_delta_s": receipt.field_delta_s,
        "population_receipt_digest": receipt.population_receipt_digest,
        "selection_policy_digest": receipt.selection_policy_digest,
        "candidate_universe_digest": receipt.candidate_universe_digest,
        "prediction_bank_digest": receipt.prediction_bank_digest,
        "candidate_count": receipt.candidate_count,
        "candidates": [
            {
                "catalog_number": item.catalog_number,
                "object_name": item.object_name,
                "selected_element_digest": item.selected_element_digest,
                "element_epoch_utc_ns": item.element_epoch_utc_ns,
                "element_age_s_at_reference": item.element_age_s_at_reference,
            }
            for item in receipt.candidates
        ],
        "propagation_complete_for_association": True,
    }


def _inventory(
    archive_path: Path,
    archive_sha256: str,
    receipts: tuple[SealedFieldBankReceipt, ...],
) -> SealedResponseFreeBankInventory:
    payload = {
        "algorithm_version": "sealed-leading-field-bank-inventory-v1",
        "archive_sha256": archive_sha256,
        "field_banks": [_receipt_payload(item) for item in receipts],
        "response_section_parsed": False,
        "candidate_ranking_performed": False,
    }
    return SealedResponseFreeBankInventory(
        archive_path=archive_path.resolve().as_posix(),
        archive_sha256=archive_sha256,
        field_banks=receipts,
        content_digest=canonical_digest(payload),
    )


def _fixture(
    tmp_path: Path,
    *,
    candidate_count: int = 5,
    observation_count: int = 6,
    tau_count: int = 3,
) -> _Fixture:
    tmp_path.mkdir(parents=True, exist_ok=True)
    support = _support(observation_count)
    raw_tle = b"authenticated synthetic TLE fixture\n"
    tle_snapshot = TleSnapshotRefV1(
        provider="space-track",
        collected_utc_ns=1_700_000_000_000_000_000,
        digest=sha256_digest(raw_tle),
        object_count=candidate_count + 10,
    )
    observer_site = ObserverSiteV1(
        latitude_deg=37.0,
        longitude_deg=-122.0,
        altitude_m=12.0,
        label="fixture",
    )
    selection_protocol_digest = _digest("selection-protocol", 1)
    tau_policy = _tau_policy(tau_count)
    prediction_policy = Sgp4SupportPredictionPolicy(
        integration_sample_count=5,
        maximum_propagated_states=(candidate_count * observation_count * tau_count * 6 + 1),
    )
    reference_ns = min(item.support_center_utc_ns for item in support.observations)
    metadata = {
        50_000 + index: (
            f"STARLINK-{50_000 + index}",
            _digest("element", 50_000 + index),
            reference_ns - (index + 1) * 1_000_000_000,
        )
        for index in range(candidate_count)
    }
    fake_builder = _FakeBuilder(metadata=metadata, calls=[])
    members = tuple(
        CatalogueVerifiedTleMemberV1(
            catalog_number=number,
            selected_element_digest=values[1],
            element_epoch_utc_ns=values[2],
        )
        for number, values in metadata.items()
    )
    membership_digest = canonical_digest(
        {
            "algorithm_version": "response-free-tle-membership-authority-v1",
            "snapshot_digest": tle_snapshot.digest,
            "members": [item.model_dump(mode="json") for item in members],
        }
    )
    site_rf_authority = KnownSiteRfAuthority.create(
        observer_site=observer_site,
        nominal_rf_hz=11_440_312_498.0,
    )
    expected_banks: dict[int, CataloguePredictionBankV1] = {}
    receipts: list[SealedFieldBankReceipt] = []
    for field_delta_s in _FIELDS:
        selection_policy_digest = _digest("selection-policy", field_delta_s)
        universe = FrozenResponseFreeCandidateUniverse(
            candidates=tuple(
                FrozenCatalogueCandidate(
                    catalog_number=number,
                    eligible_episode_ids=support.episode_ids,
                )
                for number in metadata
            ),
            selection_protocol_digest=selection_protocol_digest,
            selection_policy_digest=selection_policy_digest,
            tle_membership_authority_digest=membership_digest,
            catalogue_field_delta_s=field_delta_s,
        )
        bank = fake_builder(
            support,
            raw_tle,
            tle_snapshot=tle_snapshot,
            site_rf_authority=site_rf_authority,
            candidate_universe=universe,
            verified_tle_members=members,
            tau_policy=tau_policy,
            prediction_policy=prediction_policy,
            catalogue_field_delta_s=field_delta_s,
        )
        expected_banks[field_delta_s] = bank
        receipts.append(
            SealedFieldBankReceipt(
                field_delta_s=field_delta_s,
                population_receipt_digest=_digest("population", field_delta_s),
                selection_policy_digest=selection_policy_digest,
                candidate_universe_digest=bank.candidate_universe_digest,
                prediction_bank_digest=bank.content_digest,
                candidate_count=len(bank.candidates),
                candidates=tuple(
                    SealedFieldCandidateReceipt(
                        catalog_number=item.catalog_number,
                        object_name=item.object_name,
                        selected_element_digest=item.selected_element_digest,
                        element_epoch_utc_ns=item.element_epoch_utc_ns,
                        element_age_s_at_reference=(item.element_age_s_at_reference),
                    )
                    for item in bank.candidates
                ),
                propagation_complete_for_association=True,
            )
        )
    archive_path = tmp_path / "sealed-result.json.zst"
    archive_bytes = b"sealed response-free fixture archive"
    archive_path.write_bytes(archive_bytes)
    inventory = _inventory(
        archive_path,
        sha256_digest(archive_bytes),
        tuple(receipts),
    )
    fake_builder.calls.clear()
    return _Fixture(
        support=support,
        raw_tle=raw_tle,
        tle_snapshot=tle_snapshot,
        observer_site=observer_site,
        selection_protocol_digest=selection_protocol_digest,
        tau_policy=tau_policy,
        prediction_policy=prediction_policy,
        inventory=inventory,
        expected_banks=expected_banks,
        fake_builder=fake_builder,
    )


def _compact_iterator(
    fixture: _Fixture,
    output: Path,
    *,
    compact_policy: CompactFieldBankRebuildPolicy | None = None,
):
    return iter_rebuilt_digest_identical_compact_field_banks(
        fixture.support,
        fixture.raw_tle,
        tle_snapshot=fixture.tle_snapshot,
        observer_site=fixture.observer_site,
        nominal_rf_hz=11_440_312_498.0,
        selection_protocol_digest=fixture.selection_protocol_digest,
        tau_policy=fixture.tau_policy,
        prediction_policy=fixture.prediction_policy,
        inventory=fixture.inventory,
        storage_directory=output,
        compact_policy=compact_policy,
    )


def test_compact_rebuild_is_lazy_complete_and_public_digest_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    monkeypatch.setattr(
        rebuild_module,
        "build_sgp4_catalogue_prediction_bank",
        fixture.fake_builder,
    )
    output = tmp_path / "compact"
    output.mkdir()
    iterator = _compact_iterator(
        fixture,
        output,
        compact_policy=CompactFieldBankRebuildPolicy(candidate_chunk_size=2),
    )

    assert fixture.fake_builder.calls == []
    first = next(iterator)
    assert {item[0] for item in fixture.fake_builder.calls} == {-500}
    assert max(len(item[1]) for item in fixture.fake_builder.calls) == 2
    assert first.content_digest == fixture.expected_banks[-500].content_digest
    assert first.candidate_universe_digest == (
        fixture.expected_banks[-500].candidate_universe_digest
    )
    assert first.prediction_shape == (5, 3, 6)
    assert first.prediction_reference_utc_ns == (
        fixture.expected_banks[-500].prediction_reference_utc_ns
    )
    assert first.source_candidate_count == first.returned_candidate_count == 5
    assert first.response_accessed is False
    assert first.truncated_candidate_count == 0
    assert first.complete_tau_inventory is True
    assert first.public_contract_materialized is False
    assert not hasattr(first, "candidates")
    with pytest.raises(
        CompactCataloguePredictionBankError,
        match="prediction reference",
    ):
        replace(
            first,
            prediction_reference_utc_ns=first.prediction_reference_utc_ns + 1,
        )
    with pytest.raises(CompactCataloguePredictionBankError, match="prediction shape"):
        replace(first, source_candidate_count=first.source_candidate_count + 1)
    verify_compact_catalogue_prediction_bank(first)

    with open_compact_prediction_arrays(first, verify_hashes=False) as (
        predictions,
        uncertainties,
    ):
        assert predictions.shape == first.prediction_shape
        assert uncertainties.shape == first.prediction_shape
        assert predictions.flags.writeable is False
        assert uncertainties.flags.writeable is False
    assert (
        materialize_compact_candidate(
            first,
            4,
            verify_hashes=False,
        )
        == fixture.expected_banks[-500].candidates[4]
    )
    with open_compact_catalogue_prediction_array_bank_view(first) as pure_view:
        public_view = catalogue_prediction_array_view_from_bank(
            fixture.expected_banks[-500],
            field_delta_s=-500,
        )
        assert pure_view.public_bank_content_digest == first.content_digest
        assert pure_view.prediction_inventory_authority_digest == (
            public_view.prediction_inventory_authority_digest
        )
        assert pure_view.prediction_inventory_authority_digest != first.content_digest
        assert pure_view.prediction_reference_utc_ns == first.prediction_reference_utc_ns
        assert pure_view.candidate_catalog_numbers == tuple(
            item.catalog_number for item in fixture.expected_banks[-500].candidates
        )
        assert pure_view.tau_values_s == tuple(
            item.tau_s for item in fixture.expected_banks[-500].candidates[0].tau_states
        )
        assert pure_view.predicted_cfo_hz.flags.writeable is False
        assert pure_view.standard_uncertainty_hz.flags.writeable is False
        assert not hasattr(pure_view, "predicted_cfo_array_path")

    remaining = list(iterator)
    compact_banks = (first, *remaining)
    assert tuple(item.field_delta_s for item in compact_banks) == _FIELDS
    assert tuple(item.content_digest for item in compact_banks) == tuple(
        fixture.expected_banks[field].content_digest for field in _FIELDS
    )
    assert all(len(numbers) <= 2 for _, numbers in fixture.fake_builder.calls)
    assert len(tuple(output.glob("*.npy"))) == 6


def test_compact_rebuild_rejects_digest_storage_and_chronology_poison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    monkeypatch.setattr(
        rebuild_module,
        "build_sgp4_catalogue_prediction_bank",
        fixture.fake_builder,
    )

    digest_output = tmp_path / "digest-output"
    digest_output.mkdir()
    bad_receipts = (
        replace(
            fixture.inventory.field_banks[0],
            prediction_bank_digest=_digest("wrong-bank", 1),
        ),
        *fixture.inventory.field_banks[1:],
    )
    fixture.inventory = _inventory(
        Path(fixture.inventory.archive_path),
        fixture.inventory.archive_sha256,
        bad_receipts,
    )
    with pytest.raises(LongArcObservabilityRebuildError, match="prediction-bank"):
        next(_compact_iterator(fixture, digest_output))
    assert tuple(digest_output.iterdir()) == ()

    fixture = _fixture(tmp_path / "inventory-fixture")
    monkeypatch.setattr(
        rebuild_module,
        "build_sgp4_catalogue_prediction_bank",
        fixture.fake_builder,
    )
    inventory_output = tmp_path / "inventory-output"
    inventory_output.mkdir()
    fixture.inventory = replace(
        fixture.inventory,
        content_digest=_digest("poisoned-inventory", 1),
    )
    with pytest.raises(LongArcObservabilityRebuildError, match="does not close"):
        next(_compact_iterator(fixture, inventory_output))
    assert fixture.fake_builder.calls == []
    assert tuple(inventory_output.iterdir()) == ()

    fixture = _fixture(tmp_path / "chronology-fixture")
    monkeypatch.setattr(
        rebuild_module,
        "build_sgp4_catalogue_prediction_bank",
        fixture.fake_builder,
    )
    fixture.tle_snapshot = TleSnapshotRefV1(
        provider=fixture.tle_snapshot.provider,
        collected_utc_ns=min(item.support_start_utc_ns for item in fixture.support.observations),
        digest=fixture.tle_snapshot.digest,
        object_count=fixture.tle_snapshot.object_count,
    )
    chronology_output = tmp_path / "chronology-output"
    chronology_output.mkdir()
    with pytest.raises(LongArcObservabilityRebuildError, match="pre-measurement"):
        next(_compact_iterator(fixture, chronology_output))
    assert fixture.fake_builder.calls == []
    assert tuple(chronology_output.iterdir()) == ()

    fixture = _fixture(tmp_path / "qnap-fixture")
    monkeypatch.setattr(
        rebuild_module,
        "build_sgp4_catalogue_prediction_bank",
        fixture.fake_builder,
    )
    with pytest.raises(LongArcObservabilityRebuildError, match="QNAP"):
        next(_compact_iterator(fixture, Path("/mnt/qnap01/forbidden-compact")))
    assert fixture.fake_builder.calls == []


def test_compact_array_hash_detects_post_commit_poison(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)
    monkeypatch.setattr(
        rebuild_module,
        "build_sgp4_catalogue_prediction_bank",
        fixture.fake_builder,
    )
    output = tmp_path / "compact"
    output.mkdir()
    bank = next(_compact_iterator(fixture, output))
    prediction_path = Path(bank.predicted_cfo_array_path)
    with prediction_path.open("r+b") as stream:
        stream.seek(-1, 2)
        final_byte = stream.read(1)
        stream.seek(-1, 2)
        stream.write(bytes((final_byte[0] ^ 0x01,)))

    with pytest.raises(CompactCataloguePredictionBankError, match="hash drifted"):
        verify_compact_catalogue_prediction_bank(bank)


def test_compact_work_caps_fail_before_builder_or_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, candidate_count=4, observation_count=8)
    monkeypatch.setattr(
        rebuild_module,
        "build_sgp4_catalogue_prediction_bank",
        fixture.fake_builder,
    )
    output = tmp_path / "compact"
    output.mkdir()
    policy = CompactFieldBankRebuildPolicy(
        candidate_chunk_size=1,
        maximum_prediction_cells_per_field=95,
    )

    with pytest.raises(LongArcObservabilityRebuildError, match="prediction cells"):
        next(_compact_iterator(fixture, output, compact_policy=policy))
    assert fixture.fake_builder.calls == []
    assert tuple(output.iterdir()) == ()


def test_compact_rebuild_scaled_peak_heap_is_chunk_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate_count = 72
    observation_count = 96
    tau_count = 9
    fixture = _fixture(
        tmp_path,
        candidate_count=candidate_count,
        observation_count=observation_count,
        tau_count=tau_count,
    )
    fixture.expected_banks.clear()
    fixture.fake_builder.calls.clear()
    gc.collect()
    monkeypatch.setattr(
        rebuild_module,
        "build_sgp4_catalogue_prediction_bank",
        fixture.fake_builder,
    )
    output = tmp_path / "compact"
    output.mkdir()
    policy = CompactFieldBankRebuildPolicy(
        candidate_chunk_size=2,
        maximum_prediction_cells_per_field=100_000,
    )

    tracemalloc.start()
    banks: tuple[CompactCataloguePredictionBank, ...]
    try:
        banks = tuple(_compact_iterator(fixture, output, compact_policy=policy))
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    logical_prediction_entries = len(_FIELDS) * candidate_count * tau_count * observation_count
    assert logical_prediction_entries == 186_624
    assert (
        tuple(item.prediction_shape for item in banks)
        == ((candidate_count, tau_count, observation_count),) * 3
    )
    assert max(len(numbers) for _, numbers in fixture.fake_builder.calls) == 2
    assert peak_bytes < 32_000_000
    # This message is intentionally visible under ``pytest -s`` so the measured
    # qualification value, rather than only the cap, can be reported upstream.
    print(
        "compact scaled peak: "
        f"{peak_bytes} bytes for {logical_prediction_entries} public prediction entries"
    )
