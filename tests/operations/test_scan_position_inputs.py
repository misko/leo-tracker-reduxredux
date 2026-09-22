from types import SimpleNamespace

import numpy as np

import leo.operations.scan_position_inputs as subject
from leo.analysis.nearest_neighbour_association import (
    deterministic_randomized_observation_partition,
)
from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import ObserverSiteV1
from leo.sky.sites import resolve_preset


class _Satellite:
    def sgp4_array(self, jd, fraction):
        seconds = (np.asarray(jd) + np.asarray(fraction) - 2440587.5) * 86400.0
        position = np.column_stack((7000.0 + seconds * 0.001, seconds * 0, seconds * 0))
        velocity = np.tile((0.0, 7.5, 0.0), (len(seconds), 1))
        return np.zeros(len(seconds), dtype=int), position, velocity


def _row(identity, utc):
    return SimpleNamespace(
        observation_id=identity,
        support_center_utc_ns=utc,
        support_start_utc_ns=utc - 10,
        support_end_utc_ns=utc + 10,
        measured_cfo_hz=100.0,
    )


def test_prepare_preserves_saved_partition_and_excludes_overlapping_track(monkeypatch):
    start = 2_000_000_000_000
    rows = tuple(
        _row(canonical_digest({"obs": number}), start + number * 1_000_000_000)
        for number in range(14)
    )
    overlap = rows[:4] + tuple(
        _row(canonical_digest({"other": number}), start + (4 + number) * 1_000_000_000)
        for number in range(10)
    )
    graph_a = SimpleNamespace(observations=rows)
    graph_b = SimpleNamespace(observations=overlap)
    hypothesis = SimpleNamespace(tracklet_ids=("track-a", "track-b"))
    trajectory = SimpleNamespace(hypotheses=(hypothesis,), tracklets=())
    monkeypatch.setattr(subject, "project_scanner_candidates", lambda source: ())
    monkeypatch.setattr(
        subject, "reconstruct_persistent_hop_trajectories", lambda *a, **k: trajectory
    )
    monkeypatch.setattr(
        subject,
        "persistent_hop_tracklet_graph",
        lambda _hypothesis, tracklet_id: {"track-a": graph_a, "track-b": graph_b}[tracklet_id],
    )
    monkeypatch.setattr(
        subject,
        "CataloguePredictionSupportV1",
        SimpleNamespace(
            from_graph=lambda graph: SimpleNamespace(content_digest="sha256:" + "1" * 64)
        ),
    )
    catalogue = SimpleNamespace(
        satellite_numbers=(100, 101),
        satellites=(_Satellite(), _Satellite()),
        element_epoch_utc_ns=lambda: (start - 10_000_000_000, start - 20_000_000_000),
        __len__=lambda self: 2,
    )

    # SimpleNamespace has no special-method lookup for len.
    class _Catalogue:
        satellite_numbers = catalogue.satellite_numbers
        satellites = catalogue.satellites

        def element_epoch_utc_ns(self):
            return catalogue.element_epoch_utc_ns()

        def __len__(self):
            return 2

    monkeypatch.setattr(subject, "parse_element_sets", lambda payload: _Catalogue())
    monkeypatch.setattr(subject, "timing_is_qualified_for_tle", lambda timing: True)

    preset = resolve_preset("spinnaker-sausalito")
    site = ObserverSiteV1(
        label=preset.label,
        latitude_deg=preset.latitude_deg,
        longitude_deg=preset.longitude_deg,
        altitude_m=preset.altitude_m,
    )
    # This is the literal protocol in scanner_tle_review_report.build_report,
    # rather than the preparation helper under test.
    selection = canonical_digest(
        {
            "algorithm": "scanner-shared-tracking-v12",
            "utc_qualification_limit_ns": 2_000_000_000,
            "trajectory": PersistentHopTrajectoryConfig().digest,
            "group_limit": 4,
            "selection": "eligible-first-longest-support-v1",
            "catalogue": "exclude-labelled-debris-and-sgp4-failures-before-response-v1",
            "observer": preset.model_dump(mode="json"),
        }
    )
    seed = canonical_digest(
        {
            "policy": "persistent-hop-fixed-orbit-randomized-residual-v1",
            "response_free_support_digest": "sha256:" + "1" * 64,
            "selection_protocol_digest": selection,
        }
    )
    training, evaluation = deterministic_randomized_observation_partition(
        tuple(row.observation_id for row in rows), training_fraction=0.6, split_seed=seed
    )
    candidate = SimpleNamespace(catalog_number=100, selected_tau_s=5.0)
    review_a = SimpleNamespace(
        tracklet_id="track-a",
        candidates=(candidate, SimpleNamespace(catalog_number=101, selected_tau_s=-4.0)),
        fit_observation_count=len(training),
        randomized_evaluation_observation_count=len(evaluation),
    )
    training_b, evaluation_b = deterministic_randomized_observation_partition(
        tuple(row.observation_id for row in overlap), training_fraction=0.6, split_seed=seed
    )
    review_b = SimpleNamespace(
        tracklet_id="track-b",
        candidates=(candidate,),
        fit_observation_count=len(training_b),
        randomized_evaluation_observation_count=len(evaluation_b),
    )
    snapshot = SimpleNamespace(
        digest="sha256:" + "2" * 64, collected_utc_ns=start - 600_000_000_000
    )
    product = SimpleNamespace(
        track_reviews=(review_a, review_b),
        original_tle_snapshot=SimpleNamespace(digest=snapshot.digest),
        observer_site=site,
        input_manifest_sha256="sha256:" + "3" * 64,
        analysis_manifest_sha256="sha256:" + "4" * 64,
        model_dump=lambda mode: {"session_id": "target"},
    )
    source = SimpleNamespace(
        session_id="target",
        radio_id="radio-a",
        capture_start_utc_ns=start,
        timing=SimpleNamespace(first_sample_estimate_utc_ns=start),
        input_manifest_sha256="sha256:" + "3" * 64,
        analysis_manifest_sha256="sha256:" + "4" * 64,
    )
    inputs = SimpleNamespace(
        load=lambda session_id: source,
        session_ids=lambda: ("target",),
        captured_at=lambda session_id: start,
    )
    products = SimpleNamespace(
        status=lambda session_id: SimpleNamespace(state="complete", product=product)
    )
    archive = SimpleNamespace(
        select_latest_before=lambda utc: snapshot,
        read=lambda selected: "catalogue",
    )

    prepared = subject.prepare_scan_position_inputs(
        "target", inputs=inputs, products=products, archive=archive
    )

    assert len(prepared.target_episodes) == len(prepared.episodes) == 1
    episode = prepared.episodes[0]
    assert tuple(episode.observation_id) == tuple(row.observation_id for row in rows)
    assert set(episode.observation_id[episode.training]) == set(training)
    assert tuple(episode.candidate_id) == (100, 101)
    assert episode.pass_id == "target:100"
    assert any(item.reason == "overlapping-alternative-hypothesis" for item in prepared.exclusions)
    assert prepared.provenance[0].site_conditioned is True
    assert prepared.provenance[0].shortlist_calibrated_probabilities is False
    assert episode.phase_position_minus2_ecef_km.shape == (2, 14, 3)
    assert episode.phase_position_plus2_ecef_km.shape == (2, 14, 3)

    calls = []
    public_phase_state = subject.phase_state

    def phase_state(*args, **kwargs):
        calls.append(kwargs)
        return public_phase_state(*args, **kwargs)

    monkeypatch.setattr(subject, "phase_state", phase_state)
    audit = subject.verify_orbit_fit(
        prepared,
        {
            "latitude_deg": preset.latitude_deg,
            "longitude_deg": preset.longitude_deg,
            "diagnostics": {"rate_corrections_s_h": {"100": 0.01}},
        },
    )
    assert audit["compared_observation_count"] == 14
    assert len(calls) == 2
    assert all(call["minus2"] is not None and call["plus2"] is not None for call in calls)


