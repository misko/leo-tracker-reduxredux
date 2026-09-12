from dataclasses import replace

import pytest

from pluto_plus import bootstrap_firmware as b


def test_restore_preserves_qualified_target_and_requires_exact_source():
    standard = b.STANDALONE_FLASH_PROFILES["iq-direct-async-v4-release-persistent-promotion"]
    restore = b.STANDALONE_FLASH_PROFILES["iq-direct-async-v4-from-pss30-1r1t-restore"]
    assert (
        replace(
            restore,
            policy=standard.policy,
            source_iio_layout=standard.source_iio_layout,
            return_iio_layout=standard.return_iio_layout,
            allowed_before_firmwares=(),
        )
        == standard
    )
    assert restore.policy.model_dump(exclude={"profile_id"}) == standard.policy.model_dump(
        exclude={"profile_id"}
    )
    assert restore.policy.asset_sha256 == (
        "f45524f4765d5743144703ff6f4541084ff1ab9b1ce20a77f3f6fa820a1f84b6"
    )
    assert restore.source_iio_layout is b.SINGLE_RX_DETECTOR_ONLY_LAYOUT
    assert restore.return_iio_layout is b.SINGLE_RX_TX_CAPABLE_LAYOUT
    b._require_allowed_before_firmware("starlink-pss30-iio-v1-dnm", restore)
    with pytest.raises(b.BootstrapFirmwareError, match="source firmware"):
        b._require_allowed_before_firmware("starlink-pss60-iio-v1-dnm", restore)


def test_source_rejects_active_rx_scan_and_wrong_tx_shape():
    facts = {
        "device_names": ("ad9361-phy", "cf-ad9361-lpc", "starlink-pss"),
        "cf-ad9361-lpc,scan_channels": (),
    }

    def check(value):
        b._require_iio_layout_shape(
            value,
            b.SINGLE_RX_DETECTOR_ONLY_LAYOUT,
            expected_tandem=False,
            transport="source",
        )

    check(facts)
    for update in (
        {"cf-ad9361-lpc,scan_channels": ("voltage0", "voltage1")},
        {"device_names": (*facts["device_names"], "cf-ad9361-dds-core-lpc")},
        {"device_names": (*facts["device_names"], "tandem-agc")},
    ):
        with pytest.raises(b.BootstrapFirmwareError):
            check(facts | update)
