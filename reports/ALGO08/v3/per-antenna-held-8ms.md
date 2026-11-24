# Per-antenna history under the 8 ms North mask

The per-antenna rule did not recover North localization. Against the same
globally routed mask, it reduced the fixed-`c` error by 21 m and increased the
fitted-`c` error by 84 m. Both errors exceeded the corresponding complete
8 ms history results. The fixed-`c` arm exceeded the named ALGO08v3 error by
645 m and failed the predeclared named-plus-250 m condition.

| Receiver and selection | Fixed-`c` error (m) | Fitted-`c` error (m) | Fixed/fitted RF RMS (Hz) | Owners per arm |
|---|---:|---:|---:|---:|
| Named ALGO08v3 | 105.690 | 140.779 | 5.406 / 5.167 | 302 |
| Complete 8 ms, global history | 111.954 | 128.086 | 9.133 / 8.921 | 342 |
| Masked 8 ms, globally unfiltered | 771.969 | 162.150 | 11.590 / 9.899 | 319 |
| **Masked 8 ms, per antenna** | **751.014** | **245.917** | **16.926 / 12.657** | **171** |

The frozen held-cycle gain was +4.191 nats on radio 0 and −4.270 on radio 1.
History retained 114 of 560 measured radio-0 factors. Radio 1 retained all
529. The selector used the original masked chronology with all 2,400 signed
lane opportunities and no CFO remeasurement. The mask represented 304 full
anchor lanes and 1,408 short lanes paid, with 688 short lanes omitted. All 171
candidate owners were present with identical family and role in the globally
masked control. Against complete 8 ms, 119 were shared, 223 were lost, 52 were
added and 13 shared observations changed role in each calibration. The
original named publication preserves only owner counts and signed map digests
for this join. Both per-antenna arm endpoints were on the original offered
face, and the signed scoring reference was 100 m inside. The table uses
terminal RF RMS, separate from position error.

The same-sign path reproduced the entire original selected packet and
detector recipe byte for byte. The genuine physical DS30-0016 8 ms control
chose unfiltered on both radios at −25.287/−11.749 nats, retaining 506 factors.
The genuine complete North 8 ms control chose history at +92.630/+83.174
nats, retaining 456 factors. Both are saved selector checks with no new
localization solves.

## Paid boundaries

One fresh saved numerical worker exited zero in **5.172 s elapsed and
5.161 s CPU**, including authentication and signoff for the reprojected mask,
the selector and one staged detector handoff. Acquisition, including any
potential masked DSP saving, was outside this boundary. Saved input checks,
masking, history and packet signing took 0.127 s CPU in scope, including
0.077 s for the selector with its independent full history replay. Numerical
solve took 2.789 s CPU and rendering 0.731 s. The separately measured parity
and font setup took 0.216/0.181 s elapsed. The historical globally masked
publication took 5.747 s elapsed and 5.742 s CPU and received an already
serialized packet. It is a single comparison with different factor counts,
setup and page state (616 vs 112 filesystem input blocks). The previous
complete 8 ms and named control clocks (10.828 s and 16.761 s elapsed)
include waveform acquisition and have a different boundary from this saved
trial.

The solver used the original offer and pre-RF archive, native geographic
proof, corrected portable orbit index (11 sidecar hits, no fallback), and
grouped rank (176 compact profiles, one admitted rank and zero original
ranks). The original survivor finish accepted. A complete matched 137-node
grid and all eight PNGs were verified, including signed path/grid sidecars
bound to each publication's own position PNG. The owner maps and both arms are
in the receipt. The normalized globally masked reference was checked against
its preserved pre-normalization seal, whose scientific outputs are identical.

The mask outcome motivated this North-only diagnostic. It did not qualify
per-antenna routing for geographic transfer. No other publication was run.

## Reproduction

The [frozen protocol](per-antenna-held-8ms-protocol.md) is at `b7494de99`.
The timed launch used `2b3377755`. The [trial driver](radio_held_8ms_trial.py)
accepts `launch`, `seal` and `score` with a fresh tmpfs output directory.
Run on Gauss holding `/tmp/leo-algo08v2-2x-bench/gauss.lock`, CPU2,
`nice -n 15`, `ionice -c 2 -n 7` and numerical thread variables set to 1.
Use the named release's Python and the checkout's research, `src` and root
directories plus released payload, `src` and root on the outer PYTHONPATH.
Run the offline verifier as the output-directory owner. Original staged
assets and all input pins are recorded in the
[receipt](measurements/per-antenna-held-8ms.json.gz).
The three component tests cover signs and ties, signed projection and exact
same-sign delegation. The paid root is
`/dev/shm/leo-v3-per-antenna-held-8ms-result01`.