def test_shifted_orbit_uses_original_receive_time_for_earth_rotation():
    satellite = _Satellite()
    utc = np.asarray([2_000_000_000_000], dtype=np.int64)
    position, velocity = subject._propagate(satellite, utc, 1.0)
    shifted_jd, shifted_fraction = subject.julian_day_from_utc_ns(utc + 1_000_000_000)
    _, teme_position, teme_velocity = satellite.sgp4_array(shifted_jd, shifted_fraction)
    original_jd, original_fraction = subject.julian_day_from_utc_ns(utc)
    expected = subject.teme_to_ecef(
        teme_position,
        teme_velocity,
        subject.greenwich_mean_sidereal_time_rad(original_jd, original_fraction),
    )
    np.testing.assert_allclose(position, expected[0])
    np.testing.assert_allclose(velocity, expected[1])


def test_history_limit_is_filled_by_completed_same_radio_sessions(monkeypatch):
    start = 40_000_000_000_000
    monkeypatch.setattr(subject, "timing_is_qualified_for_tle", lambda timing: True)

    def source(session_id, radio="radio-a"):
        instant = {
            "target": start,
            "new-incomplete": start - 1_000_000_000,
            "other-radio": start - 2_000_000_000,
            "older-complete": start - 3_000_000_000,
        }[session_id]
        return SimpleNamespace(
            session_id=session_id,
            radio_id=radio,
            capture_start_utc_ns=instant,
            timing=SimpleNamespace(first_sample_estimate_utc_ns=instant),
            input_manifest_sha256="sha256:" + "3" * 64,
            analysis_manifest_sha256="sha256:" + "4" * 64,
        )

    sources = {
        "target": source("target"),
        "new-incomplete": source("new-incomplete"),
        "other-radio": source("other-radio", "radio-b"),
        "older-complete": source("older-complete"),
    }
    complete_product = SimpleNamespace(
        track_reviews=(SimpleNamespace(tracklet_id="unused"),),
        original_tle_snapshot=None,
        input_manifest_sha256="sha256:" + "3" * 64,
        analysis_manifest_sha256="sha256:" + "4" * 64,
        model_dump=lambda mode: {"complete": True},
    )

    def status(session_id):
        if session_id == "older-complete":
            return SimpleNamespace(state="complete", product=complete_product)
        return SimpleNamespace(state="pending", product=None)

    inputs = SimpleNamespace(
        load=lambda session_id: sources[session_id],
        session_ids=lambda: tuple(sources),
        captured_at=lambda session_id: sources[session_id].capture_start_utc_ns,
    )
    prepared = subject.prepare_scan_position_inputs(
        "target",
        inputs=inputs,
        products=SimpleNamespace(status=status),
        archive=SimpleNamespace(),
        maximum_history_sessions=1,
    )

    assert tuple(item.session_id for item in prepared.provenance) == (
        "target",
        "older-complete",
    )
    assert prepared.target_source.radio_id == "radio-a"
    assert prepared.source_manifest[0]["session_id"] == "target"


