# DS30-0086 joint short-lane restoration

The DS30-0049 edit rule improved DS30-0086 by **152.088 m fixed-zero** and
**82.864 m fitted** relative to the original sparse publication. Both gains
fall below the 250 m development yardstick from DS30-0049. Both estimates
also finished closer to the survey than either full-aperture control. This
is an independent acquisition from the same roof and uses an oracle for the
installed receiver's selected factors. [Frozen transfer protocol](ds30-0086-joint-recovery-protocol.md) · [Sealed measurement and score](measurements/ds30-0086-joint-recovery.json.gz)

| Publication | Horizontal error fixed / fitted | Conditional RF RMS fixed / fitted | All-owned RF RMS fixed / fitted | Owners per arm |
| --- | ---: | ---: | ---: | ---: |
| Original installed 20 ms | 402.304 / 409.842 m | 130.429 / 130.129 Hz | 155.161 / 152.493 Hz | 2,486 |
| Original sparse 20/8 | 370.631 / 381.596 m | 179.824 / 180.081 Hz | 202.582 / 189.681 Hz | 2,095 |
| Charted same fitter on installed packet | 450.798 / 457.139 m | 130.433 / 130.131 Hz | 155.489 / 152.979 Hz | 2,486 |
| Joint short-lane restoration | 218.543 / 298.732 m | 150.721 / 150.641 Hz | 173.550 / 165.599 Hz | 2,689 |

The joint gain relative to original installed was 183.761 / 111.110 m.
Against the charted solver on the installed packet, it was 232.255 /
158.407 m. The remaining conditional RF difference above full-aperture was
about 20 Hz in each arm. Each row describes the RF fits on its own support.
The run did not separate the gains from the two edit classes on this case.
[Original scientific controls](field-receiver-solver-cross-0086.md)

The independently derived ledger inserts **564** genuine installed tuples
on empty sparse short lanes and replaces **464** disagreeing short winners.
RX0 contributes 229 insertions and 273 replacements. RX1 contributes 335
insertions and 191 replacements. All 1,202 full-anchor rows retain the
original sparse values, including 495 selected full factors. All other rows
stay in the same chronological order. The packet keeps 6,771 issued visits,
1,984 invalid visits and 4,787 admitted stereo visits. The selected factor
count moves from 3,671 to 4,235. Construction used the complete resident
copies of both signed original detector packets and checked the original
unfiltered short-aperture recipe, receiver clocks, inventory, raw authority,
offer and causal view. The geographic reference was opened only during
scoring.

Graph assigned 3,218 observations across 103 tracks, versus 2,434 across 85
on the matching saved sparse baseline. Each final arm has 2,689 owners
across 78 tracks and 27 satellites, including 353 inserted and 319 replaced
lanes. The sparse comparison shares 1,953 IDs, with 43 changing satellite
and 50 changing role. The charted full comparison shares 2,390 IDs, with six
changing satellite and 68 changing role. Of the edited owned rows, 302
insertions and 282 replacements have the same observation ID, satellite and
role on charted full. The official installed/full owner digest and count
match charted full. Only the charted full receipt includes the ordered roles.

The exact charted route used the healthy-history lean interior fit and kept
the supplied 25 km offer. Both calibration arms returned signed positions,
a complete 179-position grid with zero endpoint replay differences, a bound
position path and all eight independently decoded PNGs. The run used one
verified saved handoff and no receiver or selector replay or backing reads.
All 50 exact causal bodies and the verified portable index were resident
before launch. The used portable path attached 12 cached bodies and parsed
14 staged original bodies, with zero fallback. The one worker finished in
**16.666 s wall / 16.052 s CPU**, charging 130,928 process input blocks and
183 major faults. The bounded waiter spent 20.286 s outside the paid process.
The prior exact saved sparse control took 15.132 / 14.820 s and the prior
same-fitter full control 16.736 / 16.114 s in other leases. Packet derivation
took 0.594 / 0.586 s. These are saved-work boundaries. No raw speed or
deployable receiver gain was measured. [Exact saved sparse baseline](sparse8-cfo-epoch.md)

The transfer was frozen at `625a1514b` and the worker source at
`32d58fe75`. Twenty-three component and adjacent checks passed. The packet
SHA-256 is `78b84fec05063d5d89d2903ff2a8a7acc48f4db447fc06702f8cbb1390e6b172`.
The prediction seal is `629b9a85ba8f676d655b01acb8f5171c981f4fcb169500d37d56f746f191ddb9`
and the independent score is `11855be87a03b2c29b8b3ce16cb6916abb38a9e4f47bf5930007816faa52fde1`.
[DS30-0049 development result](ds30-0049-joint-recovery.md)
