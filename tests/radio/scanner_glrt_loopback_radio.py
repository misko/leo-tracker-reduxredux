"""Hardware-only radio double for the concrete production PPU backend.

All capture/status/metadata operations use the actual network binding. This
does not attest physical tuning or GPIO/FPGA time anchors. The loopback context
is supplied by the test; this class cannot open any radio/network context.
"""

import dataclasses
from types import SimpleNamespace

import numpy as np
from pluto_plus.hardware.iio import IioReceiverSettingsReadback
from pluto_plus.hardware.iio_metadata import IioRawSidecarCaptureSession
from pluto_plus.models import GainMode, Transport


class PrimingAdc:
    """Delegate actual network device operations; hardware anchors unavailable."""

    reg_read = None

    def __init__(self, device):
        self.device = device

    def __getattr__(self, name):
        return getattr(self.device, name)


class PrimingSdr:
    """Only pyadi's hardware layout primer; capture uses real MetadataBuffer."""

    rx_enabled_channels = (0, 1)
    _rxbuf = None

    def __init__(self, device):
        self._rxadc = PrimingAdc(device)

    def rx(self):
        return np.zeros((2, self.rx_buffer_size), dtype=np.complex64)

    def rx_destroy_buffer(self):
        self._rxbuf = None


class LoopbackRadio:
    def __init__(self, uri, serial, context, iio):
        self.context, self.iio = context, iio
        self.identity = SimpleNamespace(
            uri=uri, serial=serial, radio_id="loopback-fixture", transport=Transport.IIO_IP
        )
        self.device = context.find_device("dev0")
        for channel in self.device.channels:
            channel.enabled = True
        self.active_profile = None
        self.lo_hz = 900000000
        self.original = IioReceiverSettingsReadback(
            center_frequency_hz=float(self.lo_hz),
            sample_rate_hz=1000000.0,
            bandwidth_hz=1000000.0,
            channels=(0, 1),
            gain_modes=(GainMode.MANUAL, GainMode.MANUAL),
            gain_db=(10.0, 10.0),
        )
        self.closed = False
        self.capture = None

    def open(self):
        assert self.context.attrs["hw_serial"] == self.identity.serial

    def close(self):
        self.closed = True

    def iio_context_attributes(self):
        return self.context.attrs

    def read_receiver_settings_readback(self):
        return self.original

    def read_active_rx_fastlock_profile(self):
        return self.active_profile

    def configure_source_locked_receiver_geometry(
        self, *, sample_rate_hz, rf_bandwidth_hz, channels, manual_gain_db
    ):
        return dataclasses.replace(
            self.original,
            sample_rate_hz=float(sample_rate_hz),
            bandwidth_hz=float(rf_bandwidth_hz),
            channels=channels,
            gain_db=(manual_gain_db, manual_gain_db),
        )

    def write_center_frequency_bufferless(self, center_frequency_hz):
        self.lo_hz = int(center_frequency_hz)
        self.active_profile = None

    def read_center_frequency(self):
        return float(self.lo_hz)

    def store_rx_fastlock_profile(self, profile):
        return tuple((profile + offset) % 256 for offset in range(16))

    def save_rx_fastlock_profile(self, profile):
        return self.store_rx_fastlock_profile(profile)

    def recall_rx_fastlock_profile(self, profile):
        self.active_profile = profile

    def begin_raw_sidecar_metadata_capture(self, sample_count, *, kernel_buffers, **kwargs):
        self.device.set_kernel_buffers_count(kernel_buffers)
        capture = IioRawSidecarCaptureSession(
            PrimingSdr(self.device),
            self.iio.MetadataBuffer,
            samples_per_channel=sample_count,
            kernel_buffers=kernel_buffers,
            **kwargs,
        )
        capture.open()
        self.capture = capture
        return capture

    def read_kernel_buffers_count(self):
        return self.device.kernel_buffers_count

    def restore_receiver_settings_readback(self, snapshot):
        self.active_profile = None
        self.lo_hz = int(snapshot.center_frequency_hz)
        return snapshot
