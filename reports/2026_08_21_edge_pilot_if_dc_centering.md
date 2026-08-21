# Qin edge-pilot IF and digital-DC centering review

**Date:** 2026-08-21

**Scope:** repository review of Starlink edge-pilot tuning and sampled-band
geometry; no live-radio operation or corpus mutation

## Executive conclusion

The repository's edge-pilot tuning model is conceptually correct.

The selected pilot does not enter the Pluto at DC. The 9.75 GHz low-band LNB
first converts the Ku-band pilot to an ordinary L-band intermediate frequency
(IF), and the Pluto tunes its receive LO to that IF. The Pluto's direct-conversion
mixer then intentionally places the *center of the eight-tone pilot band* near
zero in complex digital baseband.

No Qin pilot tone lies at DC. After centering, the eight tones are at
`-820,312.5`, `-585,937.5`, `-351,562.5`, `-117,187.5`, `+117,187.5`,
`+351,562.5`, `+585,937.5`, and `+820,312.5 Hz`. A zero-frequency spur or DC
correction notch therefore falls between the two central pilot tones rather
than directly on a pilot.

The important operational limitation is not DC centering. It is the narrow
sampled-band margin of the 2.5 MS/s profile. After the frozen 937.5 kHz pilot
occupied half-width and 300 kHz Doppler guard, only 12.5 kHz remains for
residual centering error and uncertainty. The qualification path recognizes
this limit and fails closed, but no nonzero Pluto filter-edge allowance has yet
been scientifically established.

## Signal-chain interpretation

For a selected pilot RF center `f_pilot`, low-band LNB LO `f_LNB`, and Pluto
receive LO `f_Pluto`, the repository implements:

```text
LNB output IF                 = f_pilot - f_LNB
Pluto complex-baseband center = LNB output IF - f_Pluto
```

Nominal acquisition sets:

```text
f_Pluto = f_pilot - f_LNB
```

so the pilot-band mean appears at digital baseband zero. Doppler, LNB LO error,
Pluto reference error, and path-specific drift move the observed pilot away
from zero by a common carrier-frequency offset (CFO), which the acquisition
pipeline searches and tracks.

CH4 lower is the concrete production example:

```text
Published pilot RF center      11,459,687,500 Hz
Low-band LNB LO               - 9,750,000,000 Hz
                               ------------------
Nominal Pluto IF tune           1,709,687,500 Hz

Nominal digital band center                 0 Hz
```

The word `center_frequency_hz` in capture settings is therefore the Pluto's
analog L-band tuning frequency, not a claim that the physical LNB output is
near zero hertz.

## Low-band edge-pilot tuning authority

The current live capture subset is Qin channels 1 through 4 using the 9.75 GHz
low-band LNB LO. All nominal IF centers lie inside the conventional 950--1950
MHz low-band output range.

| Qin channel | Edge | Pilot RF center | Pluto IF center | Distance to nearest nominal LNB output boundary |
|---:|---|---:|---:|---:|
| 1 | lower | 10,709.6875 MHz | 959.6875 MHz | 9.6875 MHz |
| 1 | upper | 10,940.3125 MHz | 1,190.3125 MHz | 240.3125 MHz |
| 2 | lower | 10,959.6875 MHz | 1,209.6875 MHz | 259.6875 MHz |
| 2 | upper | 11,190.3125 MHz | 1,440.3125 MHz | 509.6875 MHz |
| 3 | lower | 11,209.6875 MHz | 1,459.6875 MHz | 490.3125 MHz |
| 3 | upper | 11,440.3125 MHz | 1,690.3125 MHz | 259.6875 MHz |
| 4 | lower | 11,459.6875 MHz | 1,709.6875 MHz | 240.3125 MHz |
| 4 | upper | 11,690.3125 MHz | 1,940.3125 MHz | 9.6875 MHz |

CH1 lower and CH4 upper are close to the nominal LNB band boundaries. They are
valid frequency mappings, but hardware-specific LNB gain and phase roll-off at
those band edges remains a separate empirical consideration.

The tuning authority is implemented in
[`src/leo/acquisition/starlink_tuning.py`](../src/leo/acquisition/starlink_tuning.py):

- `starlink_edge_rf_center_frequency_hz` selects the published pilot-band RF
  center;
- `starlink_edge_if_center_frequency_hz` subtracts the documented 9.75 GHz
  LNB LO; and
- `_tuning` places that IF center in the requested Pluto settings.

The scanner independently carries the same CH1--CH4 RF centers and derives the
same IF centers in [`src/leo/scanner/models.py`](../src/leo/scanner/models.py).
The Pluto adapters then apply the selected value as `rx_lo` or
`center_frequency_hz`; they do not apply a hidden second frequency translation.

## Why centering at digital DC is acceptable

Qin's two edge-pilot sets contain eight OFDM subcarriers each. The repository
synthesizes either set and subtracts the mean of its absolute subcarrier
frequencies. Both lower and upper edge templates consequently use the same
centered tone geometry:

| Tone | Centered frequency |
|---:|---:|
| 1 | -820,312.5 Hz |
| 2 | -585,937.5 Hz |
| 3 | -351,562.5 Hz |
| 4 | -117,187.5 Hz |
| 5 | +117,187.5 Hz |
| 6 | +351,562.5 Hz |
| 7 | +585,937.5 Hz |
| 8 | +820,312.5 Hz |

This construction is in
[`src/leo/analysis/starlink/templates.py`](../src/leo/analysis/starlink/templates.py),
and the exact values are frozen by
[`tests/dsp/test_starlink_templates.py`](../tests/dsp/test_starlink_templates.py).