def test_unqualified_target_is_bindable_without_catalogue_or_corpus_traversal(monkeypatch):
    estimate = 9_000_000_000
    source = SimpleNamespace(
        session_id="unqualified",
        radio_id="radio-a",
        capture_start_utc_ns=None,
        timing=SimpleNamespace(first_sample_estimate_utc_ns=estimate),
        input_manifest_sha256="sha256:" + "3" * 64,
        analysis_manifest_sha256="sha256:" + "4" * 64,
    )
    product = SimpleNamespace(
        input_manifest_sha256=source.input_manifest_sha256,
        analysis_manifest_sha256=source.analysis_manifest_sha256,
        model_dump=lambda mode: {"session_id": "unqualified", "immutable": True},
    )
    monkeypatch.setattr(subject, "timing_is_qualified_for_tle", lambda timing: False)

    class Inputs:
        def load(self, session_id):
            assert session_id == "unqualified"
            return source

        def session_ids(self):
            raise AssertionError("unqualified target must not traverse the corpus")

    class Archive:
        def select_latest_before(self, utc_ns):
            raise AssertionError("unqualified target must not query causal TLEs")

    prepared = subject.prepare_scan_position_inputs(
        "unqualified",
        inputs=Inputs(),
        products=SimpleNamespace(
            status=lambda session_id: SimpleNamespace(state="complete", product=product)
        ),
        archive=Archive(),
    )

    assert prepared.episodes == prepared.target_episodes == ()
    assert prepared.target_source.capture_start_utc_ns == estimate
    assert prepared.provenance[0].tracking_product_sha256 is not None
    assert prepared.source_manifest[0]["input_manifest_sha256"] == source.input_manifest_sha256
    assert prepared.exclusions[0].reason == "utc-unqualified"
    assert prepared.coverage.selected_track_count == 0
    assert prepared.coverage.observation_count == 0
