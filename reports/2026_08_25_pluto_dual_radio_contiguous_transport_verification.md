# Dual-radio Pluto+ contiguous transport verification

Date: 2026-08-25
Status: bounded local hardware verification complete

> Production follow-up: the complete Leo recorder subsequently passed ten
> strict two-radio 60-second trials at 3 MS/s and was deployed with randomized
> 2.5/3/5 MS/s per-dwell selection. See
> [3 MS/s and 5 MS/s production capture deployment](2026_08_25_3m_5m_production_capture_deployment.md).

## Summary

Two local Pluto+ radios were tested over direct USB and over their native
`192.168.1.*` Ethernet interfaces using paired RX0/RX1 CI16 capture and the
FPGA sample-sequence metadata.

The strict sustained result is:

- **3.0 MS/s per receiver is contiguous for two radios running simultaneously
  for 60 seconds over both USB and standard libiio IP/TCP.**
- 4.0 MS/s over IP/TCP is not a two-radio strict-continuity setting: one radio
  skipped two complete 262,144-sample refills during the 60-second canary.
- 5.0 MS/s over IP/TCP is not a two-radio strict-continuity setting: both
  radios skipped refills during the 60-second canary.
- 5.0 MS/s passed the short individual IP/TCP cells. This did not generalize to
  a simultaneous sustained run and must not be used as continuity evidence.

At 3.0 MS/s, paired CI16 RX requires 24 MB/s per radio and 48 MB/s across the
two radios. Each sustained passing arm returned 180,092,928 sample instants
spanning exactly 180,092,928 FPGA sample times, or 60.030976 seconds of device
time, with zero skipped buffers.

For the complete Leo recorder, 2.5 MS/s remains the conservative production
setting until the K=8 producer/consumer, compression, and storage path passes
the same simultaneous 3.0 MS/s canary. This report qualifies the radio
transport, not the complete durable-recording pipeline.

## Hardware and transport identity

The same two radios were used for both transport runs:

| radio | direct USB URI | native Ethernet URI | firmware |
|---|---|---|---|
| `104000bac4950008230026001b440a003a` | `usb:5.27.5` | `ip:192.168.1.17` | `v0.41-plutoplus-spf-tandem-agc-v8-rc2` |
| `1040007c4a94000211000b009186843ef2` | `usb:3.21.5` | `ip:192.168.1.18` | `v0.41-plutoplus-spf-tandem-agc-v8-rc3` |

Both IP routes resolved through physical interface `enp132s0`, source
`192.168.1.142`. The IP run did not use either radio's `192.168.2.1` USB
gadget network.

The production acquisition controller was already paused before the campaign
and remained paused afterward at generation 21. The benchmark never enabled
TX. Final readback on both radios was the original 2.5 MS/s sample rate,
1.5 MHz RX bandwidth, manual RX gain, and -80 dB on both TX channels.

## Software provenance

| component | revision or identity |
|---|---|
| Leo base used for this report | `5930f6758d3bd14be8eb3890ede93bf58494f1cf` |
| SPF benchmark source | `215b99556308deac5ee57cd7accd162260e6c61b` |
| pluto-plus-utils inventory source | `1562ac5fbcd4ae3ead2dd86430cb7a20de000d30` |
| libiio source checkout | `70739d25ec1fa7b95d9069bd26a3e4192fdb3851` |
| loaded native libiio identity | `0.25 / 6305ea1` |
| native `libiio.so` SHA-256 | `637fae39edf281bb6c697da14e0efc5b1d7c82f6ea8392db5e181d3894e1a135` |
| Python `iio.py` SHA-256 | `cf03126f861ecbdae8abf565a32b39b708c8e7557e4475c70dde739334f24203` |

The capture cell was the unchanged
`tests/radio_hardware/test_iio_transport_benchmark_hardware.py::_capture_cell`
implementation from SPF. A direct pytest invocation could not enumerate USB
contexts because the host-wide libiio scanner tried unavailable Avahi discovery
and returned `ETXTBSY`. The run therefore supplied the already attested USB
and IP URIs explicitly while retaining the same capture cell, metadata parser,
radio settings, TX muting, and restoration logic. No source file was changed
to run the campaign.

## Method

### Short rate matrices

Each short cell used:

- RX0 and RX1 enabled as paired CI16;
- two IIO kernel buffers;
- 262,144 sample instants per refill;
- two warm-up refills;
- 12 timed refills;
- ordinary IIO followed by metadata IIO;
- configured rates of 1, 1.5, 2, 2.5, 3, 5, 10, 20, and 30 MS/s;
- one radio at a time, first over direct USB and then over native IP/TCP.

The complete raw results are in the
[USB matrix](figures/2026_08_25_pluto_dual_radio_contiguous_transport_verification/iio_usb_rate_matrix.json)
and
[IP/TCP matrix](figures/2026_08_25_pluto_dual_radio_contiguous_transport_verification/iio_tcp_rate_matrix.json).

### Simultaneous sustained canaries

The sustained arms ran one capture process per radio at the same time:

| configured rate | timed refills | returned sample instants | nominal device duration |
|---:|---:|---:|---:|
| 3.0 MS/s | 687 | 180,092,928 | 60.030976 s |
| 4.0 MS/s | 916 | 240,123,904 | 60.030976 s |
| 5.0 MS/s | 1,145 | 300,154,880 | 60.030976 s |

