import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from leo.cli.backend import CliBackendError
from leo.cli.composition import CliSettings, CompositionHooks, LocalAcquisitionBackend
from leo.cli.scanner_glrt import (
    existing_scanner_glrt_warning,
    publish_scanner_glrt,
    scanner_glrt_options,
)
from leo.radio.scanner_glrt_metadata import ScannerGlrtOptions
from leo.storage.scanner_glrt import ScannerGlrtStore
from tests.cli.test_persistent_hop_schedule import (
    _BoundedPersistentRadio,
    _Lifecycle,
    _RecordingAuthority,
    _RecordingStore,
    _settings,
)
from tests.scanner.glrt_publication_fixtures import (
    ALGORITHM,
    CONFIGURATION,
    make_capture,
    make_evidence,
    make_publication,
)

OPTIONS = ScannerGlrtOptions(ALGORITHM, CONFIGURATION)


def test_opt_in_requires_exact_identities_and_explicit_decision_mode():
    assert scanner_glrt_options({}) is None
    good = {
        "LEO_SCANNER_GLRT_MODE": "unqualified-evidence",
        "LEO_SCANNER_GLRT_ALGORITHM_SHA256": ALGORITHM,
        "LEO_SCANNER_GLRT_CONFIGURATION_SHA256": CONFIGURATION,
    }
    assert scanner_glrt_options(good) == OPTIONS
    positive = scanner_glrt_options(good | {"LEO_SCANNER_GLRT_MODE": "positive-only-v1"})
    assert positive == ScannerGlrtOptions(ALGORITHM, CONFIGURATION, mode="positive-only-v1")
    for update in (
        {"LEO_SCANNER_GLRT_MODE": "qualified"},
        {"LEO_SCANNER_GLRT_MODE": "disabled"},
        {"LEO_SCANNER_GLRT_ALGORITHM_SHA256": "0" * 64},
        {"LEO_SCANNER_GLRT_CONFIGURATION_SHA256": "bad"},
        {"LEO_SCANNER_GLRT_DRAIN_BUDGET_SECONDS": "nan"},
        {"LEO_SCANNER_GLRT_DRAIN_BUDGET_SECONDS": "11"},
    ):
        with pytest.raises(ValueError):
            scanner_glrt_options(good | update)
    with pytest.raises(CliBackendError):
        CliSettings.from_environ(good)


def test_runtime_mode_requires_persistent_scanner_and_passes_options_to_radio(
    tmp_path, monkeypatch
):
    original = _settings(tmp_path)
    for update in ({"scanner_enabled": False}, {"scanner_capture_mode": "sequential"}):
        with pytest.raises(ValueError, match="enabled persistent-hop"):
            replace(original, scanner_glrt=OPTIONS, **update)
    settings = replace(original, scanner_glrt=OPTIONS)
    constructed = []
    monkeypatch.setattr(
        "leo.cli.composition.PlutoPersistentHopRadio",
        lambda *args, **kwargs: constructed.append((args, kwargs)),
    )
    LocalAcquisitionBackend(settings)._persistent_hop_radio(settings.radios[0])
    assert constructed[0][1]["scanner_glrt"] == OPTIONS
    assert constructed[0][0] == ("192.168.1.18",)
    assert constructed[0][1]["expected_serial"] == "serial-a"


def test_complete_environment_opt_in_preserves_existing_scanner_geometry(tmp_path):
    original = _settings(tmp_path)
    manifest = original.scanner_persistent_iiod_binary_path.parent / "bundle.json"
    manifest.write_text('{"checked_by_ppu_at_entry": true}')
    settings = CliSettings.from_environ(
        {
            "LEO_RADIO_BACKEND": "pluto",
            "LEO_RADIOS_JSON": json.dumps([radio.model_dump() for radio in original.radios]),
            "LEO_BULK_ROOT": str(original.bulk_root),
            "LEO_SCANNER_ENABLED": "true",
            "LEO_SCANNER_RADIO_ID": original.scanner_radio_id,
            "LEO_SCANNER_CAPTURE_MODE": "persistent_hop",
            "LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH": str(
                original.scanner_persistent_iiod_binary_path
            ),
            "CREDENTIALS_DIRECTORY": str(original.scanner_persistent_credentials_directory),
            "LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH": str(manifest),
            "LEO_SCANNER_GLRT_MODE": "unqualified-evidence",
            "LEO_SCANNER_GLRT_ALGORITHM_SHA256": ALGORITHM,
            "LEO_SCANNER_GLRT_CONFIGURATION_SHA256": CONFIGURATION,
            "LEO_SCANNER_GLRT_DRAIN_BUDGET_SECONDS": "3",
        }
    )
    assert settings.scanner_glrt == ScannerGlrtOptions(ALGORITHM, CONFIGURATION, 3)
    assert settings.scanner_persistent_iiod_bundle_manifest_path == manifest
    constructed = []
    hooks = CompositionHooks(persistent_hop_iiod_lifecycle_factory=constructed.append)
    LocalAcquisitionBackend(settings, hooks=hooks)._persistent_hop_iiod_lifecycle(
        settings.radios[0]
    )
    assert constructed[0].bundle_manifest_path == manifest
    for field in (
        "scanner_run_seconds",
        "scanner_dwell_ms",
        "scanner_interval_seconds",
        "scanner_persistent_transition_guard_us",
        "scanner_persistent_kernel_buffers",
        "scanner_persistent_samples_per_block",
        "scanner_persistent_read_ahead_visits",
        "scanner_persistent_queue_capacity_visits",
    ):
        assert getattr(settings, field) == getattr(original, field)


