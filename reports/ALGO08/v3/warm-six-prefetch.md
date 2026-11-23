# Verified page-warm acquisition across six signed members

On the existing fully resident public North tmpfs recording, six-member verified acquisition sustained **285.15–295.76 compressed MB/s** with serial demand and **294.84–297.31 MB/s** with one-member prefetch. All four runs passed both 231 and 250 MB/s and produced byte-identical detector packets. Prefetch saved **72.67 ms** in the first order and added **5.32 ms** in reverse. The matched orders do not establish a repeatable prefetch gain. No DS30 waveform traffic was generated. [Protocol](warm-six-prefetch-protocol.md) · [Complete admission, timing and science receipt](measurements/warm-six-prefetch.json.gz)

## Passive admission

Before reading waveforms, the first six original DS30-0008 members were ineligible. The first compressed member had **5,891 of 18,907 pages** and the other five had zero. DS30-0016 initially had all six members and indexes resident, so it was enrolled. The initial physical arm stopped reading its manifest because the release Python lacks the flags wrapper for `preadv2`. The libc-backed guard corrected that, but the passive readmission found **176 missing payload pages** across the six members. No physical arm reached waveform acquisition. There was no prewarming, eviction or staging of original input. [Passive states and launch boundaries](measurements/warm-six-prefetch.json.gz)

The existing signed public North tmpfs copy then qualified under its owner, with full file residency before and after every accepted arm. Its six members contain **506,934,774 compressed and 614,400,000 decoded bytes**. Each accepted arm read exactly **507,178,478 logical source bytes** including the original indexes and manifest. The public read path checked the tmpfs device and full residency of every held waveform or metadata descriptor before using it. All five traversals charged **2,534,673,870 compressed logical bytes**. Two earlier public serial starts completed traversal but stopped before sealing when the overly strict process-wide counter showed 159,744 and 1,302,528 bytes. Across those two discarded traversals and the five accepted arms, total public compressed reads were **3,548,543,418 logical bytes**. The process counter can include unrelated storage reads. The final matched comparison retained that counter separately while guarding every signed input descriptor. [Scope and guard implementation](warm_six_prefetch.py)

## Matched costs

| Order | Reader | Acquisition CPU / elapsed s | Compressed MB/s | Fresh process CPU / elapsed s | Process-wide physical input bytes, acquisition / entire process |
|---:|---|---:|---:|---:|---:|
| 1 | Serial demand | 1.774 / 1.778 | 285.15 | 3.773 / 3.824 | 442,368 / 5,541,888 |
| 2 | One-member prefetch | 1.704 / 1.705 | 297.31 | 3.573 / 3.626 | 69,632 / 118,784 |
| 3 | One-member prefetch | 1.718 / 1.719 | 294.84 | 3.635 / 3.674 | 0 / 0 |
| 4 | Serial demand | 1.713 / 1.714 | 295.76 | 3.635 / 3.671 | 0 / 12,288 |
| 5 | Serial verification, DSP omitted | 0.850 / 0.852 | 595.12 | 2.751 / 2.770 | 0 / 86,016 |

At this size, 231 and 250 MB/s allow **2.195 and 2.028 s** through acquisition. The verification-only arm omits the waveform searches and leaves the full signed reader and empty-row construction in place. It took **0.86–0.93 s** less than the two serial DSP runs. This is the observed detector-work ceiling on this warm prefix. The helper lent all five future members, **422,678,803 bytes per pass** with zero fallback, and charged **86.76 and 86.45 ms CPU** inside the acquisition clock. Total demand wait was **25.92 and 26.74 µs**. The four DSP outputs each took under 1.7 ms to seal. Peak process RSS was **416–418 MiB** with DSP and about **399 MiB** with verification only. One helper at most shared CPU 2 and the same low-priority Gauss lock. There was no additional public input staging in these measurements. [All scoped clocks and guards](measurements/warm-six-prefetch.json.gz)

## Scientific identity

Every pass authenticated all six compressed member and index digests, all 384 per-window I/Q digests and all six whole-decoded digests. The resident prefix had all **384 admitted stereo visits**, with no exclusions. The four DSP passes made **96 full and 672 short antenna calls**, and reproduced all **768 ordered probes and 359 factors** from the original signed mixed-aperture receiver, with its original hardware clock anchor and prefix deliveries. Their complete detector document SHA-256 was `2a3f7069a06497c7c5c01fdecc8ec5f20b1e19f1224c279bf3773640e2e117c0`. The verification-only arm retained the same acquisition authority and opportunities and returned empty factor lists. These rates characterize the public resident tmpfs recording and leave real DS30 warm and cold six-member rates unmeasured. [Prior three-member public comparison](public-short-prefetch.md) · [Postponed cold physical trial](long-physical-prefetch-admission.md)

The accepted files remain at `/dev/shm/leo-v3-warm-six-public-03`. The runner takes the signed short-receiver library and a new output directory. Its `--public-after` input binds the failed passive real-source admission when continuing under the public tmpfs owner's account. Six component and adjacent tests passed. [Runner](warm_six_prefetch.py) · [Guard tests](../../../tests/pipeline_eval/test_warm_six_prefetch.py)
