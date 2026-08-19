# Common RX1 tuner center

The frozen CH4-lower RX1 hardware profile is
`profiles/starlink-ch4-lower-2p5m-60s-rx1-centered-v1.yaml`, revision
`sha256:0f6aa753e16feaba1f76df21f0b620f32ab0b72456cb6034f2b1ea6a60c11e1a`.
It uses an integer IF center of `1,709,521,250 Hz` and RF center of
`11,459,521,250 Hz`. The RF identity remains
exactly `IF + 9,750,000,000 Hz`; `starlink_channel=ch4` and
`starlink_edge=lower` are unchanged. This is an acquisition-center correction,
not a redefinition of the Starlink channel edge.

The historical detector evaluation reported recommended RX1 acquisition
centers of `-170,442.5 Hz` for LNB-B and `-162,048.5 Hz` for LNB-D at the old
`1,709,687,500 Hz` IF tune. Their midpoint is `-166,245.5 Hz`. The selected
whole-Hz common correction is `-166,250 Hz`, producing residual historical
centers of `-4,192.5 Hz` and `+4,201.5 Hz`. Source:
`leo-tracker/reports/starlink-detector-evaluation/figures/abscal-pipeline-abscal.json`,
under the top-level JSON object `rebinned` (that is,
`rebinned["lnb-b|gen2"]` and `rebinned["lnb-d|gen2"]`).

The Pluto path is integer-preserving: the profile contract stores integer Hz,
the adapter passes that value to `pluto-plus-utils`, the utility rounds once to
the IIO `rx_lo` integer, and the persisted applied settings are rounded back to
integer Hz. Capture acceptance requires the applied center to equal the frozen
integer exactly, so a different hardware readback cannot qualify.

At 2.5 MS/s the sampled half-band is 1,250,000 Hz. After subtracting the frozen
937,500 Hz pilot occupied half-width and the symmetric 300,000 Hz satellite
Doppler guard, only 12,500 Hz remains for residual center plus empirical
uncertainty. The two residual centers therefore permit at most 8,307.5 Hz and
8,298.5 Hz uncertainty respectively. This is feasible in principle (the
predeclared measurement allowance is 500 Hz), but it is narrow. Historical
centers do not qualify the new campaign by themselves. The separate
pre-acceptance calibration must measure each chain at this new tune and the
existing sampled-band gate must reject either chain if its observed uncertainty
exceeds its actual remaining margin. No Doppler, pilot-width, or uncertainty
gate is weakened by this retune.