def test_bundle_option_does_not_enable_detector_and_rejects_relative_paths(tmp_path):
    settings = _settings(tmp_path)
    assert settings.scanner_persistent_iiod_bundle_manifest_path is None
    manifest = settings.scanner_persistent_iiod_binary_path.parent / "bundle.json"
    manifest.write_text("{}")
    assert (
        replace(settings, scanner_persistent_iiod_bundle_manifest_path=manifest).scanner_glrt
        is None
    )
    with pytest.raises(ValueError):
        replace(settings, scanner_persistent_iiod_bundle_manifest_path=Path("relative.json"))
    with pytest.raises(CliBackendError, match="absolute path and iiOD binary"):
        CliSettings.from_environ(
            {"LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH": str(manifest)}
        )


class EvidenceRadio(_BoundedPersistentRadio):
    def __init__(self, lifecycle, events, *, wrong_session=False):
        super().__init__(events)
        self.iiod = lifecycle
        self.wrong_session = wrong_session
        self.receipt = None
        self.evidence_reads = 0

    def begin_session(self, plan, *, session_id):
        session = super().begin_session(plan, session_id=session_id)
        self.receipt = session.finish()
        return session

    @property
    def classification_error(self):
        return None

    @property
    def classification_evidence(self):
        assert self.close_count == self.iiod.exit_count == 1
        self.evidence_reads += 1
        self.events.append("glrt.read-after-close")
        evidence = make_evidence(self.receipt)
        if self.wrong_session:
            evidence = evidence.model_copy(update={"session": evidence.session + 1})
        return evidence


def capture_once(backend):
    intent = backend.scheduled_scanner_intent(
        operation_key="scheduled-scanner:20260902T002000Z",
        scheduled_for=datetime(2026, 9, 2, 0, 20, tzinfo=UTC),
    )
    return backend.capture_scheduled_scanner(intent, cancel=Event())


@pytest.mark.parametrize("wrong_session", [False, True])
def test_normal_runtime_seals_iq_then_publishes_results_without_reopening_on_retry(
    tmp_path,
    wrong_session,
):
    events = []
    lifecycle = _Lifecycle(events)
    radio = EvidenceRadio(lifecycle, events, wrong_session=wrong_session)
    backend = LocalAcquisitionBackend(
        _settings(tmp_path, scanner_glrt=OPTIONS),
        CompositionHooks(
            persistent_hop_radio_factory=lambda _: radio,
            persistent_hop_iiod_lifecycle_factory=lambda _: lifecycle,
            persistent_hop_store_factory=lambda root: _RecordingStore(root, events),
        ),
    )
    backend._capture_authority = _RecordingAuthority(events)
    first = capture_once(backend)
    publication = ScannerGlrtStore.open_read_only(tmp_path / "bulk").read(
        first.published.session_id
    )
    assert publication.input_manifest_sha256 == first.published.manifest_sha256
    assert first.published.manifest.receipt == radio.receipt
    assert first.published.manifest.receipt.capture_outcome == "cancelled"
    if wrong_session:
        assert publication.evidence is None
        assert "wire session" in publication.error
        assert first.classification_warning
    else:
        assert publication.evidence.delivery_complete
        assert not publication.evidence.classification_complete
        assert first.classification_warning is None
    second = capture_once(backend)
    assert second.published.manifest_sha256 == first.published.manifest_sha256
    assert second.classification_warning == first.classification_warning
    assert radio.evidence_reads == radio.open_count == radio.close_count == 1
    assert events.index("glrt.read-after-close") > events.index("lifecycle.exit")
    assert events.index("glrt.read-after-close") > events.index("claim.release")
    assert events.index("glrt.read-after-close") > events.index("store.publish")