Strict continuity required both:

```text
capture_index_gap_count == 0
captured_sample_coverage_ratio == 1.0
```

The SPF helper also emits `continuous_sustainable` using a looser
`coverage >= 0.98` and host-delivery threshold. That field is useful for
capacity classification but is not a gapless claim. In particular, the
5.0 MS/s sustained IP cells passed that loose threshold while their FPGA
counters proved missing refills. This report uses the strict rule only.

## Results

### Short matrices

| transport | rate | radio `003a` | radio `3ef2` | strict interpretation |
|---|---:|---:|---:|---|
| USB | 3.0 MS/s | 100% coverage, 0 gaps, 23.969 MB/s | 100%, 0 gaps, 23.938 MB/s | pass |
| USB | 5.0 MS/s | 70.588%, 5 gaps, 26.680 MB/s | 70.588%, 5 gaps, 26.374 MB/s | fail |
| IP/TCP | 3.0 MS/s | 100%, 0 gaps, 24.001 MB/s | 100%, 0 gaps, 23.961 MB/s | pass |
| IP/TCP | 5.0 MS/s | 100%, 0 gaps, 40.046 MB/s | 100%, 0 gaps, 39.968 MB/s | short-cell pass only |
| IP/TCP | 10.0 MS/s | 63.158%, 7 gaps, 49.718 MB/s | 63.158%, 7 gaps, 47.994 MB/s | fail |

The USB failure establishes only that the strict breakpoint is somewhere above
3.0 and at or below 5.0 MS/s; 4.0 MS/s was not tested over USB.

### Simultaneous 60-second canaries

| transport | rate | radio `003a` | radio `3ef2` | strict result |
|---|---:|---:|---:|---|
| USB | 3.0 MS/s | 100% coverage, 0 gaps, 24.002 MB/s | 100%, 0 gaps, 24.000 MB/s | **pass** |
| IP/TCP | 3.0 MS/s | 100%, 0 gaps, 24.001 MB/s | 100%, 0 gaps, 24.000 MB/s | **pass** |
| IP/TCP | 4.0 MS/s | 100%, 0 gaps, 32.001 MB/s | 99.782%, 2 gaps, 31.932 MB/s | **fail** |
| IP/TCP | 5.0 MS/s | 98.792%, 14 gaps, 39.517 MB/s | 99.565%, 5 gaps, 39.826 MB/s | **fail** |

At 4.0 MS/s, radio `3ef2` omitted 524,288 FPGA sample instants. At
5.0 MS/s, radio `003a` omitted 3,670,016 and radio `3ef2` omitted
1,310,720. Every omission was an integer number of 262,144-sample refills.

The sustained evidence is preserved in:

- [USB, two radios, 3.0 MS/s](figures/2026_08_25_pluto_dual_radio_contiguous_transport_verification/iio_usb_two_radio_60s_3m.json)
- [IP/TCP, two radios, 3.0 MS/s](figures/2026_08_25_pluto_dual_radio_contiguous_transport_verification/iio_tcp_two_radio_60s_3m.json)
- [IP/TCP, two radios, 4.0 MS/s](figures/2026_08_25_pluto_dual_radio_contiguous_transport_verification/iio_tcp_two_radio_60s_4m.json)
- [IP/TCP, two radios, 5.0 MS/s](figures/2026_08_25_pluto_dual_radio_contiguous_transport_verification/iio_tcp_two_radio_60s_5m.json)

## Decision

For this host, these two radios, paired RX, 262,144-sample refills, and the
counter-metadata libiio path:

1. **3.0 MS/s per receiver is the highest tested strict-contiguous rate shared
   by USB and native Ethernet.**
2. **The two-radio native-Ethernet strict breakpoint lies between 3.0 and
   4.0 MS/s per receiver.**
3. 4.0 or 5.0 MS/s must not be described as sustained contiguous based on
   individual short cells.
4. The Leo production recorder should remain at 2.5 MS/s until its complete
   K=8 queue and durable-storage path is separately qualified at 3.0 MS/s.

This is a delivered-RX adjacency result on each radio's FPGA sample clock. It
does not establish UTC synchronization or phase coherence between the radios,
and it is not evidence for the custom finite-burst direct-IP UDP transport.

## Evidence digests

| artifact | SHA-256 |
|---|---|
| `iio_usb_rate_matrix.json` | `f8cd9c462b6f13f0dd59b36d053fd366b27c08bab4c475a381c6dc9b7c21076e` |
| `iio_usb_two_radio_60s_3m.json` | `da55bc47f5948e96b55784d7a3357017a26bbdd34d7a10855da231cd0ed17bec` |
| `iio_tcp_rate_matrix.json` | `efc970a1844ecaf9440a2a03666374ad507f36e4694022ea88b6fdd023331211` |
| `iio_tcp_two_radio_60s_3m.json` | `4fca67ecfad514dbb2a763e2eedc95b39d720abb3293f835f6bbdd3ef0ca3e99` |
| `iio_tcp_two_radio_60s_4m.json` | `33131d7fa366c624c5e8cb713ced5923903aadad0e4ae9932707ebabddae8450` |
| `iio_tcp_two_radio_60s_5m.json` | `230930b0022f89a98dfc45724e5267d4c0c2cf22e4ab7f58a7357225dea8e75a` |
