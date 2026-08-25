# 3 MS/s and 5 MS/s production capture deployment

Date: 2026-08-25
Status: deployed and live-verified

## Outcome

Revision `b4c59a6e1931a3b28ef9a4b16dca480ef0619e2b` is deployed for the
global, API, worker, and acquisition selectors. The production acquisition
supervisor chooses one profile uniformly per scheduled dwell from the ordered
pool below and applies that same profile to both radios:

| mode | profile | production interpretation |
|---:|---|---|
| 2.5 MS/s | `starlink-ch4-lower-2p5m-60s-continuity-v2` | conservative contiguous mode |
| 3.0 MS/s | `starlink-ch4-lower-3m-60s-capture-v2` | qualified contiguous capture-only mode |
| 5.0 MS/s | `starlink-ch4-lower-5m-60s-segmented-v2` | experimental segmented capture-only mode |

The deployed selection policy is `uniform_per_dwell`: each profile has
probability 1/3 for a dwell. Selection occurs once before the durable operation
is enqueued; it is not selected independently for each radio. The persisted
operation also makes retries and supervisor restarts replay the same choice.

No radio firmware was changed. The production pair remains on
`v0.38-plutoplus-spf-libiio-metadata-v5`, advertises metadata ABI 1, and is used
through the receipt-pinned pyadi/pylibiio host path.

## Production identities and runtime

| item | deployed identity |
|---|---|
| Leo revision | `b4c59a6e1931a3b28ef9a4b16dca480ef0619e2b` |
| pluto-plus-utils revision | `162fa9b4fd42f264b5d8960a6530923242581e96` |
| native libiio | `0.25 (c26258b)`, metadata ABI 1 |
| native libiio SHA-256 | `6bd7c8acc4909db12d7d8f67303ca3ff0ee437fa431d4a6ff0846e98a51c4f03` |
| Python iio SHA-256 | `c5b8a2b53ffc4ddfe4258dab4173edcd554e0ecf5a276b0fc47db0cb3dc8e12b` |
| network route | `enp132s0`, source `192.168.1.142` |
| radio A | `radio_pluto_5d4d`, serial `1040005e0b100007100010000bf33a5d4d`, `ip:192.168.1.20` |
| radio B | `radio_pluto_19f2`, serial `10400056f695001322002d0010ad1719f2`, `ip:192.168.1.21` |

## Strict 3 MS/s recorder qualification

The V3 promotion contract intentionally qualifies the exact production
native-IP path. A separate USB pair with different firmware and metadata ABI is
diagnostic hardware, not evidence for the deployed radios, and is not a V3
prerequisite. The retained gates are:

- exact production radio, host, source revision, PPU, libiio, and pylibiio identities;
- per-radio host-IIO safety and exact RX-setting restoration evidence;
- one-second counter-authoritative native-IP canaries on both radios;
- an incompressible writer benchmark of at least 72 MB/s;
- exactly ten simultaneous two-radio 60-second recorder trials;
- K=8 kernel buffers, queue capacity 32, queue high-water at most 24;
- exact bundle digest verification and zero gaps, missing samples, overflows,
  enqueue failures, or terminal rejections in every trial.

The campaign `rate-3m-1787690934776725874-87f8b72b` passed all gates:

| measurement | result |
|---|---:|
| trials / committed trials | 10 / 10 |
| complete radio streams | 20 / 20 |
| observed sample instants | 3,600,000,000 |
| device-span sample instants | 3,600,000,000 |
| gaps / missing / overflow / enqueue failures | 0 / 0 / 0 / 0 |
| maximum queue high-water | 17 / 32 |
| maximum refill service interval | 127,185,529 ns |
| qualification threshold | 699,050,666 ns |
| uncompressed IQ | 28,800,000,000 bytes |
| compressed IQ | 13,933,301,646 bytes |
| writer throughput | 108.486 MB/s |

The read-only accepted receipt is:

```text
/srv/bulk/leo/qualification/sample-rate-3m/accepted/b4c59a6e1931a3b28ef9a4b16dca480ef0619e2b/contiguous-rate-qualification-receipt-v3.json
```

Its file SHA-256 is
`ce2c343fefef8e16ea873bf34718016b89fc9ea04b08af7648ebdd240ed64e73`,
and its canonical target digest is
`sha256:ae032fdc864cfb35f88d2d4760980b3332637950c6f0b9c25994438802b20394`.
The incompressible writer receipt SHA-256 is
`8ad264e153924e20f13b8f3a5bac20d5778c746623c8f7fab0031824d94c44d0`.

This is the end-to-end result that promotes 3 MS/s: the complete Leo producer,
bounded queue, compressor, durable store, manifest, gap map, and digest verifier
all participated. It supersedes the earlier report's restriction of 3 MS/s to
transport-only evidence.

## 5 MS/s segmented characterization

5 MS/s is not presented as contiguous. The first live production dwell after
deployment randomly selected the 5 MS/s profile for both radios. Its durable
operation payload recorded the exact three-profile pool,
`selection_policy=uniform_per_dwell`, and the ordered production radio IDs.

Session `cap-20260825T210634-100cd778f0a9` covered the full requested
300,000,000-device-sample interval on each radio while storing only observed IQ:

| radio | observed | missing | coverage | gaps | Q high-water | max refill |
|---|---:|---:|---:|---:|---:|---:|
| `radio_pluto_5d4d` | 286,892,800 | 13,107,200 | 95.6309% | 50 | 20/32 | 112.621 ms |
| `radio_pluto_19f2` | 277,717,760 | 22,282,240 | 92.5726% | 85 | 18/32 | 125.926 ms |

Both streams were `partial`, the session was `degraded`, and there were zero
overflow flags or enqueue failures. The counter-derived gap maps preserve every
omission. Bundle verification passed with 138 chunks, 4,516,884,480
uncompressed bytes, 3,260,152,133 compressed bytes, two timelines, and two gap
maps. Automatic Standard analysis refused the degraded capture, as required for
the `CAPTURE_ONLY`/`EXPERIMENTAL` mode.

The manifest is:

```text
/srv/bulk/leo/recordings/2026/08/25/cap-20260825T210634-100cd778f0a9/manifest.json
```

Its SHA-256 is
`d7d28d079d9aee5cbd3d69f44779287531116ed63afca9154b8d9e7e72fe5c8a`.

## Deployment and live state

The full deployment transaction completed in 204.813 seconds and reported
`healthy=true`. Its receipt is:

```text
/srv/bulk/leo/qualification/deployment/deploy-20260825T210540Z-b4c59a6e1931a3b28ef9a4b16dca480ef0619e2b.json
```

The deployment receipt SHA-256 is
`11f3b32eb0e90d874c65a5f23fd10bf292e393308ab809669f2109ed7b978b60`.
All four selectors resolve to the target revision. `leo-api.service` and
`leo-acquisition.service` are active. Capture authority is running at generation
22 after an explicit resume with reason
`resume receipt-qualified 2.5/3/5 MS/s production pool`.

## Decision

1. Use 2.5 MS/s when conservative margin is preferred.
2. Treat 3.0 MS/s per receiver as qualified counter-contiguous production
   capture for this exact two-radio Ethernet station and runtime.
3. Treat 5.0 MS/s only as loss-observable segmented capture. It is useful when
   wider instantaneous bandwidth justifies missing source time, but it is not a
   contiguous mode. The first live dwell missed 4.3691% on radio A and 7.4274%
   on radio B; future loss can vary.
4. Keep 3 MS/s and 5 MS/s tagged `CAPTURE_ONLY`; widening scientific analysis
   support remains a separate reviewed change.
5. Continue using metadata counters as the continuity authority. Host delivery
   pace or stored sample indexes alone are not sufficient evidence.
