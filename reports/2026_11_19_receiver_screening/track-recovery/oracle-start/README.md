# Raw GLRT with a known capture-era start

Giving the four-center wide detector the archived pilot epoch recovered **14 of 16 missed targets** at the original fractional gate. Thirteen matched the absolute CFO within 1 kHz, and one matched after the existing CFO alias adjustment. Twelve became the largest-margin wide detection, including eleven absolute-CFO matches. Stock and half-frame sham recovered zero. The hint displaced two unrelated stock positives. This experiment shows how much a correct timing center can recover on these visits, using a label that an operational scout would have to estimate. [Figure](oracle-start.pdf) · [Candidate and rank results](oracle-start.csv)

| Recording and actual template edge | Missed targets gated | Absolute-CFO matches | Becomes wide winner | Retained matched controls | Other stock positives displaced |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0162, upper | 3 / 4 | 3 / 4 | 2 / 4 | 1 / 1 | 0 |
| DS26-0237, lower | 4 / 4 | 3 / 4 | 4 / 4 | 2 / 2 | 0 |
| DS29-0082, upper | 3 / 4 | 3 / 4 | 3 / 4 | 2 / 2 | 0 |
| DS29-0519, lower | 4 / 4 | 4 / 4 | 3 / 4 | 2 / 2 | 2 |

Among the 16 misses, the known start recovered 3/4 weak, 4/4 middle, and 7/8 strong archived winners. Both remaining targets reached a nearby complete fractional epoch but had no matching CFO. No matching complete candidate failed only the gate. One recovered candidate on DS26-0237 matched within the established alias tolerance with a 226,986 Hz absolute CFO difference. There were no unrelated positives added by the known start. The eight planned matched controls include seven accepted trials, all of which retained the same target candidate and acquisition rank. The sham added one other positive in a matched control. [Endpoint counts](counts.json) · [Full fractional results](summary.json)

## Input and execution

Every arm searched all four timing centers and the original ±800 kHz CFO range through the same fractional GLRT and gate. For each target, only the known rounded epoch was supplied to one physical receiver. It replaced the weakest of four time centers when sufficiently separated, leaving the other three centers and the original matcher intact. All 16 admitted misses activated the replacement and searched 12 regional epochs. All seven completed known-match controls used the redundant-hint guard. The untreated receiver reproduced stock factors. The stock arm reproduced both complete archived wide probe entries byte for byte, and the overlay with both hints absent matched all stock public fields other than timings. [Original wide prediction seal](../../receiver-core/full-stride/prediction-lock.json) · [Hinted native ABI](../../receiver-core/hinted-glrt/build-lock.json)

The roster was frozen before reading waveforms. It selects four missed winners covering three independently specified margin bands and two already matched controls per recording, using chronological tie-breaking and one target per distinct visit. Each missed target passed the archived gate and had no exported wide timing within three samples. The verified index cap was 48 MiB per read. The initial worker incorrectly inferred DS26-0162’s template edge from its recording ID. Stock parity rejected visit 0, a matched control. The corrected worker binds the actual archived edge and checks it against the raw metadata. The failed read remains unavailable and was never repeated, leaving 23 accepted from 24 total dual-RX reads. Original and amended sources and all exclusions are retained. Input came from the indexed read-only XFS archive, with local ext4 scratch. [Frozen rule](PROTOCOL.md) · [Input and exclusion lock](input-lock.json) · [Execution correction](execution-amendment.json) · [Worker hash lock](worker-lock.json)

| Host cost, 69 timed calls per arm | Stock | Known epoch | Half-frame sham |
| --- | ---: | ---: | ---: |
| Native detector CPU, dual RX median | 16.46 ms | 16.27 ms | 16.11 ms |
| Python adapter wall, dual RX median | 17.46 ms | 17.46 ms | 17.01 ms |
| Native search CPU, receiver 0 median | 6.96 ms | 6.74 ms | 7.00 ms |
| Native search CPU, receiver 1 median | 5.87 ms | 6.18 ms | 5.91 ms |

Three warm alternating calls per method used paired measurements on the same host core, CPUs 2 or 3. The lane clocks exclude shared setup and detector packing. The stage CSV records both lanes and per-call process CPU and wall time. These costs cover the full raw detector after input loading. The experiment did not rerun positioning or measure physical board performance. [Per-case stage chart](oracle-start.png) · [Per-call timing and stage CSV](oracle-start-stages.csv) · [Result seal](result-lock.json)