@pytest.mark.parametrize("failure", ["unsafe_nested_copy", "wrong_identity", "wrong_type"])
def test_invalid_evidence_is_persisted_as_an_explicit_failure(tmp_path, failure):
    iq, capture = make_capture(tmp_path)
    evidence = make_evidence(capture.manifest.receipt)
    if failure == "unsafe_nested_copy":
        # Pydantic model_copy deliberately does not validate nested updates.
        row = evidence.results[0].model_copy(update={"margin": float("nan")})
        evidence = evidence.model_copy(update={"results": (row,)})
    elif failure == "wrong_identity":
        evidence = evidence.model_copy(update={"algorithm_sha256": "c" * 64})
    else:
        evidence = evidence.model_dump()
    warning = publish_scanner_glrt(
        SimpleNamespace(classification_evidence=evidence, classification_error=None),
        capture,
        OPTIONS,
        store_factory=ScannerGlrtStore,
        bulk_root=tmp_path,
    )
    assert "evidence rejected" in warning
    publication = ScannerGlrtStore.open_read_only(tmp_path).read(capture.session_id)
    assert publication.evidence is None and publication.error == warning
    assert iq.verify(capture.session_id).manifest_sha256 == capture.manifest_sha256


def test_cached_capture_never_invents_or_replaces_old_evidence(tmp_path):
    _, capture = make_capture(tmp_path)
    options = dict(store_factory=ScannerGlrtStore, bulk_root=tmp_path)
    warning = existing_scanner_glrt_warning(capture, OPTIONS, **options)
    assert "no GLRT evidence recorded" in warning
    assert not (tmp_path / "scanner-hop-classifications").exists()
    publication = make_publication(capture)
    store = ScannerGlrtStore(tmp_path)
    store.publish(publication)
    warning = existing_scanner_glrt_warning(
        capture, ScannerGlrtOptions("c" * 64, CONFIGURATION), **options
    )
    assert "different GLRT identities" in warning
    assert store.read(capture.session_id) == publication


def test_glrt_store_failure_preserves_published_capture_without_retrying_rf(tmp_path, caplog):
    events = []
    lifecycle = _Lifecycle(events)
    radio = EvidenceRadio(lifecycle, events)

    def broken_store(_):
        raise OSError("injected metadata disk failure")

    backend = LocalAcquisitionBackend(
        _settings(tmp_path, scanner_glrt=OPTIONS),
        CompositionHooks(
            persistent_hop_radio_factory=lambda _: radio,
            persistent_hop_iiod_lifecycle_factory=lambda _: lifecycle,
            scanner_glrt_store_factory=broken_store,
        ),
    )
    first = capture_once(backend)
    assert first.published.manifest.receipt == radio.receipt
    assert first.published.manifest.receipt.restoration.status == "restored"
    assert "metadata disk failure" in first.classification_warning
    second = capture_once(backend)
    assert second.published.manifest_sha256 == first.published.manifest_sha256
    assert "existing GLRT evidence unavailable" in second.classification_warning
    assert radio.open_count == 1 and "IQ capture preserved" in caplog.text


def test_unsupported_radio_publishes_explicit_error_but_disabled_mode_does_no_glrt_io(tmp_path):
    radio = _BoundedPersistentRadio()
    lifecycle = _Lifecycle()
    backend = LocalAcquisitionBackend(
        _settings(tmp_path, scanner_glrt=OPTIONS),
        CompositionHooks(
            persistent_hop_radio_factory=lambda _: radio,
            persistent_hop_iiod_lifecycle_factory=lambda _: lifecycle,
        ),
    )
    captured = capture_once(backend)
    assert "no GLRT evidence" in captured.classification_warning
    publication = ScannerGlrtStore.open_read_only(tmp_path / "bulk").read(
        captured.published.session_id
    )
    assert publication.evidence is None
    other = tmp_path / "disabled"
    other.mkdir()

    def forbidden(_):
        raise AssertionError("disabled GLRT must not open its store")

    backend = LocalAcquisitionBackend(
        _settings(other),
        CompositionHooks(
            persistent_hop_radio_factory=lambda _: _BoundedPersistentRadio(),
            persistent_hop_iiod_lifecycle_factory=lambda _: _Lifecycle(),
            scanner_glrt_store_factory=forbidden,
        ),
    )
    assert capture_once(backend).classification_warning is None
    assert not (other / "bulk/scanner-hop-classifications").exists()