Centering gives three benefits:

1. it places the pilot symmetrically within the complex sampled band;
2. it maximizes equal positive- and negative-Doppler headroom at a fixed sample
   rate; and
3. it leaves DC between tones rather than placing an information-bearing pilot
   directly on zero frequency.

The current evidence does not justify moving the pilot away from DC while
retaining the 2.5 MS/s geometry. Such a move would trade a hypothetical DC
improvement for a definite loss of already scarce sampled-band margin.

## Nominal and empirically centered profiles

The ordinary profile
[`profiles/starlink-ch4-lower-2p5m-60s.yaml`](../profiles/starlink-ch4-lower-2p5m-60s.yaml)
uses the nominal CH4-lower IF center of `1,709,687,500 Hz`. Normal paired-radio
tuning may replace this nominal profile center with the selected channel and
edge center, but the same RF-minus-LNB-LO rule applies.

The separate RX1 qualification profile
[`profiles/starlink-ch4-lower-2p5m-60s-rx1-centered-v1.yaml`](../profiles/starlink-ch4-lower-2p5m-60s-rx1-centered-v1.yaml)
uses `1,709,521,250 Hz`, which is 166,250 Hz below the nominal IF. This is an
acquisition-center correction, not a redefinition of the Qin pilot RF center.

Historical evaluation placed two RX1 path centers at approximately
`-170,442.5` and `-162,048.5 Hz` relative to the old nominal tune. The common
`-166,250 Hz` tuner correction leaves historical residuals of `-4,192.5` and
`+4,201.5 Hz`. Thus, although the corrected Pluto LO is not numerically equal
to the nominal pilot IF, its purpose is still to place the *observed* pilot
near digital DC after real receiver-path error. The derivation and its
qualification limits are recorded in
[`docs/qualification/common-rx1-tuner-center.md`](../docs/qualification/common-rx1-tuner-center.md).

The observed center must not be interpreted as intrinsic LNB error alone. It
also contains satellite Doppler and other oscillator/path contributions.

## Sampled-band margin

The frozen qualification geometry uses:

| Quantity | Half-width or allowance |
|---|---:|
| Complex sampled half-band at 2.5 MS/s | 1,250,000 Hz |
| Pilot occupied half-width | 937,500 Hz |
| Satellite Doppler guard | 300,000 Hz |
| Nominal remainder | **12,500 Hz** |

For the two historical centered residuals, the documented maximum uncertainty
remaining after the residual center is only 8,307.5 and 8,298.5 Hz. The
qualification campaign must measure each actual path and reject it if the
observed uncertainty exceeds its remaining margin.

The repository explicitly freezes `EDGE_FILTER_GUARD_HZ = 0.0` because no
additional hardware filter-edge allowance has been established. Zero is not
evidence that the Pluto's usable passband is perfectly flat to Nyquist. It
means this hardware term is still unmeasured. This distinction should be
preserved in future design and review.

## Review findings

1. **No RF/IF arithmetic defect was found.** The CH1--CH4 mappings consistently
   implement `pilot RF center - 9.75 GHz LNB LO`.
2. **The code intentionally centers the pilot band at complex baseband DC.**
   This is standard narrowband direct-conversion behavior, not an attempt to
   feed a zero-frequency signal into the Pluto.
3. **No pilot tone is located at DC.** The closest tones are at
   `+/-117,187.5 Hz`.
4. **The RX1 corrected tune is intentional.** It compensates historical
   path-level observed center offsets so that the real signal, rather than the
   ideal nominal frequency, lies close to digital DC.
5. **The primary risk is sampled-band/filter margin.** The nominal 12.5 kHz
   remainder is narrow and has no experimentally established filter-edge term.
6. **The extreme low-band targets deserve hardware scrutiny.** CH1 lower and
   CH4 upper are only 9.6875 MHz from nominal LNB band boundaries.
7. **A wider capture would change the tradeoff.** At 5 MS/s there would be room
   to test an intentional digital-center offset while retaining Doppler and
   filter margin. Such a change would require explicit versioned scientific
   configuration and component-owned tests; it should not silently alter the
   frozen 2.5 MS/s qualification contract.

## Durable operational reminders

- Keep `IF center`, `pilot RF center`, and `digital baseband frequency` as
  distinct concepts in contracts, reports, and UI labels.
- Do not “fix” the current DC-centered design merely because its digital center
  is zero; first demonstrate a measured DC impairment on the pilot tones.
- Do not reduce the 300 kHz Doppler guard to create apparent bandwidth margin.
- Treat zero filter-edge guard as an unmeasured limitation, not as proven zero
  loss.
- Preserve per-path empirical center and uncertainty evidence. A common
  nominal LNB frequency does not make independent physical receiver paths
  frequency-identical.
- If wider-band capture is evaluated, compare centered and deliberately offset
  tuning on the same reviewed corpus or a separately authorized bounded RF
  capture before changing acquisition policy.

## Verification performed

The review inspected the acquisition tuning authority, scanner target model,
Pluto application path, Qin template construction, ordinary and centered
profiles, and WP11 frequency-calibration documentation. The focused component
suite completed successfully:

```text
tests/acquisition/test_starlink_tuning.py
tests/dsp/test_starlink_templates.py
tests/contracts/test_profiles.py

27 passed
```

No live radio was contacted, no RF collection was started, no QNAP path was
written, and no persisted or golden scientific contract was changed.
