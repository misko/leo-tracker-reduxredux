# Saved publication layout prepass on DS30-0016

The prototype reduced median CPU for the eight genuine figures from **1.481 to 1.375 s** across six renders per arm. All **96 generated PNGs** matched the archived physical candidate byte for byte, including decoded pixels, dimensions, mode and metadata. The 12 fresh official publications also reproduced the manifest, numerical grid and path, and scan report. The median difference was **106 ms** on this packet, with variable results under direct stage clocks.

## What changed

The installed control already shares pixels across the two orbit views, reuses ticks and layout, and encodes through the native lossless path. For the two residual plots, the track RMS plot and the regional position map, Matplotlib also walks the artists while renderer output is disabled, before the real saved draw. The prototype keeps the original aspect preparation and both passes of the constrained-layout engine and skips that preliminary artist traversal. The normal final draw and original PNG encoder still run. The patch is scoped to the serial Agg experiment at Matplotlib 3.11.1, ordinary uncropped PNGs in memory and constrained figures without draw callbacks.

The trial restored the plotting packet from the sealed physical candidate's saved detector JSON and matched both arms, the ordered satellite and role rows and the numerical grid and path. The regenerated grid's elapsed field was excluded from that comparison. The original sealed sidecars then went through the official store with the generated figures so their published bindings stayed exact. Numerical restoration took 2.93–3.17 CPU s outside the render timers. The trial used the capture-era archive and original offered region, without reading I/Q.

## Matched timings and interpretation

| Order | Installed renderer CPU s | Layout-only renderer CPU s | Median reduction |
| --- | ---: | ---: | ---: |
| Installed, layout, layout, installed | 1.477 / 1.516 | 1.397 / 1.331 | 132 ms |
| Installed, layout, layout, installed, with stage observers | 1.444 / 1.612 | 1.383 / 1.366 | 153 ms |
| Layout, installed, installed, layout, with stage observers | 1.485 / 1.376 | 1.304 / 1.427 | 65 ms |

A first attempt to reverse the sequence reversed a palindrome and repeated the installed-first block. The runner now switches the first arm explicitly. Both observed orders are retained in the receipt. The final reversed block had a 180 ms improvement in its first paired comparison and a 51 ms slowdown in its second.

The four constrained figures' prepass and final draw together had median CPU of 607 ms installed and 534 ms with the patch across the two instrumented blocks. The repeated installed-first block cost about 10 ms more with the patch in this combined stage. In the layout-first block, it saved 151–182 ms. The final draw sometimes recovered work removed from the disabled traversal. Encoder CPU also varied despite identical outputs, with aggregate medians of 191 and 169 ms. The observed whole-render difference is larger than the reduction in the directly affected combined draw stage. This experiment does not establish a stable or fully attributable speedup.

Official publication, scan report and ordinary artifact readback took about 9 ms CPU per eight-figure bundle in both arms. The previously measured empty-residual-scatter optimization can omit at most 16 collections on this newer physical result with only two fitted satellite IDs and 16 residual axes, compared with 228 omitted on the earlier larger physical result. Dense publication work remains unmeasured here.

The physical candidate spent 7.980 CPU s in the publication function, including 3.426 in acquisition and 3.026 in solve. That leaves **1.528 CPU s** for all other work in that function, including rendering, input and output bookkeeping and report publication. The measured render opportunity is a small part of the candidate's 9.442 s total process CPU. A whole-process timing or a 2× result does not follow from this renderer comparison. [Original physical pair](full-short-physical.md)

Seventeen targeted prototype, existing layout and encoder tests passed. [Frozen procedure](saved-publication-layout-protocol.md) · [Per-render timing and validation receipt](measurements/saved-publication-layout.json) · [Prototype](saved_publication_layout.py) · [Saved replay](saved_publication_trial.py) · [Component tests](../../../tests/pipeline_eval/test_saved_publication_layout.py)
