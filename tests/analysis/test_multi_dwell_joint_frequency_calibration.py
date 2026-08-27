from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from leo.analysis.joint_frequency_calibration import (
    JointFrequencyCalibrationConfig,
    ReceiverComponentOffsetPrior,
    ReceiverHardwareDriftPrior,
)
from leo.analysis.multi_dwell_catalogue_adapter import (
    adapt_catalogue_dwells_to_filter_inputs,
)
from leo.analysis.multi_dwell_catalogue_persistence import (
    build_multi_dwell_catalogue_posterior,
)
from leo.analysis.multi_dwell_catalogue_smoothing import MultiDwellFilterConfig
from leo.analysis.multi_dwell_joint_frequency_calibration import (
    calibrate_multi_dwell_history_frequencies,
)
from leo.analysis.satellite_correction_replay import SatelliteCorrectionInputError
from leo.contracts.catalogue_association import CataloguePredictionBankV1
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import TleSnapshotRefV1
from tests.analysis.test_multi_dwell_catalogue_adapter import (
    _dwell_graph,
    _prediction_bank,
)


def _inputs() -> tuple[Any, ...]:
    graphs = (_dwell_graph(0), _dwell_graph(1))
    banks = tuple(_prediction_bank(item) for item in graphs)
    adapted = adapt_catalogue_dwells_to_filter_inputs(
        graphs=graphs,
        prediction_banks=banks,
    )
    config = MultiDwellFilterConfig(
        initial_candidate_log_weight=2.0,
        initial_null_log_weight=-2.0,
        dwell_offset_prior_standard_uncertainty_hz=100.0,
        null_prediction_standard_uncertainty_hz=1.0,
    )
    posterior = build_multi_dwell_catalogue_posterior(
        dwells=adapted.dwells,
        prediction_bank=adapted.prediction_bank,
        config=config,
    )
    component_priors = tuple(
        ReceiverComponentOffsetPrior(
            continuity_component_id=graph.episodes[0].continuity_component_id,
            mean_hz=0.0,
            standard_uncertainty_hz=100.0,
        )
        for graph in graphs
    )
    hardware_priors = (
        ReceiverHardwareDriftPrior(
            hardware_epoch_id="receiver-a",
            reference_utc_ns=adapted.dwells[0].center_utc_ns,
            mean_hz_s=0.0,
            standard_uncertainty_hz_s=5.0,
        ),
    )
    return graphs, banks, adapted, posterior, component_priors, hardware_priors


def test_calibrates_sequential_histories_without_relabelling_association() -> None:
    graphs, banks, adapted, posterior, component_priors, hardware_priors = _inputs()

    result = calibrate_multi_dwell_history_frequencies(
        posterior=posterior,
        graphs=graphs,
        prediction_banks=banks,
        component_priors=component_priors,
        hardware_priors=hardware_priors,
        receiver_frequency_reference_authority_digest=canonical_digest(
            {"receiver-frequency": "synthetic"}
        ),
        receiver_frequency_gauge_resolved=True,
        calibration_config=JointFrequencyCalibrationConfig(
            minimum_observations_per_satellite=4,
            minimum_span_s_per_satellite=1.0,
        ),
    )

    assert result.source_posterior_digest == posterior.content_digest
    assert result.adapter_result_digest == adapted.content_digest
    assert result.sequential_history_posterior_preserved
    assert result.association_result_relabelled is False
    assert result.transferable_correction_emitted is False
    assert result.receiver_local_state_exportable is False
    assert result.identity_claimed is False
    assert result.mode_calibrations
    assert all(
        item.estimate.association_mode_digest == item.history_mode_digest
        for item in result.mode_calibrations
    )
    assert any(
        item.active_catalog_numbers == (10_001,) and item.estimate.calibration_evidence_eligible
        for item in result.mode_calibrations
    )


def test_unresolved_receiver_frequency_gauge_keeps_every_mode_ineligible() -> None:
    graphs, banks, _adapted, posterior, component_priors, hardware_priors = _inputs()

    result = calibrate_multi_dwell_history_frequencies(
        posterior=posterior,
        graphs=graphs,
        prediction_banks=banks,
        component_priors=component_priors,
        hardware_priors=hardware_priors,
        receiver_frequency_reference_authority_digest=canonical_digest(
            {"receiver-frequency": "unresolved"}
        ),
        receiver_frequency_gauge_resolved=False,
    )

    assert result.mode_calibrations
    assert all(not item.estimate.calibration_evidence_eligible for item in result.mode_calibrations)


