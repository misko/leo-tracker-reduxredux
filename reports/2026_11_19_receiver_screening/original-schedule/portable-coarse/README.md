# Standalone original detector from dual CI16

The static C program regenerated **112 ordered coarse seeds** and reproduced **both gate-driven retries** on six held dual-receiver visits from three authentic capture producers. The raw input carried physical CI16, edge, receive-lane mask, sample count and calibrated CFO bounds. The program regenerated the Qin templates and ran coarse scoring, historical peak selection, fine CFO search, and integer and fractional GLRT. The held inputs came from the earlier frozen verifier study, with its stored templates and supplied coarse seeds stripped before execution. [Held seed and gate ledger](summary.json) · [Frozen inputs](input-lock.json) · [Protocol](PROTOCOL.md)

The portable result agreed with the installed detector on all discrete gates and on all distinct candidate ranks. Two equivalent duplicates exchanged internal seed identities on native x86 and retained their physical epoch, acquired CFO, gates and equal ranked evidence. The 112 attempt-level candidates included 17 integer passes and 19 fractional passes. The largest held fractional margin difference was 7.80 × 10⁻¹⁴ and the largest fractional epoch difference was 3.01 × 10⁻¹³ samples. The closest held positive margin was 2.31 × 10⁻⁶ above the 0.025 gate. Earlier hardware-clock-authenticated archived rows also agreed. [Native verification](x86.json) · [Original verifier qualification](../../coarse-and-navigation/portable-verifier/README.md)

## Coarse bank and public templates

The C entry point rolls eight finite Qin tone correlations for each CFO, applies the actual binary64-derived seam correction, and combines anchor contributions before magnitude and original frame-support normalization. The 12-anchor mask uses direct signed QPSK mixing and the 22-anchor mask shares the four relative phase sums of adjacent tone pairs. Selection preserves linear local-peak edges, circular epoch suppression, the inclusive CFO radius, stable lane discovery order, and the original bounded ±1-sample epoch nudge. Each emitted seed includes the clipped 500 Hz search start and count required by the frozen verifier. [Coarse API](../../../../tools/pipeline_eval/variants/portable_coarse.h) · [Portable C kernel](../../../../tools/pipeline_eval/variants/portable_coarse.c)

Both edge families and rolls are generated in C from the published eight-tone QPSK states. Their maximum deviation from the installed float32 templates was 2.36 × 10⁻¹⁶. On 12 development grids across both masks and physical lanes, maximum score error relative to the prepared float32 bank was 9.12 × 10⁻⁸. Every tested ordered peak key agreed. The rolling score map uses approximate floating-point recurrence arithmetic. Component tests cover signed CFO and epoch ties, circular suppression, a silent receiver, receiver masking, and exact support counts on truncated inputs. The downstream verifier requires a full 200,000-sample visit. [Development evidence](summary.json) · [Component tests](../../../../tests/pipeline_eval/test_portable_coarse.py)

## Standalone runtime

| Measured native boundary | Median process CPU | Median wall |
|---|---:|---:|
| Cold template and verifier setup | 4.53 ms | 5.03 ms |
| One 12-anchor coarse lane | 67.45 ms | 68.63 ms |
| One 22-anchor coarse lane | 96.51 ms | 97.63 ms |
| One fine CFO and GLRT verification group | 40.32 ms | 40.78 ms |
| Complete dual visit with primary only | 214.46 ms | 218.50 ms |
| Complete dual visit with partner retry | 355.29 ms | 362.43 ms |

The native rows use three repetitions per held visit on a pinned x86 core. Complete timing sums the coarse and verifier stages after resident CI16 is available. Named allocation totals include 5,374,168 bytes for coarse, 5,858,144 bytes for the verifier, and a 1,600,000-byte raw input buffer. The independently launched native process peaked at 13,320 KiB RSS. The x86 and AArch64 static executables are 958,016 and 777,416 bytes. The Cortex-A9 executable is 5,146,168 bytes unstripped, including a 544,976-byte text section. [Stage chart](stage.pdf) · [CPU and wall rows](stage.csv) · [Native direct resource receipt](native-direct-resources.json)

Each ARM build reproduced 40 exact ordered seeds and one genuine retry from the same two short held windows, spanning both edges. Each produced the same 11 fractional passes and matched the installed oracle and archived decisions within the existing numerical tolerances. The measurements used host QEMU. [AArch64 results](aarch64.json) · [Cortex-A9 results](cortex-a9.json)

## Build and input

The C kernel links with libm and has no FFT library dependency. The unified executable also links the frozen standalone verifier sources. The target binaries and exact build commands are sealed. The derived fixture can be regenerated from the earlier sealed capture bundle with the trial driver. This stage ends at original acquisition and GLRT output, before calibrated association or positioning. [C driver](../../../../tools/pipeline_eval/qualification/portable_coarse_cli.c) · [Build and replay commands](../../../../tools/pipeline_eval/qualification/portable_coarse_trial.py) · [Qualification seal](qualification-lock.json)

The little-endian input starts with `LEOCOA01` and a `uint32` visit count. Each visit has five `uint32` fields for visit, sample count, edge (`0` lower, `1` upper), two-bit receiver mask, and mode. Four binary64 fields follow for receiver 0 center, receiver 1 center, minimum residual and maximum residual, all in hertz. CI16 follows in `[sample][physical receiver][I,Q]` order. Mode `1` runs the complete detector with conditional retry, mode `0` runs primary coarse, and mode `2` evaluates both coarse anchor masks for diagnostics. [Raw header writer](../../../../tools/pipeline_eval/qualification/portable_coarse_trial.py)
