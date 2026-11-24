# DS30-0397 completed with fresh causal phase support

Count DS30-0397 as a **verified successor fix** and an **installed solver
failure**. The successor's saved audit records four live corner
support extensions. It propagated **1,116 new SGP4 states** and retried the
same strict interpolation stencil at unchanged times and phases.
The full candidate publication contains both calibrated positions,
the 179-point grid, the path and eight verified PNGs.
[Machine receipt](measurements/ds30-0397-orbit-support-audit.json.gz)

## Failure and repaired dispatch

The installed worker failed in receiver-smooth corner exploration during
initial rank, before either calibration fit or a terminal. Its native
sparse ranking port calls the strict phase projector on each active
satellite over the scan's track times and three phase offsets
`φ`, `φ + 0.05 s` and `φ − 0.05 s`. Both the initial attempt and the
installed retry threw `ValueError: orbit phase interpolation never
extrapolates` at that test. The installed retry patches
`ScanLikelihood.shifted` on the class. The sparse rank port already
sets a `shifted` method on the scan instance, which shadows the class
method. The second traceback still enters the sparse instance method.

The frozen successor binds support at that instance method while the
actual initial corner runs. It first calls the same strict projector.
After a range rejection, the repair checks the capture origin, exact
nominal orbit grid, NORAD order and selected position/velocity rows.
It independently propagates the needed knots from the same causal
catalogue rows, checks usable finite states and retains the nominal
states. It then passes the original query times, phases and derivative
step back to the same projector on the expanded bank. The projector
still rejects requests beyond its supplied knots. Four actual
extensions succeeded and the run performed one inference with zero
whole-solver restarts. The published orbit policy is `orbit_support`.
The source-pinned demonstration shows the original projector rejecting
synthetic queries of −25.49, −25.44 and −25.54 s, then reconstructing all
three exactly after adding the causal-support knot pattern. It does
not reconstruct the as-run phases or propagate any TLE.

The recorded successor ranking used its existing two-centre scout and
the original four corners. The two arms consumed different verified
native packets with the same inventory, 6,773 issued visits and 6,375
admitted visits. They share the same hardware clock and causal
authority. The successful trace proves valid support for the
successor's actual queries. The failed stock trace preserves neither
the numeric offending phase nor which side of its domain was exceeded.
It supplies no same-packet counterfactual.

## Time and causal authority

The orbit origin is the measured clock-bracket midpoint,
**2026-11-19 21:41:23.110483904 UTC**. The causal cutoff is the distinct
bracket start at **21:41:23.021204777 UTC**. The successor's latest
passing native timestamp is 299.961249 s. Its nominal one-second
bank therefore spans **−17 to +317 s** relative to the origin.
The actual extension added every knot **from −26 to −18 s**, moving
the earliest supported UTC from **21:41:06.110483904** to
**21:40:57.110483904**. Since the guard floors
`min(track_time) + min(active_phase) − 0.05 s`, the earliest
actual derivative query lies in **[−26, −25) s**. Available
telemetry leaves each individual proposal and active NORAD list
unknown. The repair admits absolute phases of at most 30 s and real
track times inside the nominal observation interval.

The receipt binds the same enrolled archive for both arms. The
successor logged **132 authenticated reads of 236,048,464 bytes**
across **46 verified snapshot names and 41 distinct bodies**. The
latest read snapshot was collected at **20:05:08.280273822 UTC** on
November 19, **5,774.741 s before the causal cutoff**. No body hit
the earlier portable index. The selected-element preparation checks
the archived publication times and element epochs against the
original cutoff before propagation. The extension takes those same
selected satellite objects from the live nominal bank.

## Verified output

| Calibration | Horizontal error | Conditional RF RMS | All-owner RF RMS | Ordered owners | Grid minimum |
| --- | ---: | ---: | ---: | ---: | --- |
| Fixed `c = 0` | 0.736061 km | 139.860 Hz | 169.113 Hz | 3,242 | Own endpoint, index 0 |
| Fitted `c` | 0.877525 km | 139.692 Hz | 147.721 Hz | 3,242 | Own endpoint, index 1 |

The sealed path and grid rederive their scientific digests and bind
the exact terminal, native packet, two owner maps and position PNG.
All 179 locations have finite scores in both arms. Endpoint objective
replay is zero. The native grid audit records 708 projections and
356 selections and design assemblies. The path records five
refinement rounds in both arms. The existing final-fit clamp of
numerical expansion references to ±15 s belongs to the ordinary
phase-reference policy. The failed corner interpolation precedes
that fit and the repair preserves its query.

The successor's verified wall time was **61.143 s**. Installed spent
**90.017 s** before its failed exit. These clocks have different
terminal outcomes and belong outside successful-pair speedup
comparisons. No waveform or TLE body was opened for this audit and
no solver was rerun. The bounded synthetic stencil and three
component tests verified the report's interpretation.
[Audit and bounded demonstration](ds30_0397_orbit_support_audit.py) ·
[Tests](../../../tests/pipeline_eval/test_ds30_0397_orbit_support_audit.py)
