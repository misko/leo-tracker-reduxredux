from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.cli.persistent_hop_canary import (
    PersistentHopCanarySettings,
    _parser,
    run_persistent_hop_canary,
)
from leo.storage.errors import BundleNotFoundError


class _QueueTelemetry:
    def model_dump(self, *, mode: str):
        assert mode == "json"
        return {"capacity_visits": 64, "high_water_visits": 3}


class _Store:
    def __init__(self, root: Path, published) -> None:
        self.root = root
        self.spool_root = root
        self.bundles_root = root
        self.published = published
        self.verified = False

    def inspect(self, session_id: str):
        assert session_id == "durable-canary"
        raise BundleNotFoundError(session_id)

    def verify(self, published):
        assert published is self.published
        self.verified = True
        return published


def _published(plan, root: Path):
    receipt = SimpleNamespace(
        qualified=True,
        radio_id="radio-a",
        radio_serial="serial-a",
        radio_uri="ip:192.168.1.18:30432",
        capture_outcome="complete",
        visits=(object(), object()),
        target_coverage=tuple(
            SimpleNamespace(target=profile.target, visit_count=2) for profile in plan.profiles
        ),
        valid_sample_count=600_000,
        transition_invalid_sample_count=25_000,
        duty_denominator_sample_count=625_000,
        valid_duty_ppm=960_000,
        valid_duty_percent=96.0,
        duty_target_met=True,
        continuity_attested=True,
        missing_sample_count=0,
        overflow_count=0,
        hop_event_sequence_gap_count=0,
        restoration=SimpleNamespace(status="restored"),
    )
    manifest = SimpleNamespace(
        plan=plan,
        receipt=receipt,
        queue_telemetry=_QueueTelemetry(),
        chunks=(object(),),
        uncompressed_bytes=4_800_000,
        compressed_bytes=4_000_000,
        uncompressed_sha256="sha256:" + "a" * 64,
    )
    return SimpleNamespace(
        session_id="durable-canary",
        path=root / "scanner-hop-recordings/2026/09/03/durable-canary",
        uri="bulk://scanner-hop-recordings/2026/09/03/durable-canary",
        manifest_sha256="sha256:" + "b" * 64,
        manifest=manifest,
    )


def _settings(tmp_path: Path) -> PersistentHopCanarySettings:
    return PersistentHopCanarySettings(
        host="192.168.1.18",
        expected_serial="serial-a",
        radio_id="radio-a",
        bulk_root=tmp_path,
        sample_rate_hz=2_500_000,
        session_id="durable-canary",
        iiod_port=30_432,
    )


def test_canary_uses_alternate_endpoint_and_verifies_published_scanner_history(tmp_path) -> None:
    calls = []
    stores = []
    ticks = iter((10.0, 312.0, 320.5))

    def radio_factory(host, **kwargs):
        calls.append((host, kwargs))
        return "radio"

    def store_factory(root):
        store = _Store(root, None)
        stores.append(store)
        return store

    def capture(radio, plan, **kwargs):
        assert radio == "radio"
        assert kwargs["session_id"] == "durable-canary"
        assert kwargs["queue_capacity_visits"] == 64
        stores[0].published = _published(plan, stores[0].root)
        return stores[0].published

    summary = run_persistent_hop_canary(
        _settings(tmp_path),
        radio_factory=radio_factory,
        store_factory=store_factory,
        disk_usage=lambda _root: SimpleNamespace(free=20_000_000_000),
        capture=capture,
        monotonic=lambda: next(ticks),
    )

    assert calls == [
        (
            "192.168.1.18",
            {
                "expected_serial": "serial-a",
                "radio_id": "radio-a",
                "iiod_port": 30_432,
                "read_ahead_visits": 8,
            },
        )
    ]
    assert stores[0].verified
    assert summary["passed"] is True
    assert summary["radio_uri"] == "ip:192.168.1.18:30432"
    assert summary["rf_bandwidth_hz"] == summary["sample_rate_hz"] == 2_500_000
    assert summary["samples_per_block"] == 131_072
    assert summary["kernel_buffers"] == 8
    assert summary["read_ahead_visits"] == 8
    assert summary["capture_elapsed_seconds"] == 302.0
    assert summary["verification_elapsed_seconds"] == 8.5
    assert summary["storage"]["full_chunk_verification_passed"] is True
    assert summary["storage"]["scanner_history_eligible"] is True


def test_canary_refuses_insufficient_space_before_constructing_radio(tmp_path) -> None:
    settings = _settings(tmp_path)
    store = _Store(tmp_path, None)

    with pytest.raises(RuntimeError, match="storage admission rejected"):
        run_persistent_hop_canary(
            settings,
            radio_factory=lambda *_args, **_kwargs: pytest.fail("radio opened"),
            store_factory=lambda _root: store,
            disk_usage=lambda _root: SimpleNamespace(free=7_073_741_823),
            capture=lambda *_args, **_kwargs: pytest.fail("capture started"),
        )


def test_canary_refuses_unwritable_publication_root_before_radio(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    store = _Store(tmp_path, None)
    store.spool_root = tmp_path / "spool"
    store.bundles_root = tmp_path / "scanner-hop-recordings"
    store.spool_root.mkdir()
    store.bundles_root.mkdir()
    monkeypatch.setattr(
        "leo.cli.persistent_hop_canary.os.access",
        lambda path, _mode: Path(path) != store.bundles_root,
    )

    with pytest.raises(PermissionError, match="scanner-hop-recordings"):
        run_persistent_hop_canary(
            settings,
            radio_factory=lambda *_args, **_kwargs: pytest.fail("radio opened"),
            store_factory=lambda _root: store,
            disk_usage=lambda _root: SimpleNamespace(free=20_000_000_000),
            capture=lambda *_args, **_kwargs: pytest.fail("capture started"),
        )


def test_canary_cli_makes_alternate_port_explicit_and_keeps_exact_defaults(tmp_path) -> None:
    args = _parser().parse_args(
        [
            "--host",
            "192.168.1.18",
            "--serial",
            "serial-a",
            "--radio-id",
            "radio-a",
            "--bulk-root",
            str(tmp_path),
            "--sample-rate",
            "5000000",
            "--iiod-port",
            "30432",
        ]
    )

    assert args.iiod_port == 30_432
    assert args.transition_guard_us == 5_000
    assert args.samples_per_block == 131_072
    assert args.kernel_buffers == 8
    assert args.read_ahead_visits == 8
    assert args.queue_capacity_visits == 64
    assert args.safety_reserve_bytes == 1024**3