def test_posterior_response_lineage_must_match_exact_adapter() -> None:
    graphs, banks, adapted, posterior, component_priors, hardware_priors = _inputs()
    changed_graphs = (graphs[0], _dwell_graph(1, response_shift_hz=1.0))
    changed_banks = (banks[0], _prediction_bank(changed_graphs[1]))
    assert (
        adapt_catalogue_dwells_to_filter_inputs(
            graphs=changed_graphs,
            prediction_banks=changed_banks,
        ).prediction_bank
        == adapted.prediction_bank
    )

    with pytest.raises(SatelliteCorrectionInputError, match="exact graph/bank"):
        calibrate_multi_dwell_history_frequencies(
            posterior=posterior,
            graphs=changed_graphs,
            prediction_banks=changed_banks,
            component_priors=component_priors,
            hardware_priors=hardware_priors,
            receiver_frequency_reference_authority_digest=canonical_digest(
                {"receiver-frequency": "synthetic"}
            ),
            receiver_frequency_gauge_resolved=True,
        )


def test_calibration_requires_one_exact_tle_member_inventory() -> None:
    graphs, banks, _adapted, posterior, component_priors, hardware_priors = _inputs()
    source = banks[1]
    changed_second = CataloguePredictionBankV1.create(
        support=source.support,
        tle_snapshot=TleSnapshotRefV1(
            provider=source.tle_snapshot.provider,
            collected_utc_ns=source.tle_snapshot.collected_utc_ns,
            digest=canonical_digest({"snapshot": "different"}),
            object_count=source.tle_snapshot.object_count,
        ),
        observer_site=source.observer_site,
        nominal_rf_hz=source.nominal_rf_hz,
        selection_protocol_digest=source.selection_protocol_digest,
        selection_policy_digest=source.selection_policy_digest,
        tle_membership_authority_digest=source.tle_membership_authority_digest,
        verified_tle_members=source.verified_tle_members,
        propagation_model=source.propagation_model,
        candidates=source.candidates,
        source_candidate_count=source.source_candidate_count,
        tau_search_policy=source.tau_search_policy,
    )

    with pytest.raises(SatelliteCorrectionInputError, match="one exact TLE"):
        calibrate_multi_dwell_history_frequencies(
            posterior=posterior,
            graphs=graphs,
            prediction_banks=(banks[0], changed_second),
            component_priors=component_priors,
            hardware_priors=hardware_priors,
            receiver_frequency_reference_authority_digest=canonical_digest(
                {"receiver-frequency": "synthetic"}
            ),
            receiver_frequency_gauge_resolved=True,
        )


def test_missing_receiver_prior_fails_closed() -> None:
    graphs, banks, _adapted, posterior, component_priors, _hardware_priors = _inputs()

    with pytest.raises(SatelliteCorrectionInputError, match="hardware"):
        calibrate_multi_dwell_history_frequencies(
            posterior=posterior,
            graphs=graphs,
            prediction_banks=banks,
            component_priors=component_priors,
            hardware_priors=(),
            receiver_frequency_reference_authority_digest=canonical_digest(
                {"receiver-frequency": "synthetic"}
            ),
            receiver_frequency_gauge_resolved=True,
        )


def test_history_mode_probability_change_alters_posterior_digest_join() -> None:
    graphs, banks, _adapted, posterior, component_priors, hardware_priors = _inputs()
    poisoned = posterior.model_copy(
        update={"source_evidence_digest": canonical_digest({"response": "poison"})}
    )

    with pytest.raises(ValidationError, match="digest"):
        calibrate_multi_dwell_history_frequencies(
            posterior=poisoned,
            graphs=graphs,
            prediction_banks=banks,
            component_priors=component_priors,
            hardware_priors=hardware_priors,
            receiver_frequency_reference_authority_digest=canonical_digest(
                {"receiver-frequency": "synthetic"}
            ),
            receiver_frequency_gauge_resolved=True,
        )
