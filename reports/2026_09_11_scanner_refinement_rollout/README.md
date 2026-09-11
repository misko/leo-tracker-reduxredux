# Scanner local and joint refinement comparisons

The [historical 2.5 / 5 MS/s study](../2026_09_11_glrt_refinement_prototype/README.md)
contains the paired-rate results, supporting PNGs, raw probe outputs, and SHA-256
inventory. Local frequency refinement usually reduces frequency-grid error;
joint timing/CFO iteration substantially improves delay-shift recovery. Neither
method wins on every probe, and neither resolves the 227 kHz alias ambiguity.

This companion adds two downloadable PNGs to each fixed or adaptive scan's web
detail: **Shift-recovery RMS** and **Individual probe errors**. The four settings
are 512, 8192, local refinement initialized from 512, and joint refinement
initialized from the local result. The existing detector, hop decisions, and
published scan products retain their behavior.

## What the live figures measure

The worker selects two interior visits per observed channel target and both
receivers, at most 32 probes. Selection does not depend on signal strength or
whether refinement helps. Each 21 ms stored-IQ read supplies a 20 ms analysis
window after symmetric cropping. Both native 2.5 and 5 MS/s inputs are supported.

Each probe receives one reproducible signed frequency shift of 100–2,000 Hz and
one signed delay of 30–300 ns, independently. Acquisition is rerun on the original
and both transformed inputs. All eight retained candidates are recorded for all
four profiles. Association uses the strongest passing baseline 512 candidate's
frame phase, an 800 ns gate, and exact GLRT score; it does not use the imposed
frequency shift to pick the correct answer.

The known imposed change is the reference. This measures relative shift
consistency, **not absolute Doppler or timing accuracy**, and does not use a cubic
track as ground truth. RMS bars use the same successfully recovered cases across
all four profiles. Recovery denominators, processing failures, and alias changes
remain visible. The individual-probe PNG preserves raw frequency errors, including
large alias jumps, on a symmetric logarithmic axis. Empty support is shown as
unavailable, never as zero error.

## Publication and operation

The existing analysis timer runs a companion worker before ordinary scanner
backfill. An invocation has a 180-second budget checked between probes and saves
a checkpoint after each probe. Later invocations resume pending work. Evidence
and both PNGs are published before the final immutable manifest. The API serves
only digest-verified saved bytes and never performs analysis on a page request.
The evidence binds the capture manifest, implementation files, deterministic
probe schedule, selected and rejected candidates, and measured runtime.

Deployment and observed scanner verification will be recorded here after the
installed release has been exercised.
